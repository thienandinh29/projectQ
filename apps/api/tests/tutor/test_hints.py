import asyncio
from typing import Any, cast

import pytest

from app.content.gateway import ModelReply
from app.content.models import Item, ModelIdentity
from app.guardrails.answerability import verify_item
from app.tutor.hints import HintDraft, hint, release_hint, verify_hint
from tests.content.fakes import FakeGateway, topic


def prepared() -> tuple[FakeGateway, Item]:
    fake = FakeGateway()
    item = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    return fake, item


def test_unverified_question_never_gets_hint() -> None:
    fake = FakeGateway()
    sources, _, _, _ = topic()
    assert (
        asyncio.run(hint(fake.item, 1, None, fake.chunks, "pro", gateway=fake, sources=sources))
        is None
    )
    assert fake.calls == []


def test_verified_hint_payload_has_citations_and_no_internal_metadata() -> None:
    fake, item = prepared()
    sources, _, _, _ = topic()
    result = asyncio.run(
        hint(
            item,
            2,
            "wrong-choice",
            fake.chunks,
            "pro",
            gateway=fake,
            sources=sources,
            history=["Em đang phân vân."],
        )
    )
    assert result is not None
    assert set(result.model_dump()) == {"hint_vi", "citations"}
    assert result.citations[0].chunk_id == item.chunk_ids[0]
    assert result.citations[0].source_id in item.source_ids


@pytest.mark.parametrize(
    "field",
    [
        "supported",
        "no_answer_leak",
        "no_elimination",
        "relevant_to_history",
        "clear_vietnamese",
        "level_appropriate",
    ],
)
def test_bad_hint_rubric_is_never_released(field: str) -> None:
    fake, item = prepared()
    fake.overrides = {field: False}
    sources, _, _, _ = topic()
    assert (
        asyncio.run(hint(item, 1, None, fake.chunks, "pro", gateway=fake, sources=sources)) is None
    )


def test_literal_answer_blocks_before_model_call() -> None:
    fake, item = prepared()
    draft = HintDraft(hint_vi="Đáp án là 2.", chunk_ids=item.chunk_ids)
    before = len(fake.calls)
    generator = ModelIdentity(
        provider="fake", model="fake", family="gemini", identity_source="gateway"
    )
    attempt = asyncio.run(verify_hint(item, draft, fake.chunks, generator, fake, level=1))
    assert attempt.verification.status == "needs_review"
    assert len(fake.calls) == before


@pytest.mark.parametrize("invalid", [None, "invented-id", "answer-leak"])
def test_hint_passage_ids_keep_exact_source_and_answer_disclosure_gates(
    invalid: str | None,
) -> None:
    fake, item = prepared()
    fake.overrides = {
        "evidence": [
            {
                "chunk_id": str(item.chunk_ids[0]),
                "passage_id": "invented-id" if invalid == "invented-id" else "source-quote-0",
            }
        ],
        "no_answer_leak": invalid != "answer-leak",
    }
    draft = HintDraft(hint_vi="Check the source rule before calculating.", chunk_ids=item.chunk_ids)
    attempt = asyncio.run(verify_hint(item, draft, fake.chunks, item.generator, fake, level=1))
    assert attempt.verification.status == ("verified" if invalid is None else "needs_review")
    if invalid is None:
        assert attempt.verification.evidence[0].quote == fake.chunks[0].content


def test_hint_same_family_and_changed_history_block_release() -> None:
    fake, item = prepared()
    sources, _, _, _ = topic()
    generator = ModelIdentity(
        provider="fake", model="fake", family="claude", identity_source="gateway"
    )
    draft = HintDraft(hint_vi="Hãy xác định phép toán trong đề.", chunk_ids=item.chunk_ids)
    failed = asyncio.run(verify_hint(item, draft, fake.chunks, generator, fake, level=1))
    assert failed.verification.status == "needs_review"
    generator = generator.model_copy(update={"family": "gemini"})
    attempt = asyncio.run(
        verify_hint(item, draft, fake.chunks, generator, fake, level=1, history=["Gợi ý trước"])
    )
    assert attempt.verification.status == "verified"
    assert release_hint(attempt, item, fake.chunks, sources, level=1, history=[]) is None
    assert (
        release_hint(attempt, item, fake.chunks, sources, level=2, history=["Gợi ý trước"]) is None
    )


@pytest.mark.parametrize("repairable", [True, False])
def test_hint_quote_correction_is_bounded_and_still_requires_exact_evidence(
    repairable: bool,
) -> None:
    fake, item = prepared()

    class Quotes(FakeGateway):
        checks = 0

        async def generate(self, **kwargs: Any) -> ModelReply:
            reply = await super().generate(**kwargs)
            if kwargs["task"] == "verify_hint":
                self.checks += 1
                if self.checks == 1 or not repairable:
                    cast(dict[str, Any], reply.content)["evidence"][0]["quote"] = (
                        "Invented quotation, absent from source"
                    )
                if self.checks == 2:
                    assert "evidence_feedback" in kwargs["payload"]
            return reply

    models = Quotes()
    models.item, models.chunks = item, fake.chunks
    draft = HintDraft(hint_vi="Hãy xác định phép toán trong đề.", chunk_ids=item.chunk_ids)
    result = asyncio.run(verify_hint(item, draft, fake.chunks, item.generator, models, level=1))
    assert models.checks == 2
    assert result.verification.status == ("verified" if repairable else "needs_review")


def test_hint_negative_rubric_does_not_trigger_quote_retry() -> None:
    fake, item = prepared()
    fake.overrides = {"no_answer_leak": False}
    before = len(fake.calls)
    draft = HintDraft(hint_vi="Hãy xác định phép toán trong đề.", chunk_ids=item.chunk_ids)
    result = asyncio.run(verify_hint(item, draft, fake.chunks, item.generator, fake, level=1))
    assert result.verification.status == "needs_review"
    assert len(fake.calls) == before + 1
