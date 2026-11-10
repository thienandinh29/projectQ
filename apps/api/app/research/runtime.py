"""Job-local research configuration; no global mutable backend shared across requests."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from psycopg_pool import ConnectionPool
from pydantic import Field

from app.config import Settings
from app.rag.embed import EMBEDDING_DIM, TeiEmbedder
from app.rag.retrieve import Retriever
from app.research.agent import ResearchAgent
from app.research.pipeline import ChunkRetriever, PipelinePorts, TopicPipeline

_agent: ContextVar[ResearchAgent | None] = ContextVar("research_agent", default=None)


@contextmanager
def research_scope(agent: ResearchAgent) -> Iterator[None]:
    token = _agent.set(agent)
    try:
        yield
    finally:
        _agent.reset(token)


def current_agent() -> ResearchAgent:
    agent = _agent.get()
    if agent is None:
        from app.research.search import default_agent

        return default_agent()
    return agent


class WorkerEmbedder:
    """One embedder facade per worker; HTTP clients cannot outlive asyncio.run loops."""

    dim = EMBEDDING_DIM

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        from app.config import get_settings

        settings = get_settings()
        embedder = TeiEmbedder(settings.tei_url, api_key=settings.tei_api_key.get_secret_value())
        try:
            return await embedder.aembed(texts)
        finally:
            await embedder.aclose()


@lru_cache(maxsize=4)
def worker_retriever(pool: ConnectionPool) -> Retriever:
    """Shared across jobs using the worker's already-managed connection pool."""
    return Retriever(pool, WorkerEmbedder())


def build_pipeline(
    ports: PipelinePorts, *, retriever: ChunkRetriever, subject: str, k: int = 12
) -> TopicPipeline:
    return TopicPipeline(ports, retriever=retriever, retrieval_subject=subject, retrieval_k=k)


def configured_pipeline(ports: PipelinePorts, pool: ConnectionPool) -> TopicPipeline:
    """Production construction used by P4's worker processor; no implicit subject."""
    subject, k = retrieval_configuration()
    return build_pipeline(ports, retriever=worker_retriever(pool), subject=subject, k=k)


class ResearchSettings(Settings):
    research_subject: str = ""
    retrieval_k: int = Field(default=12, ge=1, le=50)


def retrieval_configuration() -> tuple[str, int]:
    settings = ResearchSettings()
    subject = settings.research_subject.strip()
    if not subject:
        raise ValueError("RESEARCH_SUBJECT must name the explicitly indexed library/upload subject")
    return subject, settings.retrieval_k


def indexed_library_source(
    source_id: object, title: str, author: str | None, url: str, license_name: str, version: str
) -> dict[str, Any]:
    """Read-only bridge from P1 library rows to P4 metadata, limited to audited books."""
    from app.research.agent import canonical_url, detect_license
    from app.research.library import load_manifest
    from app.research.reader import SourceError

    manifest = load_manifest(Path(__file__).resolve().parents[4] / "data/sources/library.yaml")
    matches = [
        book
        for book in manifest.books
        if book.title == title and canonical_url(book.start_url) == canonical_url(url)
    ]
    if len(matches) != 1:
        raise SourceError("Nguồn chưa có metadata đã duyệt trong thư viện.")
    detect_license(license_name)
    book = matches[0]
    return {
        "source_id": str(source_id),
        "title": title,
        "author": author or "",
        "publisher": book.publisher,
        "version": version,
        "url": url,
        "section": title,
        "license": license_name,
        "accessed_at": datetime.now(UTC).date().isoformat(),
        "attribution": book.publisher,
        "model_ingestion_allowed": True,
    }
