"""Bind P4 adapters into P2's existing app; no duplicate routes or application framework."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings
from app.content.backends import LearningBackend, TopicsBackend, TutorBackend
from app.content.gateway import Gateway, P3Gateway
from app.content.learning import GraphConfirmation
from app.content.repository import Repository
from app.engine.placer import make_placer
from app.main import create_app as platform_app


def create_app(
    settings: Settings | None = None,
    *,
    repository: Repository | None = None,
    gateway: Gateway | None = None,
    confirmation: GraphConfirmation | None = None,
) -> FastAPI:
    """uvicorn app.content.runtime:create_app --factory (process env only; no .env read)."""
    settings = settings or Settings(_env_file=None)
    app: FastAPI
    store = repository or Repository(lambda: app.state.pool)
    models = gateway or P3Gateway()
    app = platform_app(
        settings,
        learning_backend=LearningBackend(
            store, confirmation, placer=make_placer(settings.placement_strategy)
        ),
        topics_backend=TopicsBackend(store),
        tutor_backend=TutorBackend(
            store, models, confirmation, demo_uploads_enabled=settings.demo_uploads_enabled
        ),
    )
    platform_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(current: FastAPI) -> AsyncIterator[None]:
        async with platform_lifespan(current):
            await asyncio.to_thread(store.require_schema)
            yield

    app.router.lifespan_context = lifespan
    app.state.p4_repository = store
    return app
