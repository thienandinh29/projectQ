"""Writing: prompts, essay submission, the learner's essays, and the worker's analysis
(specs/writing/step-2.1.md).

A request never analyses: it stores the essay as `queued`; the worker claims essays with FOR UPDATE
SKIP LOCKED, analyses them (`writing.analysis`) and stores the result.
"""

import logging
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import psycopg
from fastapi import HTTPException
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.curriculum.course import CourseSpec, load_course
from app.curriculum.store import sync_course
from app.engine import bkt
from app.engine.graph import UNSEEN_P_KNOWN
from app.engine.trace import fmt_p
from app.services.backend import learner_uuid, save_trace
from app.services.learning import save_mastery
from app.services.vocabulary import start_of_day
from app.writing.analysis import analyse, load_linking_words, words
from app.writing.error_map import ErrorMap, load_error_map
from app.writing.grammar import GrammarResult, Issue, analyse_grammar, choose_evidence, complexity
from app.writing.languagetool import LanguageToolClient
from app.writing.prompts import Prompt, PromptBank, load_prompts

logger = logging.getLogger(__name__)
CONSENT = (
    "writing-v1"  # the version of the notice the learner accepts (messages/vi.ts, writing.consent)
)
MAX_CHARS = 12_000
NOTE_VI = "Điểm ước lượng và nhận xét chi tiết sẽ có ở các bước sau."
GRAMMAR_OFF_VI = "Chưa kiểm tra ngữ pháp: máy chủ chưa bật LanguageTool (LANGUAGETOOL_URL)."
GRAMMAR_DOWN_VI = (
    "Chưa kiểm tra được ngữ pháp: LanguageTool không phản hồi. Bạn thử gửi lại sau nhé."
)


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


@dataclass
class GrammarStep:
    """What the worker needs for step 2.2, loaded once (spaCy takes about a second)."""

    nlp: Any
    annotator: Any
    error_map: ErrorMap
    course: CourseSpec
    client: LanguageToolClient | None  # None: LANGUAGETOOL_URL not set, grammar is not checked
    draft_learners: frozenset[UUID] = frozenset()
    _ids: tuple[UUID, dict[str, UUID]] | None = None

    def evidence_allowed(self, learner: UUID) -> bool:
        return self.error_map.status == "reviewed" or learner in self.draft_learners

    def ids(self, conn: psycopg.Connection[Any]) -> tuple[UUID, dict[str, UUID]]:
        if self._ids is None:
            concept_ids = sync_course(conn, self.course)
            row = conn.execute(
                "select id from subjects where slug=%s", (self.course.slug,)
            ).fetchone()
            assert row is not None
            self._ids = (row[0], concept_ids)
        return self._ids


def load_grammar_step(
    writing_dir: Path, courses_dir: Path, languagetool_url: str, draft_learners: str = ""
) -> GrammarStep:
    import errant
    import spacy

    nlp = spacy.load("en_core_web_sm")
    error_map = load_error_map(writing_dir / "error-map.yaml")
    course = load_course(courses_dir / f"{error_map.course}.yaml")
    if problems := error_map.problems(course):
        raise ValueError("; ".join(problems))
    return GrammarStep(
        nlp=nlp,
        annotator=errant.load("en", nlp),
        error_map=error_map,
        course=course,
        client=LanguageToolClient(languagetool_url) if languagetool_url else None,
        draft_learners=frozenset(
            learner_uuid(x.strip()) for x in draft_learners.split(",") if x.strip()
        ),
    )


def _analyse(
    text: str, task: int, writing_dir: Path, step: GrammarStep | None
) -> tuple[dict[str, Any], GrammarResult | None]:
    """The essay's result (version 2 with a grammar step) and the grammar analysis; no database."""
    linking = load_linking_words(writing_dir / "linking-words.yaml")
    if step is None:
        result = analyse(text, task, linking).to_json()
        result["note_vi"] = NOTE_VI
        return result, None
    grammar: GrammarResult | None = None
    unavailable: str | None = None
    if step.client is None:
        unavailable = GRAMMAR_OFF_VI
    else:
        try:
            grammar = analyse_grammar(
                text, step.client.matches(text), step.nlp, step.annotator, step.error_map
            )
        except httpx.HTTPError:
            logger.exception("LanguageTool did not answer")
            unavailable = GRAMMAR_DOWN_VI
    sents = (
        list(grammar.sentences)
        if grammar
        else [s.text for s in step.nlp(text).sents if words(s.text)]
    )
    result = analyse(text, task, linking, sentence_texts=sents).to_json()
    result |= {
        "version": 2,
        "note_vi": NOTE_VI,
        "grammar": None
        if grammar is None
        else {"checker": "LanguageTool", "issues": [], "counts": grammar.counts()},
        "grammar_unavailable_vi": unavailable,
        "complexity": asdict(
            grammar.complexity
            if grammar
            else complexity([s for s in step.nlp(text).sents if words(s.text)])
        ),
        "evidence": [],
    }
    return result, grammar


