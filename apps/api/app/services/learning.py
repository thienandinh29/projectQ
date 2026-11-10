"""Persistence only; callers supply engine results inside their own transaction."""

from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb


def save_attempt(
    conn: psycopg.Connection[Any],
    *,
    learner_id: UUID,
    item_id: UUID,
    answer: dict[str, Any],
    correct: bool,
    misconception_id: UUID | None = None,
) -> UUID:
    row = conn.execute(
        "insert into attempts(learner_id,item_id,answer,is_correct,misconception_id) "
        "values (%s,%s,%s,%s,%s) returning id",
        (learner_id, item_id, Jsonb(answer), correct, misconception_id),
    ).fetchone()
    assert row is not None
    return row[0]  # type: ignore[no-any-return]


def save_mastery(
    conn: psycopg.Connection[Any], learner_id: UUID, concept_id: UUID, p_known: float
) -> None:
    if not 0 <= p_known <= 1:
        raise ValueError("p_known must be in [0, 1]")
    conn.execute(
        "insert into mastery(learner_id,concept_id,p_known) values (%s,%s,%s) "
        "on conflict(learner_id,concept_id) do update "
        "set p_known=excluded.p_known, updated_at=now()",
        (learner_id, concept_id, p_known),
    )


def save_review(
    conn: psycopg.Connection[Any],
    learner_id: UUID,
    concept_id: UUID,
    state: dict[str, Any],
    due_at: datetime,
) -> None:
    if due_at.tzinfo is None:
        raise ValueError("due_at must be timezone-aware")
    conn.execute(
        "insert into review_cards(learner_id,concept_id,fsrs_state,due_at) values (%s,%s,%s,%s) "
        "on conflict(learner_id,concept_id) do update "
        "set fsrs_state=excluded.fsrs_state,due_at=excluded.due_at",
        (learner_id, concept_id, Jsonb(state), due_at),
    )
