"""Vocabulary routes (specs/vocabulary): a session of due and new words, and answers."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.schemas import DecisionTrace
from app.services.vocabulary import (
    DEFAULT_LIMIT,
    DEFAULT_NEW_PER_DAY,
    MAX_ANSWER_CHARS,
    VocabPractice,
)
from app.vocabulary.items import LearnerItem, WordCard

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class VocabEntry(BaseModel):
    item: LearnerItem
    is_new: bool
    card: WordCard | None  # new words only: the word is taught before it is asked
    due_at: datetime | None


class VocabSession(BaseModel):
    entries: list[VocabEntry]
    due: int
    new_today: int
    new_left_today: int


class VocabAnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: str = Field(min_length=1, max_length=200)
    item_id: str = Field(min_length=1, max_length=200)
    answer: str = Field(max_length=MAX_ANSWER_CHARS)


class VocabAnswerResult(BaseModel):
    correct: bool
    accepted: str
    card: WordCard
    due_at: datetime
    trace: DecisionTrace


def create_router(practice: VocabPractice) -> APIRouter:
    router = APIRouter(prefix="/vocab", tags=["vocabulary"])

    @router.get("/session")
    def session(
        learner_id: str = Query(min_length=1, max_length=200),
        list_slug: str = Query(
            default="core-seed", alias="list", min_length=1, max_length=40, pattern=SLUG_PATTERN
        ),
        limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=50),
        new_limit: int = Query(default=DEFAULT_NEW_PER_DAY, ge=0, le=50),
        max_level: Literal["A1", "A2", "B1", "B2", "C1"] = "C1",
    ) -> VocabSession:
        result = practice.session(
            learner_id, list_slug, limit=limit, new_limit=new_limit, max_level=max_level
        )
        return VocabSession(
            entries=[
                VocabEntry(item=e.item, is_new=e.is_new, card=e.card, due_at=e.due_at)
                for e in result.entries
            ],
            due=result.due,
            new_today=result.new_today,
            new_left_today=result.new_left_today,
        )

    @router.post("/answers")
    def answer(body: VocabAnswerInput) -> VocabAnswerResult:
        result = practice.answer(body.learner_id, body.item_id, body.answer)
        trace = DecisionTrace.model_validate(result.trace.model_dump())
        return VocabAnswerResult(
            correct=result.correct,
            accepted=result.accepted,
            card=result.card,
            due_at=result.due_at,
            trace=trace,
        )

    return router
