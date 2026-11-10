"""Adapter to P3's gateway; never imports a provider SDK or calls provider HTTP APIs."""

import importlib
import inspect
import json
from collections.abc import Callable
from contextlib import nullcontext
from typing import Protocol

from pydantic import BaseModel

from app.content.models import ModelIdentity, Record
from app.llm.gateway import Completion, verification_scope

TASKS = {
    "plan_research": "graph",
    "assess_research_plan": "graph",
    "assess_research_source": "graph",
    "select_library": "graph",
    "extract_graph": "graph",
    "generate_items": "items",
    "generate_hint": "tutor",
    "verify_item": "verify",
    "verify_hint": "verify",
}


class GatewayError(RuntimeError):
    pass


class ModelReply(Record):
    content: object
    identity: ModelIdentity


class Gateway(Protocol):
    async def generate(
        self,
        *,
        task: str,
        tier: str,
        system: str,
        payload: dict[str, object],
        schema: type[BaseModel],
        exclude_family: str | None = None,
    ) -> ModelReply: ...


class P3Gateway:
    """Use TEAM's complete signature; optional per-call envelope preserves fallback identity.

    P3 may expose complete_with_metadata with the same arguments, returning
    {content: str|BaseModel|dict, identity: {provider, model, family, identity_source: gateway}}.
    Plain TEAM responses remain usable for draft generation, but cannot pass the gate.
    Identity is never read from model-authored JSON or guessed from provider/model names.
    """

    def __init__(self, complete: Callable[..., object] | None = None) -> None:
        if complete is None:
            try:
                module = importlib.import_module("app.llm.gateway")
                complete = getattr(module, "complete_with_metadata", None) or module.complete
            except (ImportError, AttributeError) as exc:
                raise GatewayError("P3 gateway is not available") from exc
        self._complete = complete

    async def generate(
        self,
        *,
        task: str,
        tier: str,
        system: str,
        payload: dict[str, object],
        schema: type[BaseModel],
        exclude_family: str | None = None,
    ) -> ModelReply:
        routed_task = TASKS.get(task, task)
        if routed_task == "verify" and exclude_family not in KNOWN_FAMILIES:
            raise GatewayError("Verification requires a known actual generator family")
        # Family exclusion is request-local policy, NEVER part of model-visible payloads.
        scope = verification_scope(exclude_family) if exclude_family else nullcontext()
        with scope:
            result = self._complete(
                task=routed_task,
                tier=tier,
                system=system,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                schema=schema,
            )
            if inspect.isawaitable(result):
                result = await result
        if isinstance(result, Completion):
            return ModelReply(
                content=result.value,
                identity=ModelIdentity(
                    provider=result.route.provider,
                    model=result.route.model,
                    family=result.route.family,
                    identity_source="gateway",
                ),
            )
        if isinstance(result, ModelReply):
            return result
        if isinstance(result, dict) and set(result) == {"content", "identity"}:
            return ModelReply.model_validate(result)
        return ModelReply(
            content=result,
            identity=ModelIdentity(
                provider="unknown", model="unknown", family=None, identity_source="unavailable"
            ),
        )


def parse_reply[T: BaseModel](reply: ModelReply, schema: type[T]) -> T:
    value = reply.content
    if isinstance(value, str):
        return schema.model_validate_json(value)
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return schema.model_validate(value)


# A metadata value must identify a family, not just a model, version or provider.
# P3/P1 own taxonomy changes. Unknown taxonomy values fail closed.
KNOWN_FAMILIES = frozenset({"gpt", "claude", "gemini", "llama", "mistral", "qwen", "deepseek"})


def independent(generator: ModelIdentity, verifier: ModelIdentity) -> bool:
    return (
        generator.identity_source in {"gateway", "agent_session"}
        and verifier.identity_source == "gateway"
        and bool(generator.model.strip())
        and bool(verifier.model.strip())
        and bool(generator.provider.strip())
        and bool(verifier.provider.strip())
        and generator.family in KNOWN_FAMILIES
        and verifier.family in KNOWN_FAMILIES
        and generator.family != verifier.family
    )
