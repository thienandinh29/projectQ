from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from app.schemas import DocBlock, ParsedDocument, SourceMeta
from app.services.indexing import index_document


class Embeddings:
    dim = 1024

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return [[1.0] + [0.0] * 1023 for _ in texts]


def source() -> tuple[SourceMeta, ParsedDocument]:
    meta = SourceMeta(
        subject_slug="index-test-" + uuid4().hex,
        subject_name_vi="Kiểm tra",
        subject_name_en="Test",
        title="Licensed source",
        license="CC BY 4.0",
        url="https://example.org/book",
        version="test-revision",
    )
    doc = ParsedDocument(
        blocks=[
            DocBlock(
                chapter="Chapter",
                section="Section",
                text="First page.",
                source_uri=meta.url or "",
                page=1,
            ),
            DocBlock(
                chapter="Chapter",
                section="Section",
                text="Second page.",
                source_uri=meta.url or "",
                page=2,
            ),
        ]
    )
    return meta, doc


def test_retry_keeps_ids_vectors_and_provenance(database_url: str) -> None:
    meta, doc = source()
    embedder = Embeddings()
    first = index_document(database_url, meta, doc, embedder)
    assert index_document(database_url, meta, doc, embedder) == first
    assert embedder.calls == 1
    assert [c.page for c in first] == [1, 2]
    assert all(c.source_uri == meta.url for c in first)
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "select vector_dims(c.embedding),s.license,s.version from chunks c "
            "join sources s on s.id=c.source_id join subjects t on t.id=s.subject_id "
            "where t.slug=%s",
            (meta.subject_slug,),
        ).fetchall()
        assert rows == [(1024, meta.license, meta.version)] * 2


def test_concurrent_retry_embeds_once(database_url: str) -> None:
    meta, doc = source()
    embedder = Embeddings()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _: index_document(database_url, meta, doc, embedder),
                range(2),
            )
        )
    assert results[0] == results[1]
    assert embedder.calls == 1


def test_changed_source_rolls_back_metadata_and_retains_citations(database_url: str) -> None:
    meta, doc = source()
    embedder = Embeddings()
    original = index_document(database_url, meta, doc, embedder)
    doc.blocks[0].text = "Changed text"
    with pytest.raises(ValueError, match="source text changed"):
        index_document(database_url, meta.model_copy(update={"version": "changed"}), doc, embedder)
    with psycopg.connect(database_url) as conn:
        assert conn.execute(
            "select version from sources where id=(select source_id from chunks where id=%s)",
            (original[0].id,),
        ).fetchone() == ("test-revision",)
        assert conn.execute(
            "select content from chunks where id=%s", (original[0].id,)
        ).fetchone() == ("First page.",)


def test_embedding_failure_rolls_back_source(database_url: str) -> None:
    class Broken(Embeddings):
        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            raise RuntimeError("embedding unavailable")

    meta, doc = source()
    with pytest.raises(RuntimeError, match="embedding unavailable"):
        index_document(database_url, meta, doc, Broken())
    with psycopg.connect(database_url) as conn:
        assert not conn.execute(
            "select 1 from subjects where slug=%s", (meta.subject_slug,)
        ).fetchone()


def test_empty_document_and_wrong_dimension_rejected(database_url: str) -> None:
    meta, doc = source()
    for block in doc.blocks:
        block.text = " "
    with pytest.raises(ValueError, match="no indexable text"):
        index_document(database_url, meta, doc, Embeddings())
    meta, doc = source()
    embedder = Embeddings()
    embedder.dim = 3
    with pytest.raises(ValueError, match="dimension 1024"):
        index_document(database_url, meta, doc, embedder)


def test_index_uses_configured_embedder_lazily(
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings
    from app.services import indexing

    settings = Settings(_env_file=None, embedding_backend="tei", tei_url="http://localhost:18080")
    monkeypatch.setattr(indexing, "get_settings", lambda: settings)
    calls: list[tuple[str, str | None, str | None]] = []

    def factory(backend: str, *, tei_url: str | None, api_key: str | None) -> Embeddings:
        calls.append((backend, tei_url, api_key))
        return Embeddings()

    monkeypatch.setattr(indexing, "make_embedder", factory)
    meta, doc = source()
    assert index_document(database_url, meta, doc) == index_document(database_url, meta, doc)
    assert calls == [("tei", settings.tei_url, None)]
