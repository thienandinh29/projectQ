"""Ingest Think Python 3e notebooks into chunks + embeddings.

Usage, from apps/api:
    # with the TEI server on the GPU machine (no PyTorch needed here)
    uv run python -m app.rag.ingest ../../data/raw/thinkpython \
        --tei-url http://<host>:8080 --build-index
    # or the local model (after `uv sync --extra embed`; uses the GPU if PyTorch can see one)
    uv run python -m app.rag.ingest ../../data/raw/thinkpython --embedder local
Build the vector index once, after the last book (`--build-index`).
"""

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import psycopg

from app.config import get_settings
from app.rag.embed import Embedder
from app.rag.notebook import Chunk, parse_notebook
from app.rag.store import SourceInfo, build_vector_index, replace_chunks, upsert_source

THINK_PYTHON = SourceInfo(
    subject_slug="python",
    subject_name_vi="Lập trình Python",
    subject_name_en="Python programming",
    title="Think Python, 3rd edition",
    author="Allen B. Downey",
    license="CC BY-NC-SA 4.0 (text), MIT (code)",
    url="https://allendowney.github.io/ThinkPython/",
    version="unknown",
)

CHAPTER_FILE = re.compile(r"chap(\d{2})\.ipynb$")


def load_chunks(directory: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("chap*.ipynb")):
        match = CHAPTER_FILE.search(path.name)
        if match is None:
            continue
        notebook = json.loads(path.read_text(encoding="utf-8"))
        chunks.extend(parse_notebook(notebook, int(match.group(1))))
    return chunks


def ingest(directory: Path, database_url: str, embedder: Embedder) -> int:
    sha_file = directory / "SOURCE_SHA"
    version = sha_file.read_text().strip() if sha_file.exists() else "unknown"
    chunks = load_chunks(directory)
    if not chunks:
        raise ValueError(f"no chapter notebooks found in {directory}")
    info = replace(THINK_PYTHON, version=version)
    with psycopg.connect(database_url) as conn:
        source_id = upsert_source(conn, info)
        return replace_chunks(conn, source_id, chunks, embedder)


def add_embedder_args(parser: argparse.ArgumentParser) -> None:
    """The embedder and index options shared by every indexing command."""
    # With TEI_URL set the default is the TEI server (fast, and the same model the API queries);
    # without it, the local model, which uses the GPU if PyTorch can see one.
    default_backend = "tei" if os.environ.get("TEI_URL") else "local"
    parser.add_argument("--embedder", choices=["tei", "local"], default=default_backend)
    parser.add_argument("--tei-url", default=os.environ.get("TEI_URL"))
    parser.add_argument("--api-key", default=os.environ.get("TEI_API_KEY"))
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="build the HNSW index once loading is done (run it after the last book, not each one)",
    )


def embedder_from_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Embedder:
    if args.embedder == "tei" and not args.tei_url:
        parser.error("--embedder tei needs --tei-url (or the TEI_URL environment variable)")
    from app.rag.embed import make_embedder

    return make_embedder(args.embedder, tei_url=args.tei_url, api_key=args.api_key)


def build_index(database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as conn:
        build_vector_index(conn)
    print("Built the vector index", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    add_embedder_args(parser)
    args = parser.parse_args(argv)
    embedder = embedder_from_args(args, parser)

    database_url = get_settings().database_url
    count = ingest(args.directory, database_url, embedder)
    print(f"Ingested {count} chunks from {args.directory}", file=sys.stderr)
    if args.build_index:
        build_index(database_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