def _apply_evidence(
    conn: psycopg.Connection[Any],
    learner: UUID,
    essay_id: UUID,
    grammar: GrammarResult,
    step: GrammarStep,
    now: datetime,
) -> tuple[list[Issue], list[dict[str, Any]]]:
    """BKT updates for the chosen errors (point 6). Returns the issues, marked, and what moved."""
    chosen = (
        choose_evidence(grammar.issues, step.error_map.max_evidence_per_essay)
        if step.evidence_allowed(learner)
        else []
    )
    if not chosen:
        return list(grammar.issues), []
    subject, ids = step.ids(conn)
    params = step.error_map.params()
    rows = conn.execute(
        "select concept_id, p_known from mastery where learner_id=%s and concept_id = any(%s)",
        (learner, [ids[i.node] for i in chosen if i.node]),
    ).fetchall()
    known = {r[0]: float(r[1]) for r in rows}
    moved = []
    for issue in chosen:
        assert issue.node is not None
        p = known.get(ids[issue.node], UNSEEN_P_KNOWN)
        p_new, trace = bkt.update_traced(
            p, False, params, concept_slug=issue.node, now=now,
            item_id=f"essay:{essay_id}:{issue.id}", misconception=f"writing:{issue.errant_type}",
        )  # fmt: skip
        trace = trace.model_copy(
            update={
                "rule": "writing.error",
                "rule_vi": (
                    f"Bài viết có lỗi: {issue.explain_vi} → khả năng đã nắm vững giảm từ "
                    f"{fmt_p(p)} xuống {fmt_p(p_new)}. Lỗi khi viết tự do được tính nhẹ hơn câu "
                    f"trắc nghiệm (xác suất trượt {fmt_p(params.p_slip)}, "
                    f"đoán đúng {fmt_p(params.p_guess)})."
                ),
            }
        )
        save_mastery(conn, learner, ids[issue.node], p_new)
        save_trace(conn, learner, subject, trace)
        moved.append({"node": issue.node, "errant_type": issue.errant_type, "issue_id": issue.id,
                      "p_before": round(p, 4), "p_after": round(p_new, 4)})  # fmt: skip
    used = {i.id for i in chosen}
    return [replace(i, evidence=i.id in used) for i in grammar.issues], moved


def process_next_essay(
    database_url: str,
    writing_dir: Path,
    step: GrammarStep | None = None,
    *,
    now: datetime | None = None,
) -> bool:
    """Claim and analyse one queued essay; False when there is none (the worker then sleeps).

    Without a grammar step this is step 2.1's analysis. The result and any mastery evidence are
    written in one transaction, so a retried job never counts an essay twice.
    """
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            row = conn.execute(
                "select id,learner_id,prompt_id,text from essays where status='queued' "
                "order by submitted_at,id limit 1 for update skip locked"
            ).fetchone()
            if row is None:
                return False
            conn.execute("update essays set status='analysing' where id=%s", (row[0],))
        essay_id, learner, prompt_id, text = row
        try:
            prompt = load_prompts(writing_dir / "prompts.yaml").get(prompt_id)
            result, grammar = _analyse(text, prompt.task if prompt else 2, writing_dir, step)
            with conn.transaction():
                if grammar is not None and step is not None:
                    issues, moved = _apply_evidence(
                        conn, learner, essay_id, grammar, step, now or datetime.now(UTC)
                    )
                    names = {c.slug: c.name_vi for c in step.course.concepts}
                    result["grammar"]["issues"] = [
                        i.to_json() | {"node_vi": names.get(i.node) if i.node else None}
                        for i in issues
                    ]
                    result["evidence"] = moved
                conn.execute(
                    "update essays set status='done', result=%s, analysed_at=now() where id=%s",
                    (Jsonb(result), essay_id),
                )
        except Exception:
            logger.exception("essay analysis failed", extra={"essay_id": str(essay_id)})
            with conn.transaction():
                conn.execute(
                    "update essays set status='failed', failure_vi=%s, analysed_at=now() "
                    "where id=%s",
                    ("Không phân tích được bài viết. Bạn thử gửi lại sau nhé.", essay_id),
                )
        return True
