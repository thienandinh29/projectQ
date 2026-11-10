"""Explicit fixture-only preview for P5; never mount this in the production API.

From apps/api: uv run uvicorn tests.api.preview:app --host 127.0.0.1 --port 8013
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

from app.api import learn, topics, tutor
from tests.api.conftest import FakeBackend, fake_link

app = FastAPI(
    title="NodeTrail P3 — fixture preview",
    description=(
        "Development contract preview with fake engine, queue, storage and tutor. "
        "No real model calls or durable data. Not an end-to-end acceptance demo."
    ),
)
backend = FakeBackend()
app.include_router(learn.create_router(backend))
app.include_router(topics.create_router(backend, link_reader=fake_link, demo_uploads_enabled=True))
app.include_router(tutor.create_router(backend))


@app.middleware("http")
async def fixture_label(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    response.headers["X-NodeTrail-Backend"] = "fixture"
    return response
