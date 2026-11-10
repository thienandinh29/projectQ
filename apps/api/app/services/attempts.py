"""Retry receipts; callers must hold the learner row lock until commit."""

from typing import Any

import psycopg
from fastapi import HTTPException
from psycopg.types.json import Jsonb

from app.api.learn import AttemptInput, AttemptResponse, AttemptUpdate


def replay(conn: psycopg.Connection[Any], request: AttemptInput) -> AttemptResponse | None:
    if request.client_attempt_id is None:
        return None
    row = conn.execute(
        "select request,response from attempt_replays where learner_id=%s and item_id=%s "
        "and client_attempt_id=%s",
        (request.learner_id, request.item_id, request.client_attempt_id),
    ).fetchone()
    if row is None:
        return None
    if row[0] != request.model_dump(mode="json"):
        raise HTTPException(409, "Mã lần trả lời đã được dùng với nội dung khác.")
    return AttemptResponse.model_validate(row[1])


def remember(
    conn: psycopg.Connection[Any], request: AttemptInput, result: AttemptUpdate, *, correct: bool
) -> None:
    if request.client_attempt_id is not None:
        conn.execute(
            "insert into attempt_replays(learner_id,item_id,client_attempt_id,request,response) "
            "values (%s,%s,%s,%s,%s)",
            (
                request.learner_id,
                request.item_id,
                request.client_attempt_id,
                Jsonb(request.model_dump(mode="json")),
                Jsonb({**result.model_dump(mode="json", exclude_none=True), "correct": correct}),
            ),
        )
