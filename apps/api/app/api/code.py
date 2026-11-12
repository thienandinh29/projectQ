"""Code practice routes (specs/code-sandbox/practice-api.md); mounted when RUNNER_URL is set."""

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.schemas import DecisionTrace
from app.services.code_practice import MAX_CODE_BYTES, CodePractice

Slug = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")


class CodeAttemptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: str = Field(min_length=1, max_length=200)
    course: str = Slug
    objective: str = Slug
    code: str = Field(max_length=MAX_CODE_BYTES)
    hints_used: int = Field(default=0, ge=0, le=3, strict=True)


class VisibleTest(BaseModel):
    call: str
    expected: str


class CodeExercise(BaseModel):
    course: str
    objective: str
    concept: str
    function: str
    prompt_vi: str
    starter: str
    visible_tests: list[VisibleTest]
    hidden_tests: int


class TestResult(BaseModel):
    call: str
    passed: bool
    expected: str
    actual: str | None
    error: str | None


class CodeAttemptResult(BaseModel):
    status: str
    score: float = Field(ge=0, le=1)
    correct: bool
    visible: list[TestResult]
    hidden_passed: int
    hidden_total: int
    message_vi: str
    p_known: float = Field(ge=0, le=1)
    mastered: bool
    traces: list[DecisionTrace]


def create_router(practice: CodePractice) -> APIRouter:
    router = APIRouter(prefix="/code", tags=["code"])

    @router.get("/exercise", response_model=CodeExercise)
    def exercise_route(
        learner_id: str = Query(min_length=1, max_length=200),
        course: str = Query(min_length=1, max_length=80),
        objective: str = Query(min_length=1, max_length=80),
    ) -> dict[str, Any]:
        return practice.exercise(learner_id, course, objective)

    @router.post("/attempts", response_model=CodeAttemptResult)
    async def attempt_route(request: CodeAttemptInput) -> CodeAttemptResult:
        done = await practice.attempt(
            request.learner_id, request.course, request.objective, request.code, request.hints_used
        )
        g = done.grade
        return CodeAttemptResult(
            status=g.status,
            score=g.score,
            correct=g.correct,
            visible=[TestResult(**t.__dict__) for t in g.visible],
            hidden_passed=g.hidden_passed,
            hidden_total=g.hidden_total,
            message_vi=g.message_vi,
            p_known=done.p_known,
            mastered=done.mastered,
            traces=[DecisionTrace.model_validate(t.model_dump()) for t in done.traces],
        )

    return router
