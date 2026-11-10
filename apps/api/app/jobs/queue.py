"""Committed queue claims and durable topic snapshots, independent of P3."""

from dataclasses import asdict
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.research.failures import failure_report
from app.research.pipeline import Progress

FIELDS = "status, step_vi, progress, subject_slug, graph_ready, items_ready, sources, trail"


def enqueue(
    conn: psycopg.Connection[Any],
    goal_vi: str,
    tier: str,
    *,
    fixture: bool = False,
    mode: str = "quick",
    upload_id: UUID | None = None,
) -> UUID:
    if not goal_vi.strip() and upload_id is None:
        raise ValueError("goal_vi must not be blank")
    row = conn.execute(
        "insert into topic_jobs(goal_vi,tier,fixture,mode,upload_id) "
        "values (%s,%s,%s,%s,%s) returning id",
        (goal_vi, tier, fixture, mode, upload_id),
    ).fetchone()
    assert row is not None
    return row[0]  # type: ignore[no-any-return]


def claim(conn: psycopg.Connection[Any]) -> dict[str, Any] | None:
    """Caller commits before executing long work; competing workers skip locked rows."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "update topic_jobs set status='researching', step_vi='Đang xử lý', updated_at=now() "
            "where id=(select id from topic_jobs where status='queued' "
            "order by created_at,id for update skip locked limit 1) returning *"
        )
        return cur.fetchone()


def snapshot(conn: psycopg.Connection[Any], topic_id: UUID) -> dict[str, Any] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"select {FIELDS} from topic_jobs where id=%s", (topic_id,))
        state = cur.fetchone()
        if state is not None:
            state["progress"] /= 100
            if state["status"] == "failed":
                state["failure"] = failure_report(state["step_vi"], state["trail"])
        return state


def save_progress(conn: psycopg.Connection[Any], topic_id: UUID, progress: Progress) -> None:
    conn.execute(
        "update topic_jobs set status=%s,step_vi=%s,progress=%s,graph_ready=%s,"
        "items_ready=%s,subject_slug=%s,dropped_items=%s,sources=%s,updated_at=now() "
        "where id=%s and status not in ('ready','failed')",
        (
            progress.status,
            progress.step_vi,
            progress.progress,
            progress.graph_ready,
            progress.items_ready,
            progress.subject_slug,
            progress.dropped_items,
            Jsonb([asdict(source) for source in progress.sources]),
            topic_id,
        ),
    )


def append_trail(conn: psycopg.Connection[Any], topic_id: UUID, event: dict[str, str]) -> None:
    conn.execute(
        "update topic_jobs set trail=trail || %s,updated_at=now() "
        "where id=%s and status not in ('ready','failed')",
        (Jsonb([event]), topic_id),
    )


def finish(conn: psycopg.Connection[Any], topic_id: UUID, *, fixture: bool) -> None:
    conn.execute(
        "update topic_jobs set status=%s, step_vi=%s, progress=%s, updated_at=now() "
        "where id=%s and status='researching'",
        (
            "ready" if fixture else "failed",
            "Dữ liệu mô phỏng; chưa có nội dung học"
            if fixture
            else "Chế độ mô phỏng chưa được bật.",
            100 if fixture else 0,
            topic_id,
        ),
    )
