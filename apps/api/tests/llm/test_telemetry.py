import asyncio

from pydantic import BaseModel

from app.llm.gateway import (
    Attempt,
    Gateway,
    complete_with_metadata,
    gateway_scope,
    verification_scope,
)
from tests.llm.test_gateway import Fake, routes


def test_rejected_paid_outputs_are_observed() -> None:
    class Answer(BaseModel):
        count: int

    attempts: list[Attempt] = []
    fake = Fake(["invalid JSON", '{"count":2}'])
    gateway = Gateway(routes(), {"vertex": fake}, observe_attempt=attempts.append)
    result = asyncio.run(
        gateway.complete_with_metadata(
            "items",
            "free",
            "s",
            [{"role": "user", "content": "q"}],
            Answer,
        )
    )
    assert result.value == Answer(count=2)
    assert [a.status for a in attempts] == ["validation_error", "success"]
    assert sum(a.input_tokens for a in attempts) == 20
    assert sum(a.output_tokens for a in attempts) == 10


def test_public_gateway_entry_point_uses_job_scope() -> None:
    fake = Fake(["generated", "verified"])
    gateway = Gateway(routes(), {"vertex": fake, "bedrock": fake})

    async def run() -> None:
        with gateway_scope(gateway):
            generated = await complete_with_metadata(
                "items", "free", "system", [{"role": "user", "content": "q"}]
            )
            with verification_scope(generated.route.family):
                verified = await complete_with_metadata(
                    "verify", "free", "blind", [{"role": "user", "content": "cited chunks"}]
                )
                assert generated.route.family != verified.route.family

    asyncio.run(run())
    assert fake.models == ["gemini-test", "claude-test"]


def test_retry_backoff_is_not_provider_latency() -> None:
    from unittest.mock import patch

    from app.llm.gateway import ProviderError

    clock = [0.0]

    async def sleep(delay: float) -> None:
        clock[0] += delay

    attempts: list[Attempt] = []
    fake = Fake([ProviderError("busy", retryable=True), "ok"])
    with (
        patch("app.llm.gateway.monotonic", side_effect=lambda: clock[0]),
        patch("app.llm.gateway.asyncio.sleep", sleep),
    ):
        result = asyncio.run(
            Gateway(
                routes(), {"vertex": fake}, observe_attempt=attempts.append
            ).complete_with_metadata("items", "free", "s", [{"role": "user", "content": "q"}])
        )
    assert [a.latency_ms for a in attempts] == [0, 0]
    assert result.latency_ms == 200
    assert attempts[0].error_code == "busy"


def test_truncation_stops_paid_retry_and_keeps_usage() -> None:
    import pytest

    from app.llm.gateway import GatewayError, ProviderError, ProviderReply, Routing

    routing = routes()
    routing = Routing(tiers={"free": {"items": routing.tiers["free"]["items"][:1]}})
    fake = Fake([ProviderError("incomplete_response", reply=ProviderReply("", 21, 4096, 100))])
    attempts: list[Attempt] = []
    with pytest.raises(GatewayError):
        asyncio.run(
            Gateway(
                routing, {"vertex": fake}, observe_attempt=attempts.append
            ).complete_with_metadata("items", "free", "s", [{"role": "user", "content": "q"}])
        )
    assert len(fake.models) == len(attempts) == 1
    assert (attempts[0].input_tokens, attempts[0].output_tokens, attempts[0].thoughts_tokens) == (
        21,
        4096,
        100,
    )
