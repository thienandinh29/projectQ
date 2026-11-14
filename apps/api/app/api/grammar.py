"""Grammar roadmap routes (specs/level-test): level test, roadmap, milestone tests, practice."""

from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.schemas import DecisionTrace
from app.services.grammar import GrammarService, Step

SLUG = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
Learner = Field(min_length=1, max_length=200)
Course = Field(default="english-ielts", min_length=1, max_length=40, pattern=SLUG)


class QuestionOut(BaseModel):
    item_id: str
    prompt: str
    options: list[str]
    draft: bool  # show "Bản nháp"
    number: int
    total: int | None


class StepOut(BaseModel):
    question: QuestionOut | None
    run_id: str | None
    kind: str | None
    finished: dict[str, Any] | None
    traces: list[DecisionTrace]
    feedback: dict[str, Any] | None = None  # runs only: correct, key, misconception(_vi)


class LevelTestStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: str = Learner
    course: str = Course
    target: Literal["A2", "B1", "B2", "C1"] | None = None


class RunStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: str = Learner
    course: str = Course


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: str = Learner
    item_id: str = Field(min_length=1, max_length=200)
    answer: str = Field(max_length=100)


def _out(step: Step) -> StepOut:
    q = step.question
    return StepOut(
        question=QuestionOut(**q.__dict__) if q else None,
        run_id=step.run_id,
        kind=step.kind,
        finished=step.finished,
        traces=[DecisionTrace.model_validate(t.model_dump()) for t in step.traces],
        feedback=step.feedback,
    )


def create_router(service: GrammarService) -> APIRouter:
    router = APIRouter(tags=["grammar"])

    @router.post("/level-tests")
    def start_level_test(body: LevelTestStart) -> StepOut:
        return _out(service.start_level_test(body.learner_id, body.course, body.target))

    @router.post("/level-tests/{test_id}/answers")
    def answer_level_test(test_id: str, body: AnswerIn) -> StepOut:
        return _out(service.answer_level_test(body.learner_id, test_id, body.item_id, body.answer))

    @router.get("/roadmap")
    def roadmap(
        learner_id: str = Query(min_length=1, max_length=200),
        course: str = Query(default="english-ielts", min_length=1, max_length=40, pattern=SLUG),
    ) -> dict[str, Any]:
        result = service.roadmap(learner_id, course)
        trace = result.pop("learn_next_trace")
        result["learn_next_trace"] = trace.model_dump(mode="json") if trace else None
        return result

    @router.post("/milestones/{slug}/tests")
    def start_milestone_test(slug: str, body: RunStart) -> StepOut:
        return _out(service.start_run(body.learner_id, body.course, "milestone", slug))

    @router.post("/nodes/{slug}/practice")
    def start_practice(slug: str, body: RunStart) -> StepOut:
        return _out(service.start_run(body.learner_id, body.course, "practice", slug))

    @router.post("/grammar-runs/{run_id}/answers")
    def answer_run(run_id: str, body: AnswerIn) -> StepOut:
        return _out(service.answer_run(body.learner_id, run_id, body.item_id, body.answer))

    return router
