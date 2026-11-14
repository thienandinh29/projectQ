"""Writing: prompts, essay submission, the learner's essays, and the worker's analysis
(specs/writing/step-2.1.md).

A request never analyses: it stores the essay as `queued`; the worker claims essays with FOR UPDATE
SKIP LOCKED, analyses them (`writing.analysis`) and stores the result.
"""

import logging
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.services.backend import learner_uuid
from app.services.vocabulary import start_of_day
from app.writing.analysis import analyse, load_linking_words
from app.writing.prompts import Prompt, PromptBank, load_prompts

logger = logging.getLogger(__name__)
CONSENT = (
    "writing-v1"  # the version of the notice the learner accepts (messages/vi.ts, writing.consent)
)
MAX_CHARS = 12_000
NOTE_VI = "Lỗi ngữ pháp, điểm ước lượng và nhận xét chi tiết sẽ có ở các bước sau."


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(404, "Không tìm thấy bài viết.") from None


class WritingService:
    def __init__(
        self,
        pool: Callable[[], ConnectionPool],
        writing_dir: Path,
        *,
        draft_learners: str = "",
        daily_essays: int = 3,
    ) -> None:
        self.pool = pool
        self.writing_dir = writing_dir
        self.daily_essays = daily_essays
        self.draft_learners = {
            learner_uuid(x.strip()) for x in draft_learners.split(",") if x.strip()
        }
        self._bank: PromptBank | None = None

    def bank(self) -> PromptBank:
        if self._bank is None:
            self._bank = load_prompts(self.writing_dir / "prompts.yaml")
        return self._bank

    def _learner(self, conn: psycopg.Connection[Any], learner_id: str) -> UUID:
        learner = learner_uuid(learner_id)
        if not conn.execute(
            "select id from learners where id=%s for update", (learner,)
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy người học.")
        return learner

    def _visible(self, prompt: Prompt, learner: UUID) -> bool:
        return prompt.status == "reviewed" or learner in self.draft_learners

    def prompts(self, learner_id: str) -> list[Prompt]:
        with self.pool().connection() as conn:
            learner = self._learner(conn, learner_id)
        return [p for p in self.bank().prompts if self._visible(p, learner)]

    def submit(
        self,
        learner_id: str,
        prompt_id: str,
        text: str,
        consent: str,
        *,
        now: datetime | None = None,
    ) -> str:
        if consent != CONSENT:
            raise HTTPException(422, "Cần đồng ý với thông báo trước khi gửi bài.")
        text = unicodedata.normalize("NFC", text).strip()
        if not text or len(text) > MAX_CHARS:
            raise HTTPException(422, f"Bài viết cần từ 1 đến {MAX_CHARS} ký tự.")
        now = now or datetime.now(UTC)
        with self.pool().connection() as conn, conn.transaction():
            learner = self._learner(conn, learner_id)
            prompt = self.bank().get(prompt_id)
            if prompt is None or not self._visible(prompt, learner):
                raise HTTPException(404, "Không tìm thấy đề bài.")
            today = conn.execute(
                "select count(*) from essays where learner_id=%s and submitted_at >= %s",
                (learner, start_of_day(now)),
            ).fetchone()
            assert today is not None
            if today[0] >= self.daily_essays:
                raise HTTPException(
                    429, f"Hôm nay bạn đã gửi {self.daily_essays} bài. Hẹn bạn ngày mai nhé."
                )
            row = conn.execute(
                "insert into essays(learner_id,prompt_id,text,consent,submitted_at) "
                "values (%s,%s,%s,%s,%s) returning id",
                (learner, prompt_id, text, consent, now),
            ).fetchone()
        assert row is not None
        return str(row[0])

    def list(self, learner_id: str) -> list[dict[str, Any]]:
        with self.pool().connection() as conn:
            learner = self._learner(conn, learner_id)
            rows = conn.execute(
                "select id,prompt_id,status,result->>'words',submitted_at from essays "
                "where learner_id=%s order by submitted_at desc",
                (learner,),
            ).fetchall()
        return [
            {"id": str(r[0]), "prompt_id": r[1], "status": r[2],
             "words": int(r[3]) if r[3] is not None else None, "submitted_at": r[4]}
            for r in rows
        ]  # fmt: skip

    def get(self, learner_id: str, essay_id: str) -> dict[str, Any]:
        with self.pool().connection() as conn:
            learner = self._learner(conn, learner_id)
            row = conn.execute(
                "select id,prompt_id,text,status,submitted_at,result,failure_vi from essays "
                "where id=%s and learner_id=%s",
                (_uuid(essay_id), learner),
            ).fetchone()
        if row is None:
            raise HTTPException(404, "Không tìm thấy bài viết.")
        prompt = self.bank().get(row[1])
        return {
            "id": str(row[0]),
            "prompt": prompt.model_dump() if prompt else None,
            "text": row[2],
            "status": row[3],
            "submitted_at": row[4],
            "result": row[5],
            "failure_vi": row[6],
        }

    def delete(self, learner_id: str, essay_id: str) -> None:
        with self.pool().connection() as conn, conn.transaction():
            learner = self._learner(conn, learner_id)
            gone = conn.execute(
                "delete from essays where id=%s and learner_id=%s returning id",
                (_uuid(essay_id), learner),
            ).fetchone()
        if gone is None:
            raise HTTPException(404, "Không tìm thấy bài viết.")


def process_next_essay(database_url: str, writing_dir: Path) -> bool:
    """Claim and analyse one queued essay; False when there is none (the worker then sleeps)."""
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            row = conn.execute(
                "select id,prompt_id,text from essays where status='queued' "
                "order by submitted_at,id limit 1 for update skip locked"
            ).fetchone()
            if row is None:
                return False
            conn.execute("update essays set status='analysing' where id=%s", (row[0],))
        essay_id, prompt_id, text = row
        try:
            prompt = load_prompts(writing_dir / "prompts.yaml").get(prompt_id)
            linking = load_linking_words(writing_dir / "linking-words.yaml")
            result = analyse(text, prompt.task if prompt else 2, linking).to_json()
            result["note_vi"] = NOTE_VI
            conn.execute(
                "update essays set status='done', result=%s, analysed_at=now() where id=%s",
                (Jsonb(result), essay_id),
            )
        except Exception:
            logger.exception("essay analysis failed", extra={"essay_id": str(essay_id)})
            conn.execute(
                "update essays set status='failed', failure_vi=%s, analysed_at=now() where id=%s",
                ("Không phân tích được bài viết. Bạn thử gửi lại sau nhé.", essay_id),
            )
        conn.commit()
        return True
