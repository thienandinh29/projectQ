import asyncio
import json
import logging
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.responses import Response

from app.api import graph_confirmation, learn, topics, tutor
from app.config import Settings, get_settings
from app.db import create_pool, ping
from app.engine.placer import make_placer
from app.jobs.queue import snapshot
from app.observability import configure_logging
from app.schemas import CachedTopics, TopicState
from app.services.backend import LearningService
from app.services.graph_confirmation import GraphConfirmations
from app.services.learner_sessions import COOKIE_NAME, SESSION_SECONDS, LearnerSessions
from app.services.topics import SupabaseStorage, TopicsService

if TYPE_CHECKING:
    from app.content.gateway import Gateway
    from app.content.learning import GraphConfirmation
    from app.content.repository import Repository

logger = logging.getLogger(__name__)
HEARTBEAT_SECONDS = 15


class LearnerInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=80, pattern=r"\S")


class Health(BaseModel):
    status: str
    db: str


def create_app(
    settings: Settings | None = None,
    *,
    learning_backend: learn.LearningBackend | None = None,
    topics_backend: topics.TopicsBackend | None = None,
    tutor_backend: tutor.TutorBackend | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not settings.api_key.strip():
            if not settings.allow_unauthenticated_local_dev:
                raise RuntimeError(
                    "API_KEY is required; unauthenticated local development must be explicit"
                )
            logger.warning("API authentication disabled for explicit local development")
        settings.export_worker_environment()
        app.state.pool = create_pool(settings.database_url)
        try:
            yield
        finally:
            app.state.pool.close()

    app = FastAPI(title="NodeTrail API", lifespan=lifespan)
    app.include_router(
        learn.create_router(
            learning_backend
            or LearningService(
                lambda: app.state.pool, placer=make_placer(settings.placement_strategy)
            )
        )
    )
    storage = (
        SupabaseStorage(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
            settings.upload_bucket,
        )
        if settings.supabase_url and settings.supabase_service_role_key.get_secret_value()
        else None
    )
    app.include_router(
        topics.create_router(
            topics_backend or TopicsService(lambda: app.state.pool, storage),
            demo_uploads_enabled=settings.demo_uploads_enabled,
        )
    )
    app.include_router(tutor.create_router(tutor_backend))
    if settings.runner_url:
        from app.api import code as code_routes
        from app.graders.runner_client import RunnerClient
        from app.services.code_practice import CodePractice

        runner = RunnerClient(settings.runner_url, settings.runner_token.get_secret_value())
        practice = CodePractice(lambda: app.state.pool, runner, settings.courses_dir)
        app.include_router(code_routes.create_router(practice))
    from app.api import vocab as vocab_routes
    from app.services.vocabulary import VocabPractice

    app.include_router(
        vocab_routes.create_router(VocabPractice(lambda: app.state.pool, settings.vocab_dir))
    )
    from app.api import grammar as grammar_routes
    from app.services.grammar import GrammarService

    grammar = GrammarService(
        lambda: app.state.pool,
        settings.courses_dir,
        settings.items_dir,
        settings.vocab_dir,
        settings.draft_item_learners,
    )
    app.include_router(grammar_routes.create_router(grammar))
    app.include_router(graph_confirmation.create_router())

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid4())
        started = time.monotonic()
        response: Response
        if (
            settings.api_key
            and request.url.path != "/health"
            and not secrets.compare_digest(
                request.headers.get("x-api-key", "").encode(), settings.api_key.encode()
            )
        ):
            response = JSONResponse({"detail": "API key không hợp lệ"}, status_code=401)
        else:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("request failed", extra={"request_id": request_id})
                response = JSONResponse(
                    {"detail": "Không thể xử lý yêu cầu", "request_id": request_id}, status_code=503
                )
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "topic_id": request.path_params.get("topic_id"),
                "tier": getattr(request.state, "tier", None),
                "status": response.status_code,
                "latency_ms": round((time.monotonic() - started) * 1000),
            },
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type", "Last-Event-ID", "X-Demo-Upload-Consent"],
        expose_headers=["X-Request-ID", "X-Data-Fixture"],
    )

    @app.post("/learners")
    def create_learner(body: LearnerInput, request: Request, response: Response) -> dict[str, UUID]:
        with request.app.state.pool.connection() as conn:
            row = conn.execute(
                "insert into learners(display_name) values (%s) returning id",
                (body.display_name.strip(),),
            ).fetchone()
            sessions = getattr(request.app.state, "learner_sessions", None)
            token = (
                sessions.issue(conn, row[0])
                if isinstance(sessions, LearnerSessions) and row
                else None
            )
        assert row is not None
        if token is not None:
            response.set_cookie(
                COOKIE_NAME,
                token,
                max_age=SESSION_SECONDS,
                httponly=True,
                secure=request.url.scheme == "https",
                samesite="lax",
                path="/",
            )
        return {"learner_id": row[0]}

    @app.get("/topics/cached", response_model=CachedTopics)
    def cached_topics(request: Request) -> dict[str, list[dict[str, str]]]:
        with request.app.state.pool.connection() as conn:
            rows = conn.execute(
                "select distinct s.slug,s.name_vi from topic_jobs j "
                "join subjects s on s.slug=j.subject_slug "
                "where j.status='ready' and not j.fixture and j.graph_ready and j.items_ready"
            ).fetchall()
        return {"topics": [{"subject_slug": r[0], "name_vi": r[1]} for r in rows]}

    def topic_state(topic_id: UUID, request: Request) -> tuple[dict[str, Any], bool]:
        with request.app.state.pool.connection() as conn:
            state = snapshot(conn, topic_id)
            metadata = conn.execute(
                "select fixture,tier from topic_jobs where id=%s", (topic_id,)
            ).fetchone()
        if state is None or metadata is None:
            raise HTTPException(404, "Không tìm thấy chủ đề")
        request.state.tier = metadata[1]
        return state, metadata[0]

    @app.get("/topics/{topic_id}", response_model=TopicState)
    def get_topic(topic_id: UUID, request: Request) -> JSONResponse:
        state, fixture = topic_state(topic_id, request)
        return JSONResponse(state, headers={"X-Data-Fixture": str(fixture).lower()})

    @app.get("/topics/{topic_id}/events")
    async def topic_events(topic_id: UUID, request: Request) -> StreamingResponse:
        initial, fixture = await asyncio.to_thread(topic_state, topic_id, request)

        async def stream() -> AsyncIterator[str]:
            state = initial
            previous = ""
            heartbeat = time.monotonic()
            while not await request.is_disconnected():
                data = json.dumps(state, ensure_ascii=False)
                if data != previous:
                    yield f"event: state\ndata: {data}\n\n"
                    previous = data
                if state["status"] in ("ready", "failed"):
                    return
                if time.monotonic() - heartbeat >= HEARTBEAT_SECONDS:
                    yield "event: heartbeat\ndata: {}\n\n"
                    heartbeat = time.monotonic()
                await asyncio.sleep(1)
                state, _ = await asyncio.to_thread(topic_state, topic_id, request)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Data-Fixture": str(fixture).lower(),
            },
        )

    @app.get("/health")
    def health(request: Request) -> Health:
        db_ok = ping(request.app.state.pool)
        return Health(status="ok", db="ok" if db_ok else "down")

    return app


