"""Shared fixtures for the retrieval tests: a small migrated database and a Retriever on it."""

from collections.abc import Iterator

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from app.rag.embed import ThreadedEmbedder
from app.rag.notebook import Chunk, parse_notebook
from app.rag.retrieve import Retriever
from app.rag.store import SourceInfo, replace_chunks, upsert_source
from tests.rag.fixtures import NOTEBOOK, FakeEmbedder


def _info(slug: str, title: str) -> SourceInfo:
    return SourceInfo(
        subject_slug=slug,
        subject_name_vi=slug,
        subject_name_en=slug,
        title=title,
        author="Tác giả",
        license="CC BY-NC-SA 4.0",
        url="https://example.org/book",
        version="v1",
    )


@pytest.fixture
def retriever(database_url: str) -> Iterator[Retriever]:
    embedder = FakeEmbedder()
    chunks = parse_notebook(NOTEBOOK, 5)
    with psycopg.connect(database_url) as conn:
        conn.execute("delete from sources")  # tests share one database; start clean
        replace_chunks(conn, upsert_source(conn, _info("python", "Think Python")), chunks, embedder)
        other = [
            Chunk(1, "Cells", "Membranes", "text", "The cell membrane is a lipid bilayer.", "u/bio")
        ]
        replace_chunks(conn, upsert_source(conn, _info("biology", "Biology 2e")), other, embedder)
    pool = ConnectionPool(database_url, min_size=1, max_size=2, open=True)
    try:
        yield Retriever(pool, ThreadedEmbedder(embedder))
    finally:
        pool.close()
        # The database is shared by the whole session: leave it as the migrations left it, or
        # tests that count rows (ingest) would depend on which test file ran first.
        with psycopg.connect(database_url) as conn:
            conn.execute("delete from sources")
            conn.execute("delete from subjects")
