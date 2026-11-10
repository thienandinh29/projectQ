"""Explicit graph review/confirmation HTTP boundary; never grants approval on GET."""

import asyncio
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.schemas import KnowledgeGraph
from app.services.graph_confirmation import GraphConfirmations
from app.services.learner_sessions import COOKIE_NAME, LearnerSessions


class ConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    subject: str = Field(min_length=1, max_length=80)
    graph_revision: str = Field(pattern=r"^[a-f0-9]{64}$")


class GraphReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: UUID
    subject: str
    graph_revision: str
    graph: KnowledgeGraph
    confirmed: bool


class GraphConfirmed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: UUID
    subject: str
    graph_revision: str
    confirmed: Literal[True] = True


def create_router() -> APIRouter:
    router = APIRouter(tags=["graph-confirmation"])

    def service(request: Request) -> GraphConfirmations:
        backend = getattr(request.app.state, "graph_confirmations", None)
        if not isinstance(backend, GraphConfirmations):
            raise HTTPException(503, "Chưa cấu hình dịch vụ xác nhận bản đồ.")
        return backend

    async def learner(request: Request) -> UUID:
        sessions = getattr(request.app.state, "learner_sessions", None)
        if not isinstance(sessions, LearnerSessions):
            raise HTTPException(503, "Chưa cấu hình phiên người học.")
        try:
            identity = await asyncio.to_thread(sessions.resolve, request.cookies.get(COOKIE_NAME))
        except psycopg.Error:
            raise HTTPException(503, "Chưa thể kiểm tra phiên người học.") from None
        if identity is None:
            raise HTTPException(401, "Cần tạo phiên người học trước khi xác nhận bản đồ.")
        return identity

    @router.get("/graph/review", response_model=GraphReview)
    async def review(
        request: Request, subject: str = Query(min_length=1, max_length=80)
    ) -> GraphReview:
        backend = service(request)
        identity = await learner(request)
        try:
            graph, revision = await asyncio.to_thread(backend.snapshot, str(identity), subject)
            confirmed = await asyncio.to_thread(backend, str(identity), subject, revision)
        except psycopg.Error:
            raise HTTPException(503, "Chưa thể đọc trạng thái xác nhận bản đồ.") from None
        return GraphReview(
            learner_id=identity,
            subject=subject,
            graph_revision=revision,
            graph=KnowledgeGraph.model_validate(graph.team_payload()),
            confirmed=confirmed,
        )

    @router.post("/graph/confirm", response_model=GraphConfirmed)
    async def confirm(body: ConfirmationInput, request: Request) -> GraphConfirmed:
        backend = service(request)
        identity = await learner(request)
        try:
            await asyncio.to_thread(
                backend.confirm, str(identity), body.subject, body.graph_revision
            )
        except psycopg.Error:
            raise HTTPException(503, "Chưa thể lưu xác nhận bản đồ.") from None
        return GraphConfirmed(
            learner_id=identity, subject=body.subject, graph_revision=body.graph_revision
        )

    return router
