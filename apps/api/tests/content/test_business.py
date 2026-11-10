"""Business boundaries exercised offline; no genuine verification is asserted."""

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.content.backends import LearningBackend
from app.content.learning import (
    attempt_review,
    graph_confirmed,
    graph_revision,
    missing_material,
    submitted_feedback,
)
from app.content.pipeline import generate_items
from app.engine import bkt
from app.guardrails.answerability import verify_item
from tests.content.fakes import FakeGateway, topic
from tests.content.learning_loop import replay


def test_common_python_loop_is_explicitly_simulated() -> None:
    report = asyncio.run(replay())
    assert report["mode"] == "simulation" and report["real_verified_count"] == 0
    assert report["database_used"] is False and report["today_rule"] == "next_item.review"


def test_confirmation_is_per_learner_subject_and_revision_not_content_status() -> None:
    _, _, graph, _ = topic()
    approved = {("learner", "python", graph_revision(graph))}

    def confirmation(learner: str, subject: str, revision: str) -> bool:
        return (learner, subject, revision) in approved

    assert graph_confirmed(confirmation, "learner", "python", graph)
    assert not graph_confirmed(None, "learner", "python", graph)
    assert not graph_confirmed(confirmation, "someone-else", "python", graph)
    changed = graph.model_copy(deep=True)
    changed.concepts[0].description_vi += " revised"
    assert not graph_confirmed(confirmation, "learner", "python", changed)


def test_backend_blocks_learning_until_confirmation_without_new_db_fields() -> None:
    _, _, graph, _ = topic()

    class Connection:
        def execute(self, *args: Any) -> "Connection":
            return self

        def fetchone(self) -> tuple[object]:
            return (uuid4(),)

    class Store:
        def _subject(self, *args: Any) -> object:
            return uuid4()

        def graph(self, *args: Any) -> object:
            return graph

    backend = LearningBackend(Store())  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as denied:
        backend._state(Connection(), str(uuid4()), "python")  # type: ignore[arg-type]
    assert denied.value.status_code == 409


def test_outline_only_blocks_question_generation_before_any_model_call() -> None:
    sources, chunks, graph, _ = topic()
    structural = {chunk.chunk_id for chunk in chunks}
    assert set(missing_material(graph, chunks, structural)) == {c.slug for c in graph.concepts}
    fake = FakeGateway()
    with pytest.raises(ValueError, match="instructional material"):
        asyncio.run(generate_items(graph, chunks, sources, fake, structural_chunk_ids=structural))
    assert fake.calls == []


def test_submission_feedback_is_separate_from_hints_and_checks_current_content() -> None:
    sources, chunks, _, items = topic()
    fake = FakeGateway()
    checked = asyncio.run(verify_item(items[0], chunks, fake))
    chosen = next(o.id for o in checked.options if not o.correct)
    assert submitted_feedback(checked, chunks, sources, chosen, submitted=False) is None
    assert submitted_feedback(items[0], chunks, sources, chosen, submitted=True) is None
    feedback = submitted_feedback(checked, chunks, sources, chosen, submitted=True)
    assert feedback and feedback.correct is False and feedback.correct_answer_vi
    assert feedback.misconception_signal_vi and "có thể" in feedback.misconception_signal_vi
    assert feedback.citations and fake.calls[-1]["task"] == "verify_item"
    changed = checked.model_copy(update={"explanation_vi": "changed"})
    assert submitted_feedback(changed, chunks, sources, chosen, submitted=True) is None


def test_wrong_answer_creates_concept_review_without_claiming_mastery() -> None:
    now = datetime(2026, 11, 7, tzinfo=UTC)
    scheduled = attempt_review(None, False, False, now, concept="x", item_id="wrong")
    assert scheduled is not None and scheduled[1].rule == "review.again"
    assert scheduled[1].prior is None and scheduled[1].posterior is None
    assert attempt_review(None, True, False, now, concept="x", item_id="right") is None
    posterior = bkt.update(0.2, True, bkt.DEFAULT_PARAMS["mcq"])
    assert not bkt.is_mastered(posterior)  # One right answer is not a mastered chapter.
