"""Real PostgreSQL regression coverage; CI provides pgvector, never mocked."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import pytest

from app.content.repository import ContentUnavailable, Repository
from app.db import create_pool
from tests.content.fakes import topic
from tests.content.test_runtime_database import database_url as database_url


@pytest.fixture
def repository(database_url: str) -> Iterator[Repository]:
    with create_pool(database_url) as pool:
        yield Repository(lambda: pool)


def test_shared_book_chunks_keep_ids_indices_and_provenance(repository: Repository) -> None:
    sources, chunks, _, _ = topic("cell-basics")
    assert len(sources) >= 2 and len({s.title for s in sources}) < len(sources)
    subject = "alias-" + uuid4().hex
    repository.save_material(subject, sources, chunks)

    def snapshot() -> list[tuple[Any, ...]]:
        with repository.transaction() as conn:
            return conn.execute(
                "select id,source_id,chunk_index,source_uri,p4_metadata from chunks "
                "where id=any(%s) order by id",
                ([c.chunk_id for c in chunks],),
            ).fetchall()

    first = snapshot()
    assert len(first) == len(chunks)
    assert len({row[1] for row in first}) == 1  # Both Biology sections share one DB book.
    assert len({(row[1], row[2]) for row in first}) == len(chunks)
    repository.save_material(subject, list(reversed(sources)), list(reversed(chunks)))
    assert snapshot() == first
    new_chunk = chunks[0].model_copy(update={"chunk_id": uuid4(), "content": "Additional section."})
    repository.save_material(subject, sources, [new_chunk])
    assert snapshot() == first
    with repository.transaction() as conn:
        loaded_sources, loaded_chunks = repository.material(conn, [c.chunk_id for c in chunks])
        assert loaded_chunks == chunks
        assert {s.source_id: s for s in loaded_sources} == {s.source_id: s for s in sources}
        assert conn.execute(
            "select count(*) from chunks where id=%s", (new_chunk.chunk_id,)
        ).fetchone() == (1,)


def test_concurrent_retry_and_rollback_preserve_stable_ids(repository: Repository) -> None:
    sources, chunks, _, _ = topic("cell-basics")
    # Independent fixture identities: canonical UUIDs belong to the first test's book.
    chunks = [c.model_copy(update={"chunk_id": uuid4()}) for c in chunks]
    subject = "concurrent-" + uuid4().hex
    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: repository.save_material(subject, sources, chunks), range(2)))
    with repository.transaction() as conn:
        assert conn.execute(
            "select count(*) from chunks where id=any(%s)", ([c.chunk_id for c in chunks],)
        ).fetchone() == (len(chunks),)
    conflicting = sources[0].model_copy(update={"source_id": "other", "title": "Other book"})
    fresh = chunks[0].model_copy(update={"chunk_id": uuid4(), "source_id": "other"})
    wrong_owner = chunks[0].model_copy(update={"source_id": "other"})
    with pytest.raises(ContentUnavailable):
        repository.save_material(subject, [conflicting], [fresh, wrong_owner])
    with repository.transaction() as conn:
        assert conn.execute(
            "select count(*) from chunks where id=%s", (fresh.chunk_id,)
        ).fetchone() == (0,)
    repository.save_material(subject, sources, chunks)


def test_search_title_change_keeps_the_same_url_and_chunk_identity(repository: Repository) -> None:
    sources, chunks, _, _ = topic()
    source = sources[0]
    chunks = [
        c.model_copy(update={"chunk_id": uuid4()})
        for c in chunks
        if c.source_id == source.source_id
    ]
    subject = "title-retry-" + uuid4().hex
    repository.save_material(subject, [source], chunks)
    with repository.transaction() as conn:
        before = conn.execute(
            "select id,source_id,chunk_index from chunks where id=any(%s) order by id",
            ([c.chunk_id for c in chunks],),
        ).fetchall()
    renamed = source.model_copy(update={"title": source.title + " (PDF)"})
    repository.save_material(subject, [renamed], chunks)
    with repository.transaction() as conn:
        after = conn.execute(
            "select id,source_id,chunk_index from chunks where id=any(%s) order by id",
            ([c.chunk_id for c in chunks],),
        ).fetchall()
        stored_sources, stored_chunks = repository.material(conn, [c.chunk_id for c in chunks])
    assert before == after
    assert stored_chunks == chunks and stored_sources == [renamed]
