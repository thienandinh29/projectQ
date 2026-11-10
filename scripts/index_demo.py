"""P2 ordered demo ingest. Run from apps/api; --build-index builds only after golden chunks.

uv run python ../../scripts/index_demo.py --build-index
--preflight validates/chunks every input without database or embedding calls.
Completed books are reused only when every stored chunk and embedding matches.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

import psycopg  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.content.artifacts import load_topic  # noqa: E402
from app.content.repository import Repository  # noqa: E402
from app.db import create_pool  # noqa: E402
from app.rag.embed import TeiEmbedder, to_pgvector  # noqa: E402
from app.rag.ingest import build_index  # noqa: E402
from app.rag.library import Book, ingest_library, load_book  # noqa: E402

ORDER = ("think-python-2e", "logic-critical-thinking", "introductory-statistics")


def already_indexed(conn: psycopg.Connection, book: Book) -> bool:
    rows = conn.execute(
        "select c.content,c.source_uri,c.page,c.embedding is not null from chunks c "
        "join sources s on s.id=c.source_id join subjects b on b.id=s.subject_id "
        "where b.slug=%s and s.title=%s order by c.chunk_index",
        (book.info.subject_slug, book.info.title),
    ).fetchall()
    return rows == [(c.content, c.source_uri, c.page, True) for c in book.chunks]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=ROOT / "data/raw/library")
    parser.add_argument("--golden", type=Path, default=ROOT / "data/golden")
    parser.add_argument("--tei-url", default="http://localhost:8080")
    parser.add_argument("--build-index", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument(
        "--receipt", type=Path, default=ROOT / "data/sources/p2-index-progress.json"
    )
    args = parser.parse_args()
    books = [load_book(args.library / slug) for slug in ORDER]
    golden = [(p.name, load_topic(p)) for p in sorted(args.golden.iterdir()) if p.is_dir()]
    if args.preflight:
        print(
            json.dumps(
                {
                    "books": {b.folder.name: len(b.chunks) for b in books},
                    "golden": {name: len(data[1]) for name, data in golden},
                }
            )
        )
        return
    settings = get_settings()
    receipt: dict[str, object] = {
        "order": [*ORDER, "P4 golden"],
        "completed": [],
        "vector_index_built": False,
    }
    completed: list[dict[str, object]] = []

    def record(stage: str) -> None:
        receipt.update(stage=stage, updated_at=datetime.now(UTC).isoformat(), completed=completed)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(receipt), flush=True)

    embedder = TeiEmbedder(args.tei_url, api_key=settings.tei_api_key.get_secret_value() or None)
    try:
        for book in books:
            record(book.folder.name)
            with psycopg.connect(settings.database_url) as conn:
                reuse = already_indexed(conn, book)
            if not reuse:
                with TemporaryDirectory() as temporary:
                    target = Path(temporary) / book.folder.name
                    target.mkdir()
                    for name in ("source.json", "document.json"):
                        copyfile(book.folder / name, target / name)
                    ingest_library(Path(temporary), settings.database_url, embedder)
            completed.append(
                {"book": book.folder.name, "chunks": len(book.chunks), "reused": reuse}
            )
        record("P4 golden")
        with create_pool(settings.database_url) as pool:
            repository = Repository(lambda: pool)
            for name, (sources, chunks, _, _) in golden:
                repository.save_material(name, sources, chunks)
                with pool.connection() as conn:
                    for chunk in chunks:
                        vector = embedder.embed([f"{chunk.section}\n{chunk.content}"])[0]
                        conn.execute(
                            "update chunks set embedding=%s::halfvec(1024) where id=%s",
                            (to_pgvector(vector), chunk.chunk_id),
                        )
                completed.append({"golden": name, "chunks": len(chunks)})
        if args.build_index:
            record("building-vector-index")
            build_index(settings.database_url)
            receipt["vector_index_built"] = True
        record("complete")
    except Exception as exc:
        receipt["error_type"] = type(exc).__name__
        record("failed")
        raise
    finally:
        embedder.close()


if __name__ == "__main__":
    main()
