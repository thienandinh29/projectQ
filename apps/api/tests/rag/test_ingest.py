import json
import sys
from pathlib import Path
from typing import Any

import psycopg
import pytest

from app.rag.embed import to_pgvector
from app.rag.ingest import ingest
from app.rag.ingest import main as ingest_main
from app.rag.store import build_vector_index, drop_vector_index
from tests.rag.fixtures import NOTEBOOK, FakeEmbedder


@pytest.fixture
def book_dir(tmp_path: Path) -> Path:
    (tmp_path / "chap05.ipynb").write_text(json.dumps(NOTEBOOK), encoding="utf-8")
    (tmp_path / "SOURCE_SHA").write_text("abc123\n")
    return tmp_path


def _chunks(database_url: str) -> list[tuple[object, ...]]:
    with psycopg.connect(database_url) as conn:
        return conn.execute(
            "select c.chunk_index, c.chapter_no, c.section, c.kind, c.source_uri,"
            " vector_dims(c.embedding), s.version, s.license"
            " from chunks c join sources s on s.id = c.source_id order by c.chunk_index"
        ).fetchall()


def test_ingest_stores_chunks_with_provenance(database_url: str, book_dir: Path) -> None:
    count = ingest(book_dir, database_url, FakeEmbedder())
    rows = _chunks(database_url)
    assert count == len(rows) == 6
    assert [r[0] for r in rows] == list(range(6))
    assert all(r[1] == 5 and r[5] == 1024 for r in rows)
    assert rows[0][6] == "abc123"
    assert "CC BY-NC-SA" in str(rows[0][7])
    assert {r[3] for r in rows} == {"text", "glossary", "exercise"}


def test_reingest_replaces_instead_of_duplicating(database_url: str, book_dir: Path) -> None:
    ingest(book_dir, database_url, FakeEmbedder())
    ingest(book_dir, database_url, FakeEmbedder())
    assert len(_chunks(database_url)) == 6
    with psycopg.connect(database_url) as conn:
        sources = conn.execute("select count(*) from sources").fetchone()
    assert sources == (1,)


def test_nearest_neighbour_finds_identical_text(database_url: str, book_dir: Path) -> None:
    embedder = FakeEmbedder()
    ingest(book_dir, database_url, embedder)
    with psycopg.connect(database_url) as conn:
        target = conn.execute(
            "select section, content, chapter from chunks where kind = 'glossary'"
        ).fetchone()
        assert target is not None
        query = embedder.embed([f"{target[2]} > {target[0]}\n\n{target[1]}"])[0]
        best = conn.execute(
            "select section from chunks order by embedding <=> %s::halfvec(1024) limit 1",
            (to_pgvector(query),),
        ).fetchone()
    assert best == ("Glossary",)


def test_wrong_dimension_is_rejected(database_url: str, book_dir: Path) -> None:
    class Short(FakeEmbedder):
        dim = 1024

        def embed(self, texts: object) -> list[list[float]]:
            return [[0.0] * 3 for _ in texts]  # type: ignore[attr-defined]

    with pytest.raises(ValueError, match="dim"):
        ingest(book_dir, database_url, Short())


def test_empty_directory_is_an_error(database_url: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no chapter notebooks"):
        ingest(tmp_path, database_url, FakeEmbedder())


def test_vector_index_is_built_after_loading(database_url: str, book_dir: Path) -> None:
    ingest(book_dir, database_url, FakeEmbedder())
    with psycopg.connect(database_url) as conn:
        drop_vector_index(conn)
        build_vector_index(conn)
        build_vector_index(conn)  # idempotent
        indexdef = conn.execute(
            "select indexdef from pg_indexes where indexname = 'chunks_embedding_idx'"
        ).fetchone()
        drop_vector_index(conn)  # leave the shared test DB as migrations left it
    assert indexdef is not None
    assert "hnsw" in indexdef[0] and "halfvec_cosine_ops" in indexdef[0]


# --- command line and device choice (GPU host) ----------------------------------------------------


def test_pick_device_follows_pytorch(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.rag.embed import pick_device

    for available, expected in ((True, "cuda"), (False, "cpu")):
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda a=available: a))
        monkeypatch.setitem(sys.modules, "torch", torch)
        assert pick_device() == expected
    monkeypatch.setitem(sys.modules, "torch", None)  # an import of None raises ImportError
    assert pick_device() == "cpu"


def test_local_embedder_uses_the_gpu_with_a_bigger_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from app.rag.embed import BgeM3Embedder

    seen: list[str] = []

    class FakeModel:
        def __init__(self, name: str, device: str) -> None:
            seen.append(device)

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=FakeModel)
    )
    gpu = BgeM3Embedder(device="cuda")
    cpu = BgeM3Embedder(device="cpu")
    explicit = BgeM3Embedder(device="cuda", batch_size=8)
    assert seen == ["cuda", "cpu", "cuda"]
    assert (gpu._batch_size, cpu._batch_size, explicit._batch_size) == (64, 16, 8)


def _run_cli(
    monkeypatch: pytest.MonkeyPatch, database_url: str, argv: list[str], env_url: str | None = None
) -> tuple[int, list[tuple[str, str | None]]]:
    from types import SimpleNamespace

    calls: list[tuple[str, str | None]] = []

    def fake_make(backend: str, *, tei_url: str | None = None, api_key: str | None = None) -> Any:
        calls.append((backend, tei_url))
        return FakeEmbedder()

    monkeypatch.setattr(
        "app.rag.ingest.get_settings", lambda: SimpleNamespace(database_url=database_url)
    )
    monkeypatch.setattr("app.rag.embed.make_embedder", fake_make)
    if env_url is None:
        monkeypatch.delenv("TEI_URL", raising=False)
    else:
        monkeypatch.setenv("TEI_URL", env_url)
    return ingest_main(argv), calls


def test_cli_defaults_to_tei_when_the_url_is_set(
    monkeypatch: pytest.MonkeyPatch, database_url: str, book_dir: Path
) -> None:
    code, calls = _run_cli(monkeypatch, database_url, [str(book_dir)], env_url="http://gpu:8080")
    assert code == 0 and calls == [("tei", "http://gpu:8080")]


def test_cli_defaults_to_the_local_model_without_a_url(
    monkeypatch: pytest.MonkeyPatch, database_url: str, book_dir: Path
) -> None:
    code, calls = _run_cli(monkeypatch, database_url, [str(book_dir)])
    assert code == 0 and calls == [("local", None)]


def test_cli_tei_without_a_url_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, database_url: str, book_dir: Path
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        _run_cli(monkeypatch, database_url, [str(book_dir), "--embedder", "tei"])
    assert exit_info.value.code == 2


def test_cli_builds_the_index_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, database_url: str, book_dir: Path
) -> None:
    def index_exists() -> bool:
        with psycopg.connect(database_url) as conn:
            row = conn.execute(
                "select 1 from pg_indexes where indexname = 'chunks_embedding_idx'"
            ).fetchone()
        return row is not None

    _run_cli(monkeypatch, database_url, [str(book_dir)])
    assert not index_exists()
    try:
        _run_cli(monkeypatch, database_url, [str(book_dir), "--build-index"])
        assert index_exists()
    finally:
        with psycopg.connect(database_url, autocommit=True) as conn:
            drop_vector_index(conn)