def create_content_app(
    settings: Settings | None = None,
    *,
    repository: "Repository | None" = None,
    gateway: "Gateway | None" = None,
    confirmation: "GraphConfirmation | None" = None,
) -> FastAPI:
    """P2 entry point: P4 learning/tutor with P2 queue and private upload storage."""
    from app.content.backends import LearningBackend, TutorBackend
    from app.content.gateway import P3Gateway
    from app.content.repository import Repository

    settings = settings or get_settings()
    current: FastAPI
    store = repository if repository is not None else Repository(lambda: current.state.pool)
    models = gateway if gateway is not None else P3Gateway()
    confirmations = GraphConfirmations(settings.database_url)
    learner_sessions = LearnerSessions(settings.database_url)
    approved = confirmation if confirmation is not None else confirmations
    current = create_app(
        settings,
        learning_backend=LearningBackend(
            store, approved, placer=make_placer(settings.placement_strategy)
        ),
        tutor_backend=TutorBackend(
            store, models, approved, demo_uploads_enabled=settings.demo_uploads_enabled
        ),
    )
    platform_lifespan = current.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        async with platform_lifespan(application):
            await asyncio.to_thread(store.require_schema)
            await asyncio.to_thread(confirmations.require_schema)
            await asyncio.to_thread(learner_sessions.require_schema)
            yield

    current.router.lifespan_context = lifespan
    current.state.p4_repository = store
    current.state.graph_confirmations = confirmations
    current.state.learner_sessions = learner_sessions
    return current


app = create_app()
