import asyncio
import json
from typing import Any, cast
from uuid import UUID

import pytest

from app.content.gateway import ModelReply, P3Gateway
from app.content.models import ModelIdentity
from app.guardrails.answerability import (
    blind_request,
    invalidate_stale,
    learner_item,
    verify_item,
)
from tests.content.fakes import FakeGateway, topic


def test_blind_request_whitelists_fields_and_omits_key_and_metadata() -> None:
    fake = FakeGateway()
    item = fake.item.model_copy(update={"explanation_vi": "KEY_SECRET_7249"})
    request = blind_request(item, fake.chunks).model_dump(mode="json")
    assert set(request) == {"question", "options", "chunks"}
    assert all(set(o) == {"id", "label"} for o in request["options"])
    assert all(set(c) == {"chunk_id", "content", "evidence_options"} for c in request["chunks"])
    result = asyncio.run(verify_item(item, fake.chunks, fake))
    assert result.status == "verified"  # Fake only; not a real quality assertion.
    call = fake.calls[0]
    serialized = json.dumps({"system": call["system"], "payload": call["payload"]})
    assert "KEY_SECRET_7249" not in serialized
    for field in ("answer_id", "explanation_vi", "misconceptions", "generator", "correct"):
        assert f'"{field}"' not in serialized


@pytest.mark.parametrize("family", ["gpt", None, "unknown", "gemini-2.5-flash"])
def test_same_or_unknown_family_cannot_verify(family: str | None) -> None:
    fake = FakeGateway()
    fake.family = family
    result = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    assert result.status == "needs_review"
    assert learner_item(result, fake.chunks) is None


@pytest.mark.parametrize(
    "change",
    [
        {"supported": False},
        {"selected_option_id": "not-an-option"},
        {"ambiguous": True},
        {"multiple_correct": True},
        {"insufficient_evidence": True},
        {"unique_answer": False},
        {"evidence": []},
        {"unexpected_field": "bad schema"},
    ],
)
def test_failed_verdict_and_invalid_schema_block(change: dict[str, object]) -> None:
    fake = FakeGateway()
    fake.overrides = change
    result = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    assert result.status == "needs_review"


def test_missing_chunk_does_not_even_call_gateway() -> None:
    fake = FakeGateway()
    item = fake.item.model_copy(update={"chunk_ids": [UUID(int=0)]})
    result = asyncio.run(verify_item(item, fake.chunks, fake))
    assert result.status == "needs_review"
    assert fake.calls == []


@pytest.mark.parametrize("error", [TimeoutError("test"), RuntimeError("provider failure")])
def test_gateway_errors_block(error: Exception) -> None:
    fake = FakeGateway()
    fake.error = error
    result = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    assert result.status == "needs_review"
    assert result.verification is not None
    assert "provider failure" not in result.verification.reason


def test_timeout_is_enforced() -> None:
    class Slow(FakeGateway):
        async def generate(self, **kwargs: object) -> ModelReply:
            await asyncio.sleep(1)
            raise AssertionError("should time out")

    fake = Slow()
    result = asyncio.run(verify_item(fake.item, fake.chunks, fake, timeout_seconds=0.001))
    assert result.status == "needs_review"


def test_fabricated_evidence_cannot_verify() -> None:
    fake = FakeGateway()
    fake.overrides = {
        "evidence": [
            {"chunk_id": str(fake.chunks[0].chunk_id), "quote": "This is not in the chunk"}
        ]
    }
    assert asyncio.run(verify_item(fake.item, fake.chunks, fake)).status == "needs_review"


@pytest.mark.parametrize("invalid", [None, "invented-id", "wrong-answer", "same-family"])
def test_source_passage_ids_preserve_exact_math_and_all_answer_gates(invalid: str | None) -> None:
    fake = FakeGateway()
    content = "Derivative formula with raw PDF spacing: f'(x) = lim\n h->0 (f(x+h)-f(x))/h."
    fake.chunks = [fake.chunks[0].model_copy(update={"content": content})]
    fake.overrides = {
        "evidence": [
            {
                "chunk_id": str(fake.chunks[0].chunk_id),
                "passage_id": "invented-id" if invalid == "invented-id" else "source-quote-0",
            }
        ],
    }
    if invalid == "wrong-answer":
        fake.overrides["selected_option_id"] = "choice-999"
    if invalid == "same-family":
        fake.family = fake.item.generator.family
    result = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    assert result.status == ("verified" if invalid is None else "needs_review")
    if invalid is None:
        assert result.verification is not None
        assert result.verification.evidence[0].quote == content
        assert len(fake.calls) == 1


