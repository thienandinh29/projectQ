"""Traced wrappers return exactly what the plain functions return, plus a valid trace."""

from datetime import UTC, datetime, timedelta

import pytest

from app.engine.bkt import DEFAULT_PARAMS, update, update_traced
from app.engine.srs import make_scheduler, new_card, review, review_traced
from app.engine.trace import DecisionTrace, fmt_p

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
MCQ = DEFAULT_PARAMS["mcq"]


@pytest.mark.parametrize("p_known", [0.0, 0.2, 0.5, 0.9, 1.0])
@pytest.mark.parametrize("correct", [True, False])
def test_update_traced_matches_update(p_known: float, correct: bool) -> None:
    new_p, trace = update_traced(p_known, correct, MCQ, concept_slug="loops", now=NOW)
    assert new_p == update(p_known, correct, MCQ)
    assert trace.kind == "bkt_update"
    assert trace.prior == p_known
    assert trace.posterior == new_p
    assert trace.evidence.correct is correct
    assert (trace.evidence.slip, trace.evidence.guess) == (MCQ.p_slip, MCQ.p_guess)
    assert trace.rule_vi
    DecisionTrace.model_validate(trace.model_dump(mode="json"))


def test_update_traced_explains_in_vietnamese() -> None:
    new_p, trace = update_traced(
        0.5, False, MCQ, concept_slug="loops", now=NOW, item_id="l-1", misconception="off-by-one"
    )
    assert trace.rule == "bkt.wrong"
    assert "giảm" in trace.rule_vi and fmt_p(0.5) in trace.rule_vi and fmt_p(new_p) in trace.rule_vi
    assert (trace.evidence.item_id, trace.evidence.misconception) == ("l-1", "off-by-one")


def test_misconception_is_dropped_on_a_correct_answer() -> None:
    _, trace = update_traced(0.5, True, MCQ, concept_slug="loops", now=NOW, misconception="x")
    assert trace.evidence.misconception is None
    assert trace.rule == "bkt.correct"


def test_crossing_the_threshold_is_flagged_as_mastery() -> None:
    _, trace = update_traced(0.9, True, MCQ, concept_slug="loops", now=NOW)
    assert trace.rule == "bkt.correct.mastered"
    assert "nắm vững" in trace.rule_vi


def test_wrong_answer_at_tiny_p_known_still_explained_honestly() -> None:
    new_p, trace = update_traced(0.0, False, MCQ, concept_slug="loops", now=NOW)
    assert new_p > 0.0  # learning transition
    assert "giảm" not in trace.rule_vi


def test_fmt_p_uses_a_decimal_comma() -> None:
    assert fmt_p(0.31) == "0,31"
    assert fmt_p(1) == "1,00"


@pytest.mark.parametrize(
    ("correct", "hints", "rule"),
    [
        (True, 0, "review.good"),
        (True, 2, "review.hard"),
        (False, 0, "review.again"),
    ],
)
def test_review_traced_matches_review(correct: bool, hints: int, rule: str) -> None:
    sched = make_scheduler(fuzz=False)
    state = new_card(NOW).state
    later = NOW + timedelta(days=1)
    result, trace = review_traced(
        state, correct, later, concept_slug="loops", hints_used=hints, scheduler=sched
    )
    assert result == review(state, correct, later, hints_used=hints, scheduler=sched)
    assert trace.kind == "review"
    assert trace.rule == rule
    assert trace.prior is None and trace.posterior is None
    assert f"{result.due_at:%d/%m/%Y}" in trace.rule_vi
    DecisionTrace.model_validate(trace.model_dump(mode="json"))
