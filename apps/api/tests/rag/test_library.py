"""Library indexing: read and validate every book, chunk it, embed it, store it with its page."""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest
from pydantic import ValidationError

from app.rag import library
from app.rag.chunker import chunk_document
from app.rag.embed import ThreadedEmbedder
from app.rag.library import ingest_library, load_book, load_library
from app.rag.retrieve import Retriever
from app.schemas import ParsedDocument, SourceMeta
from tests.rag.fixtures import FakeEmbedder

EXAMPLE = Path(__file__).resolve().parents[4] / "specs/contracts/library-example/example-biology"


def _source(
    slug: str = "sinh-hoc", title: str = "Sinh học 1", license: str = "CC BY 4.0"
) -> dict[str, Any]:
    return {
        "subject_slug": slug,
        "subject_name_vi": "Sinh học",
        "subject_name_en": "Biology",
        "title": title,
        "license": license,
    }


def _document(*texts: str, page: int | None = None) -> dict[str, Any]:
    return {
        "blocks": [
            {
                "chapter": "Chương 1",
                "section": f"Mục {i}",
                "text": t,
                "source_uri": f"https://x/book#m{i}",
                "page": page,
            }
            for i, t in enumerate(texts)
        ]
    }


def _write_book(root: Path, name: str, source: dict[str, Any], document: dict[str, Any]) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "source.json").write_text(json.dumps(source), encoding="utf-8")
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    return folder


@pytest.fixture
def clean_db(database_url: str) -> Iterator[str]:
    def wipe() -> None:
        with psycopg.connect(database_url) as conn:
            conn.execute("delete from sources")
            conn.execute("delete from subjects")

    wipe()
    yield database_url
    wipe()  # the database is shared across the session; leave it as the migrations left it


def _count(url: str, sql: str = "select count(*) from chunks") -> int:
    with psycopg.connect(url) as conn:
        row = conn.execute(sql).fetchone()
    assert row is not None
    return int(row[0])


# --- the sample P3 copies, and the contracts ---------------------------------------------------


def test_the_example_book_is_valid_and_chunks_as_documented() -> None:
    book = load_book(EXAMPLE)
    assert book.info.subject_slug == "sinh-hoc-co-ban"
    assert [c.kind for c in book.chunks] == ["text", "text", "glossary"]
    assert (
        book.chunks[0].content.count("\n\n") == 1
    )  # the two paragraphs of one block stay together


@pytest.mark.parametrize(
    "license",
    ["CC BY-ND 4.0", "CC BY-NC-ND 4.0", "cc by-nc-nd", "CC BY-NoDerivatives", "No Derivatives"],
)
def test_no_derivatives_licences_are_rejected(license: str) -> None:
    with pytest.raises(ValidationError, match="NoDerivatives"):
        SourceMeta.model_validate(_source(license=license))


@pytest.mark.parametrize(
    "license",
    ["CC BY 4.0", "CC BY-SA 4.0", "CC BY-NC-SA 4.0 (text), MIT (code)", "CC0 1.0", "Public domain"],
)
def test_other_licences_pass(license: str) -> None:
    SourceMeta.model_validate(_source(license=license))


def test_document_contract_is_strict() -> None:
    good = _document("x")["blocks"][0]
    ParsedDocument.model_validate({"blocks": [good]})
    for bad in (
        {**good, "page": 0},
        {**good, "source_uri": ""},
        {**good, "kind": "table"},
        {**good, "oops": 1},
    ):
        with pytest.raises(ValidationError):
            ParsedDocument.model_validate({"blocks": [bad]})
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate({"blocks": []})


# --- loading ---------------------------------------------------------------------------------


