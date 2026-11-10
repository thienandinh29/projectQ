"""Spaced repetition for concept review, wrapping the `fsrs` library (FSRS-6).

Cards are per learner x concept, stored as JSON in review_cards.fsrs_state.
FSRS's default 1-10 minute learning steps are for flashcards; a concept review is a
short quiz, so we skip them and schedule in days from the first review.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from fsrs import Card, Rating, Scheduler
from fsrs.card import CardDict

from app.engine.trace import DecisionTrace, Evidence

DESIRED_RETENTION = 0.9


@dataclass(frozen=True)
class ReviewResult:
    state: CardDict
    due_at: datetime


def make_scheduler(*, fuzz: bool = False) -> Scheduler:
    # Deterministic by default, including service retries/replays. Callers may explicitly
    # opt into randomized date spreading with fuzz=True outside the deterministic flow.
    return Scheduler(
        desired_retention=DESIRED_RETENTION,
        learning_steps=(),
        relearning_steps=(),
        enable_fuzzing=fuzz,
    )


def rating_for(correct: bool, hints_used: int = 0) -> Rating:
    """Map a graded review to an FSRS rating.

    No Easy: Sena rewards understanding, not speed, so a clean correct answer is Good.
    """
    if hints_used < 0:
        raise ValueError("hints_used must be >= 0")
    if not correct:
        return Rating.Again
    return Rating.Hard if hints_used > 0 else Rating.Good


def _require_aware(now: datetime) -> datetime:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(UTC)


def new_card(now: datetime) -> ReviewResult:
    """A card for a newly mastered concept, due immediately."""
    # card_id is unused (the DB keys cards by learner + concept); fix it for deterministic state.
    card = Card(card_id=0, due=_require_aware(now))
    return ReviewResult(state=card.to_dict(), due_at=card.due)


def review(
    state: CardDict,
    correct: bool,
    now: datetime,
    *,
    hints_used: int = 0,
    scheduler: Scheduler | None = None,
) -> ReviewResult:
    scheduler = scheduler or make_scheduler()
    card = Card.from_dict(state)
    card, _log = scheduler.review_card(card, rating_for(correct, hints_used), _require_aware(now))
    return ReviewResult(state=card.to_dict(), due_at=card.due)


def is_due(due_at: datetime, now: datetime) -> bool:
    return _require_aware(due_at) <= _require_aware(now)


_RATING_VI = {
    Rating.Again: "trả lời sai nên cần ôn lại sớm",
    Rating.Hard: "đúng nhưng cần gợi ý nên ôn lại sớm hơn",
    Rating.Good: "trả lời đúng không cần gợi ý",
}


def review_traced(
    state: CardDict,
    correct: bool,
    now: datetime,
    *,
    concept_slug: str,
    hints_used: int = 0,
    item_id: str | None = None,
    scheduler: Scheduler | None = None,
) -> tuple[ReviewResult, DecisionTrace]:
    """`review` plus its trace. The trace is about scheduling, so prior/posterior stay None."""
    result = review(state, correct, now, hints_used=hints_used, scheduler=scheduler)
    rating = rating_for(correct, hints_used)
    days = (result.due_at - _require_aware(now)).total_seconds() / 86400
    when = "hôm nay" if days < 1 else f"sau {round(days)} ngày"
    trace = DecisionTrace(
        kind="review",
        concept_slug=concept_slug,
        at=now,
        evidence=Evidence(item_id=item_id, correct=correct),
        rule=f"review.{rating.name.lower()}",
        rule_vi=(
            f"Ôn lại {when} ({result.due_at:%d/%m/%Y}): {_RATING_VI[rating]}; "
            f"lịch ôn giữ khả năng nhớ khoảng {round(DESIRED_RETENTION * 100)}%"
        ),
    )
    return result, trace
