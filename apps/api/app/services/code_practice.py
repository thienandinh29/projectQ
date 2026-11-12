"""Code practice: run a learner's code in the sandbox, grade it, update the learner's state.

Spec: specs/code-sandbox/practice-api.md. Learner code never runs in this process: it goes to the
runner (`graders.runner_client`), which returns only the value each test call produced; grading
happens here (`graders.code`). The sandbox run happens outside any database transaction; the
learner's state is then updated in one transaction.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

import psycopg
from fastapi import HTTPException
from psycopg_pool import ConnectionPool

from app.curriculum.course import CourseSpec, Objective, load_course
from app.curriculum.store import code_item_id, sync_course
from app.engine import bkt, srs
from app.engine.graph import UNSEEN_P_KNOWN
from app.engine.trace import DecisionTrace
from app.graders.code import CodeGrade, RunOutcome, grade, run_request
from app.graders.runner_client import RunnerUnavailable
from app.services.backend import learner_uuid, save_trace
from app.services.learning import (
    save_attempt,
    save_mastery,
    save_review,
    unaided_correct_counts,
)

MAX_CODE_BYTES = 20 * 1024
RATE_PER_MINUTE = 30


class Runner(Protocol):
    async def run(self, body: dict[str, object]) -> RunOutcome: ...


@dataclass(frozen=True)
class CodeAttemptResult:
    grade: CodeGrade
    p_known: float
    mastered: bool
    traces: list[DecisionTrace]


class CodePractice:
    def __init__(
        self,
        pool: Callable[[], ConnectionPool],
        runner: Runner,
        courses_dir: Path,
    ) -> None:
        self.pool = pool
        self.runner = runner
        self.courses_dir = courses_dir
        self._synced: set[str] = set()
        self._lock = threading.Lock()

    # --- courses -----------------------------------------------------------------------------

    def course(self, slug: str) -> CourseSpec:
        path = self.courses_dir / f"{slug}.yaml"
        if not slug.replace("-", "").isalnum() or not path.is_file():
            raise HTTPException(404, "Không tìm thấy khóa học.")
        return load_course(path)

    def objective(self, course: CourseSpec, objective_id: str) -> Objective:
        try:
            objective = course.objective(objective_id)
        except KeyError:
            raise HTTPException(404, "Không tìm thấy bài tập.") from None
        if objective.code is None:
            raise HTTPException(404, "Mục tiêu này không phải bài tập lập trình.")
        return objective

    def _ensure_synced(self, conn: psycopg.Connection[Any], course: CourseSpec) -> None:
        with self._lock:
            if course.slug in self._synced:
                return
            sync_course(conn, course)
            self._synced.add(course.slug)

    def _learner(self, conn: psycopg.Connection[Any], learner_id: str) -> UUID:
        learner = learner_uuid(learner_id)
        # Lock the learner row: one state transition at a time per learner.
        if not conn.execute(
            "select id from learners where id=%s for update", (learner,)
        ).fetchone():
            raise HTTPException(404, "Không tìm thấy người học.")
        return learner

    # --- routes' work ------------------------------------------------------------------------

    def exercise(self, learner_id: str, course_slug: str, objective_id: str) -> dict[str, Any]:
        course = self.course(course_slug)
        objective = self.objective(course, objective_id)
        with self.pool().connection() as conn:
            self._learner(conn, learner_id)
        assert objective.code is not None
        return {
            "course": course.slug,
            "objective": objective.id,
            "concept": objective.concept,
            "function": objective.code.function,
            "prompt_vi": objective.code.prompt_vi,
            "starter": objective.code.starter,
            "visible_tests": [
                {"call": t.call, "expected": t.expected} for t in objective.tests if not t.hidden
            ],
            "hidden_tests": sum(t.hidden for t in objective.tests),
        }

    async def attempt(
        self,
        learner_id: str,
        course_slug: str,
        objective_id: str,
        code: str,
        hints_used: int,
    ) -> CodeAttemptResult:
        if len(code.encode()) > MAX_CODE_BYTES:
            raise HTTPException(413, "Mã quá dài (tối đa 20 KB).")
        course = self.course(course_slug)
        objective = self.objective(course, objective_id)
        with self.pool().connection() as conn:
            learner = self._learner(conn, learner_id)
            recent = conn.execute(
                "select count(*) from attempts a join items i on i.id=a.item_id "
                "where a.learner_id=%s and i.kind='code' "
                "and a.created_at > now() - interval '1 minute'",
                (learner,),
            ).fetchone()
            if recent and recent[0] >= RATE_PER_MINUTE:
                raise HTTPException(429, "Bạn gửi quá nhanh; hãy thử lại sau một phút.")
        try:
            outcome = await self.runner.run(run_request(objective, code))  # outside any txn
        except RunnerUnavailable:
            raise HTTPException(503, "Máy chấm mã đang bận hoặc chưa sẵn sàng.") from None
        result = grade(objective, outcome)
        return self._record(learner_id, course, objective, code, hints_used, result)

    def _record(
        self,
        learner_id: str,
        course: CourseSpec,
        objective: Objective,
        code: str,
        hints_used: int,
        result: CodeGrade,
    ) -> CodeAttemptResult:
        now = datetime.now(UTC)
        with self.pool().connection() as conn, conn.transaction():
            learner = self._learner(conn, learner_id)
            self._ensure_synced(conn, course)
            row = conn.execute(
                "select i.id,c.id,c.subject_id,m.p_known from items i "
                "join concepts c on c.id=i.concept_id "
                "left join mastery m on m.concept_id=c.id and m.learner_id=%s "
                "where i.external_id=%s",
                (learner, code_item_id(course, objective)),
            ).fetchone()
            if row is None:
                raise HTTPException(503, "Bài tập chưa được nạp vào cơ sở dữ liệu.")
            item_id, concept_id, subject_id, p_known = row
            prior = float(p_known) if p_known is not None else UNSEEN_P_KNOWN
            attempt_id = save_attempt(
                conn,
                learner_id=learner,
                item_id=item_id,
                answer={
                    "kind": "code",
                    "code": code,
                    "hints_used": hints_used,
                    "phase": "practice",
                    "status": result.status,
                    "score": result.score,
                    "visible": [t.__dict__ for t in result.visible],
                    "hidden_passed": result.hidden_passed,
                    "hidden_total": result.hidden_total,
                },
                correct=result.correct,
            )
            unaided = unaided_correct_counts(conn, learner, subject_id).get(objective.concept, 0)
            p, trace = bkt.update_traced(
                prior,
                result.correct,
                bkt.params_with_help(bkt.DEFAULT_PARAMS["code"], hints_used),
                concept_slug=objective.concept,
                now=now,
                item_id=code_item_id(course, objective),
                unaided_correct=unaided,
            )
            confirmed = bkt.is_confirmed_mastery(p, unaided)
            save_mastery(conn, learner, concept_id, p)
            traces = [trace]
            card = conn.execute(
                "select fsrs_state from review_cards where learner_id=%s and concept_id=%s",
                (learner, concept_id),
            ).fetchone()
            if card or confirmed:
                state = card[0] if card else srs.new_card(now).state
                review, review_trace = srs.review_traced(
                    state,
                    result.correct,
                    now,
                    concept_slug=objective.concept,
                    hints_used=hints_used,
                    item_id=code_item_id(course, objective),
                )
                save_review(conn, learner, concept_id, dict(review.state), review.due_at)
                traces.append(review_trace)
            for t in traces:
                save_trace(conn, learner, subject_id, t, attempt_id)
        return CodeAttemptResult(result, p, confirmed, traces)
