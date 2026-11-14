"""Writing routes (specs/writing/step-2.1.md): prompts, essays, results, deletion."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.services.writing import MAX_CHARS, WritingService
from app.writing.prompts import Prompt

Learner = Query(min_length=1, max_length=200)


class EssayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: str = Field(min_length=1, max_length=200)
    prompt_id: str = Field(min_length=1, max_length=40)
    text: str = Field(max_length=MAX_CHARS + 2000)  # NFC and trimming may shorten; checked again
    consent: str = Field(max_length=40)


class CorrectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: str = Field(min_length=1, max_length=200)
    issue_id: int = Field(ge=0, le=10_000)
    sentence: str | None = Field(default=None, max_length=1000)
    show_answer: bool = False


class CorrectionOut(BaseModel):
    accepted: bool
    tries: int
    answer: str | None
    feedback_vi: str


class EssayQueued(BaseModel):
    essay_id: str
    status: str


class EssaySummary(BaseModel):
    id: str
    prompt_id: str
    status: str
    words: int | None
    submitted_at: datetime


class Essay(BaseModel):
    id: str
    prompt: Prompt | None
    text: str
    status: str
    submitted_at: datetime
    result: dict[str, Any] | None
    failure_vi: str | None
    corrections: dict[str, dict[str, Any]] = {}  # issue id -> self-correction state


def create_router(service: WritingService) -> APIRouter:
    router = APIRouter(tags=["writing"])

    @router.get("/writing/prompts")
    def prompts(learner_id: str = Learner) -> list[Prompt]:
        return service.prompts(learner_id)

    @router.post("/essays", status_code=202)
    def submit(body: EssayIn) -> EssayQueued:
        essay_id = service.submit(body.learner_id, body.prompt_id, body.text, body.consent)
        return EssayQueued(essay_id=essay_id, status="queued")

    @router.get("/essays")
    def essays(learner_id: str = Learner) -> list[EssaySummary]:
        return [EssaySummary(**e) for e in service.list(learner_id)]

    @router.get("/essays/{essay_id}")
    def essay(essay_id: str, learner_id: str = Learner) -> Essay:
        return Essay(**service.get(learner_id, essay_id))

    @router.post("/essays/{essay_id}/corrections")
    def correct(essay_id: str, body: CorrectionIn) -> CorrectionOut:
        result = service.correct(
            body.learner_id, essay_id, body.issue_id, body.sentence, show_answer=body.show_answer
        )
        return CorrectionOut(**result)

    @router.delete("/essays/{essay_id}", status_code=204)
    def delete(essay_id: str, learner_id: str = Learner) -> Response:
        service.delete(learner_id, essay_id)
        return Response(status_code=204)

    return router
