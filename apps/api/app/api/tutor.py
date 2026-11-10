"""P3 tutor/RAG HTTP boundary; P4 supplies verified content through the adapter."""

from typing import Literal, Protocol

from fastapi import APIRouter, HTTPException
from pydantic import Field

from app.api.learn import Input, Output


class Citation(Output):
    title: str = Field(min_length=1)
    section: str | None = None
    url: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)


class HintInput(Input):
    learner_id: str = Field(min_length=1, max_length=200)
    item_id: str = Field(min_length=1, max_length=200)
    level: int = Field(ge=1, le=4, strict=True)
    last_answer: int | None = Field(default=None, ge=0, strict=True)
    tier: Literal["free", "pro"]


class AskInput(Input):
    question: str = Field(min_length=1, max_length=1000)
    subject: str = Field(min_length=1, max_length=200)
    tier: Literal["free", "pro"]


class VerifiedText(Output):
    """Internal adapter output. supported is never exposed in the public response."""

    text_vi: str = Field(min_length=1)
    citations: list[Citation]
    supported: bool


class HintResponse(Output):
    hint_vi: str
    citations: list[Citation]


class AskResponse(Output):
    answer_vi: str
    citations: list[Citation]


class TutorBackend(Protocol):
    """hint calls P4's hint ladder/gate; ask uses P1 retrieval plus cited generation.

    supported must be P4's verification result, never the model's self-report.
    """

    async def hint(self, request: HintInput) -> VerifiedText: ...
    async def ask(self, request: AskInput) -> VerifiedText: ...


def create_router(backend: TutorBackend | None = None) -> APIRouter:
    router = APIRouter(tags=["tutor"])

    def service() -> TutorBackend:
        if backend is None:
            raise HTTPException(503, "Dịch vụ trợ giảng chưa được cấu hình.")
        return backend

    def checked(text: VerifiedText) -> VerifiedText:
        if not text.supported or not text.citations or not text.text_vi.strip():
            raise HTTPException(503, "Chưa đủ nguồn để xác minh nội dung trả lời.")
        return text

    @router.post("/tutor/hint", response_model=HintResponse)
    async def hint_route(request: HintInput) -> HintResponse:
        result = checked(await service().hint(request))
        return HintResponse(hint_vi=result.text_vi, citations=result.citations)

    @router.post("/ask", response_model=AskResponse)
    async def ask_route(request: AskInput) -> AskResponse:
        result = checked(await service().ask(request))
        return AskResponse(answer_vi=result.text_vi, citations=result.citations)

    return router
