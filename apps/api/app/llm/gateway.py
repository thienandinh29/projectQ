"""Bounded model fallback, validated output and request-scoped verification policy."""

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from typing import Literal, Protocol

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class Route(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["vertex", "bedrock", "openrouter", "deepseek", "gemini"]
    model: str = Field(min_length=1)
    family: Literal["gemini", "claude", "deepseek"]


class Routing(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tiers: dict[str, dict[str, list[Route]]]


@dataclass(frozen=True)
class ProviderReply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0


@dataclass(frozen=True)
class Completion:
    value: str | BaseModel
    route: Route
    latency_ms: float
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class Attempt:
    """Sanitized per-call telemetry, including paid responses rejected by validation."""

    task: str
    tier: str
    route: Route
    number: int
    latency_ms: float
    status: Literal["success", "validation_error", "provider_error", "timeout", "cancelled"]
    input_tokens: int
    output_tokens: int
    thoughts_tokens: int = 0
    error_code: str | None = None


class ProviderError(Exception):
    """Sanitized provider failure; raw HTTP responses must not reach logs."""

    def __init__(
        self, code: str, *, retryable: bool = False, reply: ProviderReply | None = None
    ) -> None:
        super().__init__(code)
        self.retryable = retryable
        self.reply = reply


class GatewayError(Exception):
    pass


class Adapter(Protocol):
    async def generate(
        self,
        route: Route,
        system: str,
        messages: Sequence[Message],
        schema: type[BaseModel] | None,
    ) -> ProviderReply: ...


@dataclass(frozen=True)
class GenerationLimits:
    max_tokens: int = 4096
    thinking_budget: int = 1024


_limits: ContextVar[GenerationLimits | None] = ContextVar("generation_limits", default=None)


def generation_limits() -> GenerationLimits:
    return _limits.get() or GenerationLimits()


_excluded_family: ContextVar[str | None] = ContextVar("generator_family", default=None)
KNOWN_GENERATOR_FAMILIES = frozenset(
    {"gemini", "claude", "deepseek", "gpt", "llama", "mistral", "qwen"}
)


@contextmanager
def verification_scope(generator_family: str) -> Iterator[None]:
    """P4 supplies Completion.route.family from the actual generator response."""
    if generator_family.casefold() not in KNOWN_GENERATOR_FAMILIES:
        raise ValueError("The actual generator family must use the known P4 identity taxonomy")
    token = _excluded_family.set(generator_family.casefold())
    try:
        yield
    finally:
        _excluded_family.reset(token)


def load_routing(path: Path | None = None) -> Routing:
    path = path or Path(__file__).with_name("routing.yaml")
    return Routing.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class Gateway:
    def __init__(
        self,
        routing: Routing,
        adapters: Mapping[str, Adapter],
        *,
        attempts_per_model: int = 2,
        request_timeout: float = 35,
        total_timeout: float = 100,
        observe: Callable[[Completion], Awaitable[None]] | None = None,
        observe_attempt: Callable[[Attempt], None] | None = None,
        task_limits: Mapping[str, GenerationLimits] | None = None,
    ) -> None:
        if attempts_per_model < 1 or request_timeout <= 0 or total_timeout <= 0:
            raise ValueError("Invalid gateway limits")
        self.routing = routing
        self.adapters = adapters
        self.attempts = attempts_per_model
        self.request_timeout = request_timeout
        self.total_timeout = total_timeout
        self.observe = observe
        self.observe_attempt = observe_attempt
        # Structured question batches need more than a single tutor response's 4096 tokens.
        self.task_limits = {
            "graph": GenerationLimits(16384),
            "items": GenerationLimits(16384),
            "verify": GenerationLimits(8192),
        }
        self.task_limits.update(task_limits or {})
        if any(
            v.max_tokens < 1 or not 0 <= v.thinking_budget < v.max_tokens
            for v in self.task_limits.values()
        ):
            raise ValueError("Invalid generation limits")

    async def complete_with_metadata(
        self,
        task: str,
        tier: str,
        system: str,
        messages: Sequence[Message | dict[str, str]],
        schema: type[BaseModel] | None = None,
    ) -> Completion:
        routes = self.routing.tiers.get(tier, {}).get(task)
        if not routes:
            raise GatewayError(f"No route for tier/task: {tier}/{task}")
        excluded = _excluded_family.get()
        if task == "verify" and excluded is None:
            raise GatewayError("Verification requires verification_scope(actual_generator_family)")
        parsed = [m if isinstance(m, Message) else Message.model_validate(m) for m in messages]
        if not parsed or parsed[0].role != "user":
            raise GatewayError("Messages must start with a user turn")
        started = monotonic()
        failures: list[str] = []
        try:
            async with asyncio.timeout(self.total_timeout):
                for configured in routes:
                    if task == "verify" and configured.family.casefold() == excluded:
                        continue
                    model = os.path.expandvars(configured.model)
                    if "$" in model or not model.strip() or model.endswith(":free"):
                        failures.append(f"{configured.provider}:model_not_configured")
                        continue
                    if configured.family not in model.casefold():
                        failures.append(f"{configured.provider}:model_family_mismatch")
                        continue
                    route = configured.model_copy(update={"model": model})
                    adapter = self.adapters.get(route.provider)
                    if adapter is None:
                        failures.append(f"{route.provider}:adapter_missing")
                        continue
                    for attempt in range(self.attempts):
                        if attempt:
                            await asyncio.sleep(0.2 * 2 ** (attempt - 1))
                        attempt_started = monotonic()
                        error_code: str | None = None
                        reply: ProviderReply | None = None
                        status: Literal[
                            "success", "validation_error", "provider_error", "timeout", "cancelled"
                        ] = "cancelled"
                        try:
                            async with asyncio.timeout(self.request_timeout):
                                limits_token = _limits.set(
                                    self.task_limits.get(task, GenerationLimits())
                                )
                                try:
                                    reply = await adapter.generate(route, system, parsed, schema)
                                finally:
                                    _limits.reset(limits_token)
                            if not reply.text.strip():
                                raise ProviderError("empty_response", retryable=True)
                            value = schema.model_validate_json(reply.text) if schema else reply.text
                            result = Completion(
                                value,
                                route,
                                (monotonic() - started) * 1000,
                                reply.input_tokens,
                                reply.output_tokens,
                            )
                            status = "success"
                        except (ValidationError, TimeoutError, ProviderError) as exc:
                            status = (
                                "validation_error"
                                if isinstance(exc, ValidationError)
                                else "timeout"
                                if isinstance(exc, TimeoutError)
                                else "provider_error"
                            )
                            if isinstance(exc, ProviderError):
                                reply = exc.reply or reply
                                error_code = str(exc)
                            failures.append(f"{route.provider}:{type(exc).__name__}")
                            if isinstance(exc, ProviderError) and not exc.retryable:
                                break
                            continue
                        finally:
                            if self.observe_attempt:
                                self.observe_attempt(
                                    Attempt(
                                        task,
                                        tier,
                                        route,
                                        attempt + 1,
                                        (monotonic() - attempt_started) * 1000,
                                        status,
                                        reply.input_tokens if reply else 0,
                                        reply.output_tokens if reply else 0,
                                        reply.thoughts_tokens if reply else 0,
                                        error_code,
                                    )
                                )
                        if self.observe:
                            await self.observe(result)
                        return result
        except TimeoutError:
            raise GatewayError("LLM request exceeded total deadline") from None
        raise GatewayError("No eligible model succeeded: " + ", ".join(failures))

    async def complete(
        self,
        task: str,
        tier: str,
        system: str,
        messages: Sequence[Message | dict[str, str]],
        schema: type[BaseModel] | None = None,
    ) -> str | BaseModel:
        return (await self.complete_with_metadata(task, tier, system, messages, schema)).value


def schema_instruction(system: str, schema: type[BaseModel] | None) -> str:
    if schema is None:
        return system
    return (
        system
        + "\nReturn only JSON matching this schema:\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


_configured_gateway: ContextVar[Gateway | None] = ContextVar("llm_gateway", default=None)


@contextmanager
def gateway_scope(gateway: Gateway) -> Iterator[None]:
    """P2 can inject telemetry and job-specific deadlines without changing complete()."""
    token = _configured_gateway.set(gateway)
    try:
        yield
    finally:
        _configured_gateway.reset(token)


async def complete_with_metadata(
    task: str,
    tier: str,
    system: str,
    messages: Sequence[Message | dict[str, str]],
    schema: type[BaseModel] | None = None,
) -> Completion:
    from app.llm.providers import default_gateway

    gateway = _configured_gateway.get() or default_gateway()
    return await gateway.complete_with_metadata(task, tier, system, messages, schema)


async def complete(
    task: str,
    tier: str,
    system: str,
    messages: Sequence[Message | dict[str, str]],
    schema: type[BaseModel] | None = None,
) -> str | BaseModel:
    return (await complete_with_metadata(task, tier, system, messages, schema)).value