def test_load_errors_name_the_book_and_the_problem(tmp_path: Path) -> None:
    _write_book(tmp_path, "nd-book", _source(license="CC BY-ND 4.0"), _document("x"))
    with pytest.raises(ValueError, match=r"^nd-book: .*NoDerivatives"):
        load_book(tmp_path / "nd-book")

    _write_book(tmp_path, "blank", _source(), _document("   ", ""))
    with pytest.raises(ValueError, match="blank: the document has no text"):
        load_book(tmp_path / "blank")

    broken = _write_book(tmp_path, "broken", _source(), _document("x"))
    (broken / "document.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_book(broken)

    missing = _write_book(tmp_path, "missing", _source(), _document("x"))
    (missing / "document.json").unlink()
    with pytest.raises(ValueError, match=r"document\.json is missing"):
        load_book(missing)


def test_a_library_needs_at_least_one_book(tmp_path: Path) -> None:
    (tmp_path / "not-a-book").mkdir()
    with pytest.raises(ValueError, match="no book folders"):
        load_library(tmp_path)


# --- indexing (real pgvector) -----------------------------------------------------------------


def test_ingest_stores_chunks_with_their_page_and_source(tmp_path: Path, clean_db: str) -> None:
    _write_book(tmp_path, "a", _source(), _document("Trang ba.", page=3))
    _write_book(tmp_path, "b", _source("hoa-hoc", "Hóa học 1"), _document("Trang chín.", page=9))
    written = ingest_library(tmp_path, clean_db, FakeEmbedder())
    assert written == {"Sinh học 1": 1, "Hóa học 1": 1}
    with psycopg.connect(clean_db) as conn:
        rows = conn.execute(
            "select s.title, c.page, c.source_uri, c.chapter from chunks c"
            " join sources s on s.id = c.source_id order by s.title"
        ).fetchall()
    assert rows == [
        ("Hóa học 1", 9, "https://x/book#m0", "Chương 1"),
        ("Sinh học 1", 3, "https://x/book#m0", "Chương 1"),
    ]


def test_reingesting_replaces_instead_of_duplicating(tmp_path: Path, clean_db: str) -> None:
    folder = _write_book(tmp_path, "a", _source(), _document("Một.", "Hai."))
    ingest_library(tmp_path, clean_db, FakeEmbedder())
    first = _count(clean_db)
    (folder / "document.json").write_text(json.dumps(_document("Chỉ một.")), encoding="utf-8")
    ingest_library(tmp_path, clean_db, FakeEmbedder())
    assert first == 2 and _count(clean_db) == 1


def test_a_bad_book_stops_the_run_before_anything_is_embedded(
    tmp_path: Path, clean_db: str
) -> None:
    _write_book(tmp_path, "a-good", _source(), _document("Tốt."))
    _write_book(tmp_path, "b-bad", _source("x", "Xấu", license="CC BY-ND 4.0"), _document("Xấu."))
    embedder = FakeEmbedder()
    with pytest.raises(ValueError, match="b-bad"):
        ingest_library(tmp_path, clean_db, embedder)
    assert (
        embedder.calls == 0 and _count(clean_db) == 0
    )  # the good book was not half-indexed either


def test_an_indexed_book_is_found_by_retrieval_with_its_page(tmp_path: Path, clean_db: str) -> None:
    from psycopg_pool import ConnectionPool

    _write_book(tmp_path, "a", _source(), _document("Quang hợp tạo ra oxy.", page=12))
    embedder = FakeEmbedder()
    ingest_library(tmp_path, clean_db, embedder)
    chunk = chunk_document(
        ParsedDocument.model_validate(_document("Quang hợp tạo ra oxy.", page=12))
    )[0]
    pool = ConnectionPool(clean_db, min_size=1, max_size=2, open=True)
    try:
        hits = asyncio.run(
            Retriever(pool, ThreadedEmbedder(embedder)).search(
                chunk.embedding_text, "sinh-hoc", k=1
            )
        )
    finally:
        pool.close()
    assert hits[0].page == 12 and hits[0].source_uri == "https://x/book#m0"


# --- command line ------------------------------------------------------------------------------


def _patch(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setattr("app.rag.library.get_settings", lambda: SimpleNamespace(database_url=url))
    monkeypatch.setattr("app.rag.embed.make_embedder", lambda *a, **k: FakeEmbedder())
    monkeypatch.delenv("TEI_URL", raising=False)


def test_cli_indexes_and_builds_the_index_on_request(
    tmp_path: Path, clean_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_book(tmp_path, "a", _source(), _document("Một."))
    _patch(monkeypatch, clean_db)
    sql = "select count(*) from pg_indexes where indexname = 'chunks_embedding_idx'"
    assert library.main([str(tmp_path)]) == 0 and _count(clean_db, sql) == 0
    try:
        assert library.main([str(tmp_path), "--build-index"]) == 0 and _count(clean_db, sql) == 1
    finally:
        with psycopg.connect(clean_db, autocommit=True) as conn:
            conn.execute("drop index if exists chunks_embedding_idx")


def test_cli_reports_a_bad_library_with_exit_code_1(
    tmp_path: Path,
    clean_db: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_book(tmp_path, "bad", _source(license="CC BY-ND 4.0"), _document("x"))
    _patch(monkeypatch, clean_db)
    assert library.main([str(tmp_path)]) == 1
    assert "error: bad:" in capsys.readouterr().err