@pytest.mark.parametrize("repairable", [True, False])
def test_quote_correction_is_blind_bounded_and_keeps_exact_evidence_gate(repairable: bool) -> None:
    class Quotes(FakeGateway):
        checks = 0

        async def generate(self, **kwargs: Any) -> ModelReply:
            assert set(kwargs["payload"]) == {"question", "options", "chunks"}
            reply = await super().generate(**kwargs)
            self.checks += 1
            if self.checks == 1 or not repairable:
                cast(dict[str, Any], reply.content)["evidence"][0]["quote"] = (
                    "Table quotation rewritten by model"
                )
            return reply

    fake = Quotes()
    result = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    assert fake.checks == 2
    assert result.status == ("verified" if repairable else "needs_review")


def test_answer_mismatch_does_not_get_a_quote_correction_retry() -> None:
    fake = FakeGateway()
    fake.overrides = {"selected_option_id": "choice-999", "evidence": []}
    result = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    assert result.status == "needs_review" and len(fake.calls) == 1


def test_learner_release_and_content_changes_invalidate_audit() -> None:
    fake = FakeGateway()
    item = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    assert learner_item(fake.item, fake.chunks) is None
    visible = learner_item(item, fake.chunks)
    assert visible is not None
    assert set(visible) == {"id", "kind", "prompt_vi", "options"}
    assert isinstance(visible["options"], list)
    assert all(set(o) == {"label"} for o in visible["options"])
    changed = item.model_copy(update={"prompt_vi": "Changed question"})
    assert learner_item(changed, fake.chunks) is None
    assert invalidate_stale(changed, fake.chunks).status == "needs_review"
    changed_chunks = [fake.chunks[0].model_copy(update={"content": "Changed source"})]
    assert learner_item(item, changed_chunks) is None
    data = item.model_dump(mode="json")
    wrong = next(o for o in data["options"] if not o["correct"])
    wrong["label"] = "A new distractor"
    assert learner_item(type(item).model_validate(data), fake.chunks) is None


def test_same_family_even_with_different_provider_and_name_blocks() -> None:
    fake = FakeGateway()
    fake.item = fake.item.model_copy(
        update={
            "generator": ModelIdentity(
                provider="other-provider",
                model="other-gpt-version",
                family="gpt",
                identity_source="gateway",
            )
        }
    )
    fake.family = "gpt"
    assert asyncio.run(verify_item(fake.item, fake.chunks, fake)).status == "needs_review"


def test_plain_team_gateway_response_has_unknown_identity() -> None:
    def complete(**kwargs: object) -> str:
        return '{"identity": {"family": "claude"}}'

    gateway = P3Gateway(complete)
    fake = FakeGateway()
    # Use a supported generator so the test reaches untrusted response identity handling.
    fake.item = fake.item.model_copy(
        update={
            "generator": ModelIdentity(
                provider="fake-test-provider",
                model="deepseek-test",
                family="deepseek",
                identity_source="gateway",
            )
        }
    )
    result = asyncio.run(verify_item(fake.item, fake.chunks, gateway))
    assert result.status == "needs_review"
    assert result.verification is not None
    assert result.verification.verifier is not None
    assert result.verification.verifier.family is None


def test_model_cannot_use_truthy_strings_instead_of_boolean_verdict() -> None:
    fake = FakeGateway()
    fake.overrides = {"supported": "yes"}
    assert asyncio.run(verify_item(fake.item, fake.chunks, fake)).status == "needs_review"


def test_human_rejection_blocks_even_a_current_model_audit() -> None:
    from datetime import UTC, datetime

    from app.content.models import HumanReview

    fake = FakeGateway()
    item = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    item = item.model_copy(
        update={
            "human_review": HumanReview(
                status="rejected",
                reviewer="test-fixture-only",
                reviewed_at=datetime.now(UTC),
                notes="Synthetic unit-test rejection, not a real human review.",
            )
        }
    )
    assert learner_item(item, fake.chunks) is None


def test_unverified_golden_never_released() -> None:
    _, chunks, _, items = topic()
    assert all(learner_item(i, chunks) is None for i in items)
