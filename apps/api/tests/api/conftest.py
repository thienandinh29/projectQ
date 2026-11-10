"""Offline HTTP harness only. These fixtures are never imported by application code."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import learn, topics, tutor
from app.graders.mcq import Grade, Item, Option
from app.uploads.reader import Document, Page


class FakeBackend:
    def __init__(self) -> None:
        self.item: Item | None = Item(
            id="q1",
            prompt_vi="Oxy sinh ra từ đâu?",
            difficulty=0.4,
            source="https://books.example/chapter",
            chunk_ids=["chunk-1"],
            status="verified",
            options=[
                Option(label="Nước", correct=True),
                Option(label="CO2", correct=False, misconception="oxygen-from-co2"),
            ],
        )
        self.done = False
        self.attempts: list[tuple[learn.AttemptInput, Grade]] = []
        self.jobs: list[topics.TopicInput] = []
        self.uploads: list[tuple[Document, bytes | None, str | None]] = []
        self.text = tutor.VerifiedText(
            text_vi="Hãy tìm chất được phân tách ở pha sáng.",
            supported=True,
            citations=[
                tutor.Citation(
                    title="Giáo trình", section="Pha sáng", url="https://books.example/chapter"
                )
            ],
        )

    def trace(self) -> learn.DecisionTrace:
        return learn.DecisionTrace(
            kind="bkt_update",
            concept_slug="photosynthesis",
            at=datetime.now(UTC),
            prior=0.2,
            posterior=0.4,
            evidence=learn.Evidence(item_id="q1", correct=False),
            rule="test fixture",
            rule_vi="Dữ liệu giả cho kiểm thử.",
            alternatives=[],
        )

    async def graph(self, learner_id: str, subject: str) -> learn.GraphResponse:
        return learn.GraphResponse(
            nodes=[
                learn.GraphNode(
                    slug="photosynthesis", name_vi="Quang hợp", p_known=0.2, mastered=False
                )
            ],
            edges=[learn.GraphEdge.model_validate({"from": "cells", "to": "photosynthesis"})],
        )

    async def placement(self, request: learn.LearnerSubject) -> learn.PlacementSelection:
        return learn.PlacementSelection(
            item=None if self.done else self.item,
            done=self.done,
            gap_slug="photosynthesis" if self.done else None,
            trace=self.trace(),
        )

    async def next_item(self, learner_id: str, subject: str) -> learn.NextSelection | None:
        if self.item is None:
            return None
        return learn.NextSelection(item=self.item, reason_vi="Ôn lại kiến thức nền tảng.")

    async def get_item(self, item_id: str) -> Item | None:
        return self.item if self.item and self.item.id == item_id else None

    async def apply_attempt(
        self,
        request: learn.AttemptInput,
        item: Item,
        result: Grade,
    ) -> learn.AttemptUpdate:
        self.attempts.append((request, result))
        trace = self.trace()
        trace = trace.model_copy(
            update={"evidence": trace.evidence.model_copy(update={"correct": result.correct})}
        )
        return learn.AttemptUpdate(
            p_known=0.4,
            mastered=False,
            traces=[trace],
            misconception_vi="Nhầm nguồn tạo oxy.",
            remediation=learn.Remediation(
                concept_slug="water", reason_vi="Ôn lại vai trò của nước."
            ),
        )

    async def reviews_due(self, learner_id: str) -> learn.ReviewsResponse:
        return learn.ReviewsResponse(
            cards=[learn.ReviewCard(concept_slug="photosynthesis", due_at=datetime.now(UTC))]
        )

    async def exam_plan(self, request: learn.ExamInput) -> learn.ExamResponse:
        return learn.ExamResponse(
            days=[
                learn.ExamDay(date=request.exam_date, concept_slugs=["photosynthesis"], minutes=20)
            ]
        )

    async def hint(self, request: tutor.HintInput) -> tutor.VerifiedText:
        return self.text

    async def ask(self, request: tutor.AskInput) -> tutor.VerifiedText:
        return self.text

    async def enqueue(self, request: topics.TopicInput) -> topics.TopicResponse:
        self.jobs.append(request)
        return topics.TopicResponse(topic_id="topic-1", cached=False)

    async def persist_upload(
        self,
        document: Document,
        body: bytes | None,
        filename: str | None,
        *,
        demo_consent: bool = False,
    ) -> str:
        assert demo_consent
        self.uploads.append((document, body, filename))
        return f"upload-{len(self.uploads)}"


async def fake_link(url: str) -> Document:
    return Document(url, (Page(1, "Kiến thức nền tảng từ tài liệu."),), True)


@dataclass
class Harness:
    client: TestClient
    backend: FakeBackend


@pytest.fixture
def harness() -> Iterator[Harness]:
    backend = FakeBackend()
    app = FastAPI()
    app.include_router(learn.create_router(backend))
    app.include_router(
        topics.create_router(backend, link_reader=fake_link, demo_uploads_enabled=True)
    )
    app.include_router(tutor.create_router(backend))
    with TestClient(app, headers={"X-Demo-Upload-Consent": "demo-v1"}) as client:
        yield Harness(client, backend)
