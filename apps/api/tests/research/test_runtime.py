"""Real SQL/retrieval wiring with fake embeddings/models; no quality or latency claim."""

import asyncio
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

import pytest

from app.content.demo import install_schema
from app.content.models import Chunk as ContentChunk
from app.content.models import Graph, Source
from app.content.ports import ContentPorts
from app.content.repository import Repository
from app.db import create_pool
from app.rag.notebook import Chunk
from app.rag.retrieve import Retriever
from app.rag.store import SourceInfo, replace_chunks, upsert_source
from app.research.library import load_manifest
from app.research.pipeline import retrieve_chunks
from app.research.reader import SourceError
from app.research.runtime import (
    ResearchSettings,
    indexed_library_source,
    retrieval_configuration,
    worker_retriever,
)
from tests.content.fakes import FakeGateway
from tests.content.test_runtime_database import database_url as database_url
from tests.rag.fixtures import FakeEmbedder


class QueryEmbedder:
    dim = 1024

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * 1023 for _ in texts]


def test_startup_requires_explicit_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = ResearchSettings(_env_file=None, research_subject="")
    monkeypatch.setattr("app.research.runtime.ResearchSettings", lambda: settings)
    with pytest.raises(ValueError, match="RESEARCH_SUBJECT"):
        retrieval_configuration()


def test_library_metadata_bridge_rejects_unreviewed_source() -> None:
    with pytest.raises(SourceError):
        indexed_library_source("id", "Unknown", None, "https://evil.example", "CC BY 4.0", "v1")


def test_sql_library_retrieval_preserves_page_urls_and_bounds_graph_context(
    database_url: str,
) -> None:
    install_schema(database_url)
    manifest = load_manifest(Path(__file__).resolve().parents[4] / "data/sources/library.yaml")
    book = next(book for book in manifest.books if book.slug == "think-python-2e")
    with create_pool(database_url) as pool:
        with pool.connection() as conn:
            source_id = upsert_source(
                conn,
                SourceInfo(
                    subject_slug=book.slug,
                    subject_name_vi=book.subject_name_vi or "Python",
                    subject_name_en=book.subject_name_en or "Python",
                    title=book.title,
                    author=None,
                    license="CC BY-NC 3.0",
                    url=book.start_url,
                    version="test",
                ),
            )
            split = [
                Chunk(
                    chapter_no=1,
                    chapter="Python",
                    section=f"Section {i}",
                    kind="text",
                    content=f"Python paragraph {i}",
                    source_uri=f"{book.start_url}/{i}",
                )
                for i in range(15)
            ]
            replace_chunks(conn, source_id, split, FakeEmbedder())
        repository = Repository(lambda: pool)
        ports = ContentPorts(repository, FakeGateway(), "topic-p3-runtime-test")
        retriever = Retriever(pool, QueryEmbedder())
        assert worker_retriever(pool) is worker_retriever(pool)

        async def generate(
            chunks: list[ContentChunk],
            sources: list[Source],
            gateway: object,
            *,
            tier: str,
            goal: str | None = None,
            max_concepts: int | None = None,
        ) -> Graph:
            assert len(chunks) == 12
            return Graph.model_validate(
                {
                    "concepts": [
                        {
                            "slug": "python",
                            "name_vi": "Python",
                            "name_en": "Python",
                            "description_vi": "Test",
                            "sources": [sources[0].url],
                            "chunk_ids": [str(c.chunk_id) for c in chunks],
                        }
                    ],
                    "edges": [],
                }
            )

        async def run() -> None:
            sources = await ports.quick_sources("Python")
            assert sources and sources[0].url == book.start_url
            prepared = list(await ports.index(sources, None))
            assert len(prepared) == 15
            assert all(
                c.source_uri != book.start_url and c.source_url == book.start_url for c in prepared
            )
            selected = await retrieve_chunks(retriever, "Python", book.slug, prepared, 12)
            assert len(selected) == 12
            assert [c.id for c in selected] == [
                c.id for c in prepared if c.id in {s.id for s in selected}
            ]
            with patch("app.content.ports.generate_graph", generate):
                graph = await ports.build_graph("Python", selected, "free")
            assert graph.supported and len(ports.chunks) == 12

        try:
            asyncio.run(run())
        finally:
            worker_retriever.cache_clear()
            with pool.connection() as conn:
                conn.execute(
                    "delete from subjects where slug=any(%s)",
                    ([book.slug, "topic-p3-runtime-test"],),
                )
