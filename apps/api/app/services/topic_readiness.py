"""A saved research graph is a checkpoint until its lesson is published."""

from uuid import UUID

import psycopg
from fastapi import HTTPException

from app.research.failures import failure_report


def require_published_topic(conn: psycopg.Connection, subject: str) -> None:
    if not subject.startswith("topic-"):
        return
    try:
        job_id = UUID(subject.removeprefix("topic-"))
    except ValueError:
        job_id = None
    row = conn.execute(
        "select status,step_vi,graph_ready,items_ready,trail from topic_jobs "
        "where subject_slug=%s or id=%s order by created_at desc limit 1",
        (subject, job_id),
    ).fetchone()
    if row and row[0] == "ready" and row[2] and row[3]:
        return
    if row and row[0] == "failed":
        failure = failure_report(row[1], row[4])
        raise HTTPException(
            409,
            f"Research thất bại [{failure['code']}] ở bước {failure['stage']}: "
            f"{failure['message_vi']} {failure['action_vi']}",
        )
    else:
        raise HTTPException(
            409, "Bản đồ còn là bản nháp; câu hỏi chưa đủ điều kiện học. Hãy xem tiến độ research."
        )
