"""Fetch catalogue books into library folders (v2, M0).

Usage, from apps/api:
    uv run python -m app.sources.fetch ../../data/sources/catalog.yaml --out <library-dir>
    uv run python -m app.sources.fetch <catalog.yaml> --out <dir> --only python-openstax

Each OpenStax book is a shallow, blob-less, sparse git checkout (collection XML and page CNXML,
no media), so a book costs a few megabytes and works wherever git can reach GitHub. Each book
folder is validated with the same `load_book` the indexer uses before the run reports success.
Indexing stays `app.rag.library` (it needs the embedding server).
"""

import argparse
import json
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from app.sources.licence import LicenceError, is_non_commercial
from app.sources.openstax import Page, parse_collection, parse_module

Slug = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)


class CatalogBook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Slug  # library folder and subject slug
    adapter: Literal["openstax_git"]
    publisher: str = Field(min_length=1)
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")  # owner/name on GitHub
    collection: str = Slug  # the collection slug inside the repository (bundles hold several books)
    ref: str = "main"
    subject_name_vi: str = Field(min_length=1)
    subject_name_en: str = Field(min_length=1)
    # Vietnamese and English terms for topic matching (M1).
    keywords: list[str] = Field(default_factory=list)


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    books: list[CatalogBook] = Field(min_length=1)


def load_catalog(path: Path) -> Catalog:
    return Catalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class BuiltBook:
    slug: str
    commit: str
    licence: str
    chapters: int
    pages: int
    blocks: int
    objectives: int
    missing_modules: tuple[str, ...]
    skipped_front_matter: int


def build_openstax(book: CatalogBook, checkout: Path, commit: str, out: Path) -> BuiltBook:
    """Turn an OpenStax checkout into `<out>/<slug>/{source,document,outline}.json`."""
    collection_path = checkout / "collections" / f"{book.collection}.collection.xml"
    if not collection_path.exists():
        found = sorted(p.name for p in (checkout / "collections").glob("*.collection.xml"))
        raise ValueError(f"{book.slug}: no collection {book.collection!r}; found {found}")
    collection = parse_collection(collection_path.read_bytes())
    blocks: list[dict[str, object]] = []
    outline: list[dict[str, object]] = []
    missing: list[str] = []
    pages = objectives = 0
    for chapter in collection.chapters:
        entry: dict[str, object] = {
            "chapter_no": chapter.number,
            "chapter": chapter.title,
            "unit": chapter.unit,
            "pages": [],
        }
        for module in chapter.modules:
            path = checkout / "modules" / module / "index.cnxml"
            if not path.exists():
                missing.append(module)
                continue
            uri = f"https://github.com/{book.repo}/blob/{commit}/modules/{module}/index.cnxml"
            page: Page = parse_module(
                path.read_bytes(),
                module=module,
                chapter_no=chapter.number,
                chapter=chapter.title,
                source_uri=uri,
            )
            pages += 1
            objectives += len(page.objectives)
            blocks.extend(b.to_contract() for b in page.blocks)
            page_list = entry["pages"]
            assert isinstance(page_list, list)
            page_list.append(
                {
                    "module": module,
                    "title": page.title,
                    "objectives": page.objectives,
                    "source_uri": uri,
                }
            )
        outline.append(entry)
    if missing:
        raise ValueError(f"{book.slug}: modules listed in the collection are missing: {missing}")
    folder = out / book.slug
    folder.mkdir(parents=True, exist_ok=True)
    source = {
        "subject_slug": book.slug,
        "subject_name_vi": book.subject_name_vi,
        "subject_name_en": book.subject_name_en,
        "title": collection.title,
        "author": book.publisher,
        "license": collection.licence,
        "url": f"https://github.com/{book.repo}/tree/{commit}",
        "version": commit,
    }
    _write(folder / "source.json", source)
    _write(folder / "document.json", {"blocks": blocks})
    _write(
        folder / "outline.json",
        {
            "book": book.slug,
            "publisher": book.publisher,
            "title": collection.title,
            "licence": collection.licence,
            "licence_url": collection.licence_url,
            "commit": commit,
            "keywords": book.keywords,
            "chapters": outline,
        },
    )
    return BuiltBook(
        slug=book.slug,
        commit=commit,
        licence=collection.licence,
        chapters=len(collection.chapters),
        pages=pages,
        blocks=len(blocks),
        objectives=objectives,
        missing_modules=tuple(missing),
        skipped_front_matter=len(collection.front_matter),
    )


def _write(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _git(*args: str, cwd: Path | None = None, timeout: int = 600) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {done.stderr.strip()[-400:]}")
    return done.stdout.strip()


def checkout_openstax(book: CatalogBook, dest: Path) -> str:
    """Sparse checkout of collection XML and page CNXML; returns the commit SHA."""
    url = f"https://github.com/{book.repo}.git"
    _git(
        "clone", "--depth", "1", "--filter=blob:none", "--no-checkout",
        "--branch", book.ref, url, str(dest),
    )  # fmt: skip
    _git("sparse-checkout", "init", "--no-cone", cwd=dest)
    _git("sparse-checkout", "set", "/collections/", "/modules/*/index.cnxml", cwd=dest)
    _git("checkout", cwd=dest)
    return _git("rev-parse", "HEAD", cwd=dest)


def fetch(catalog: Catalog, out: Path, only: Sequence[str] = ()) -> list[dict[str, object]]:
    from app.rag.library import load_book  # validates exactly as the indexer will

    rows: list[dict[str, object]] = []
    for book in catalog.books:
        if only and book.slug not in only:
            continue
        row: dict[str, object] = {"book": book.slug, "publisher": book.publisher, "repo": book.repo}
        try:
            with tempfile.TemporaryDirectory(prefix=f"{book.slug}-") as tmp:
                checkout = Path(tmp) / "repo"
                commit = checkout_openstax(book, checkout)
                built = build_openstax(book, checkout, commit, out)
            loaded = load_book(out / book.slug)
            row |= {
                "outcome": "ok",
                "commit": built.commit,
                "licence": built.licence,
                "non_commercial": is_non_commercial(built.licence),
                "chapters": built.chapters,
                "pages": built.pages,
                "blocks": built.blocks,
                "chunks": len(loaded.chunks),
                "objectives": built.objectives,
                "skipped_front_matter": built.skipped_front_matter,
            }
        except LicenceError as exc:
            row |= {"outcome": "licence_refused", "error": str(exc)}
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            row |= {"outcome": "failed", "error": str(exc)}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="library folder to write into")
    parser.add_argument("--only", nargs="*", default=[], help="book slugs to fetch (default: all)")
    parser.add_argument("--report", type=Path, help="write the run report as JSON here")
    args = parser.parse_args(argv)
    rows = fetch(load_catalog(args.catalog), args.out, args.only)
    if args.report:
        _write(args.report, {"books": rows})
    return 0 if rows and all(r["outcome"] == "ok" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
