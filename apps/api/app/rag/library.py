"""Index the textbook library: every book folder holds a `source.json` and a `document.json`.

    <library>/<book-slug>/source.json     SourceMeta     (who it is, its licence)    P3's builder
    <library>/<book-slug>/document.json   ParsedDocument (blocks in reading order)   P3's readers

Usage, from apps/api (P2 runs this on the machine that hosts the embedding server):
    uv run python -m app.rag.library ../../data/library \
        --tei-url http://localhost:8080 --build-index

Everything is read and validated before anything is embedded, so a bad licence or an empty
document stops the run up front instead of leaving a half-indexed library. Re-running replaces
each book's chunks. Build the vector index once, after the last book (`--build-index`).
"""

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg
from pydantic import ValidationError

from app.config import get_settings
from app.rag.chunker import chunk_document
from app.rag.embed import Embedder
from app.rag.ingest import add_embedder_args, build_index, embedder_from_args
from app.rag.notebook import MAX_CHARS, Chunk
from app.rag.store import SourceInfo, replace_chunks, upsert_source
from app.schemas import ParsedDocument, SourceMeta


@dataclass(frozen=True)
class Book:
    folder: Path
    info: SourceInfo
    chunks: list[Chunk]


def _read(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"{path} is missing") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc


def _explain(exc: ValidationError) -> str:
    """A validation error as one plain line: `field: problem; field: problem`."""
    parts = []
    for error in exc.errors():
        where = ".".join(str(x) for x in error["loc"])
        message = error["msg"].removeprefix("Value error, ")
        parts.append(f"{where}: {message}" if where else message)
    return "; ".join(parts)


def load_book(folder: Path, *, max_chars: int = MAX_CHARS) -> Book:
    """Read, validate and chunk one book folder."""
    try:
        meta = SourceMeta.model_validate(_read(folder / "source.json"))
        doc = ParsedDocument.model_validate(_read(folder / "document.json"))
    except ValidationError as exc:
        raise ValueError(f"{folder.name}: {_explain(exc)}") from exc
    chunks = chunk_document(doc, max_chars=max_chars)
    if not chunks:
        raise ValueError(f"{folder.name}: the document has no text")
    info = SourceInfo(
        subject_slug=meta.subject_slug,
        subject_name_vi=meta.subject_name_vi,
        subject_name_en=meta.subject_name_en,
        title=meta.title,
        author=meta.author,
        license=meta.license,
        url=meta.url,
        version=meta.version,
    )
    return Book(folder, info, chunks)


def load_library(library: Path, *, max_chars: int = MAX_CHARS) -> list[Book]:
    folders = sorted(p for p in library.iterdir() if (p / "source.json").exists())
    if not folders:
        raise ValueError(f"no book folders (with a source.json) in {library}")
    return [load_book(f, max_chars=max_chars) for f in folders]


def _progress(title: str) -> Callable[[int, int], None]:
    """Prints how far a book's indexing got and an estimate of the time left."""
    began = time.monotonic()

    def report(done: int, total: int) -> None:
        rate = done / max(time.monotonic() - began, 1e-9)
        left_min = (total - done) / rate / 60 if rate else 0.0
        print(
            f"  {title}: {done}/{total} chunks, {rate:.1f}/s, about {left_min:.0f} min left",
            file=sys.stderr,
            flush=True,
        )

    return report


def ingest_library(
    library: Path, database_url: str, embedder: Embedder, *, max_chars: int = MAX_CHARS
) -> dict[str, int]:
    """Index every book; returns chunks written per book title."""
    books = load_library(library, max_chars=max_chars)  # validate all before embedding any
    written: dict[str, int] = {}
    with psycopg.connect(database_url) as conn:
        for book in books:
            source_id = upsert_source(conn, book.info)
            written[book.info.title] = replace_chunks(
                conn, source_id, book.chunks, embedder, on_progress=_progress(book.info.title)
            )
            print(f"{book.info.title}: {written[book.info.title]} chunks", file=sys.stderr)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("library", type=Path)
    add_embedder_args(parser)
    args = parser.parse_args(argv)
    embedder = embedder_from_args(args, parser)

    database_url = get_settings().database_url
    try:
        written = ingest_library(args.library, database_url, embedder)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Indexed {len(written)} books, {sum(written.values())} chunks", file=sys.stderr)
    if args.build_index:
        build_index(database_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
