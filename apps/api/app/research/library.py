"""Resumable, bounded same-book HTML acquisition; indexing remains P1/P2's job."""

import asyncio
import hashlib
import json
import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from app.research.agent import canonical_url, detect_license, normalized_path
from app.research.reader import Download, SafeReader, SourceError, html_content, html_text


class Book(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str
    publisher: str
    start_url: str
    license_url: str
    page_prefix: str
    subject_slug: str | None = Field(
        default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80
    )
    subject_name_vi: str | None = Field(default=None, min_length=1)
    subject_name_en: str | None = Field(default=None, min_length=1)
    max_pages: int = Field(default=500, ge=1, le=1000)


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    books: list[Book]


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


_NOT_DECLARED = re.compile(r"shared under (?:a )?not declared license")


def page_license(text: str, book_license: str) -> tuple[str, str]:
    """A page's licence and where it came from (`"page"` or `"book"`).

    The book's licence page has already been verified and the page is inside the same book, so a
    page that states no licence of its own (front matter, back matter, many section pages)
    inherits the book's. A page that states a licence keeps it; ND, AI-restricted and explicitly
    undeclared pages are still refused (`detect_license`).
    """
    try:
        return detect_license(text), "page"
    except SourceError as exc:
        if exc.code == "license_missing" and not _NOT_DECLARED.search(text.casefold()):
            return book_license, "book"
        raise


def load_manifest(path: Path) -> Manifest:
    return Manifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def within_book(url: str, prefix: str) -> bool:
    actual, expected = urlsplit(url), urlsplit(prefix)
    path = normalized_path(actual.path).rstrip("/")
    root = normalized_path(expected.path).rstrip("/")
    return (
        actual.scheme == expected.scheme
        and actual.netloc.lower() == expected.netloc.lower()
        and (path == root or path.startswith(root + "/"))
        and not actual.query
    )


def export_library(manifest: Manifest, root: Path) -> list[dict[str, object]]:
    """Recheck local pages and export only hash/license/scope-valid records for P1 ingestion."""
    reports: list[dict[str, object]] = []
    for book in manifest.books:
        directory = root / book.slug
        if not directory.exists():
            reports.append(
                {"book": book.slug, "accepted_pages": 0, "rejected": [], "missing": True}
            )
            continue
        records: list[dict[str, str]] = []
        seen: set[str] = set()
        rejected: list[dict[str, str]] = []
        paths = sorted(
            path
            for path in directory.glob("*.json")
            if path.name not in {"report.json", "source.json", "document.json"}
        )
        # Bound concurrent disk reads; map preserves stable output order for reproducibility.
        with ThreadPoolExecutor(max_workers=8) as pool:
            for record, rejection in pool.map(partial(_audit_page, book=book), paths):
                if rejection is not None:
                    rejected.append(rejection)
                if record is not None and record["url"] not in seen:
                    seen.add(record["url"])
                    records.append(record)
        temporary = directory / "index.jsonl.tmp"
        with temporary.open("w", encoding="utf-8") as output:
            for record in records:
                output.write(json.dumps(record, ensure_ascii=False) + "\n")
        temporary.replace(directory / "index.jsonl")
        _export_p1(book, directory, records)
        reports.append(
            {
                "book": book.slug,
                "accepted_pages": len(records),
                "rejected": rejected,
                "missing": False,
            }
        )
    return reports


def _export_p1(book: Book, directory: Path, records: list[dict[str, str]]) -> None:
    """Emit P1 SourceMeta/ParsedDocument after the same provenance audit as JSONL.

    Numeric chapter/section names use natural URL order (2 before 10); other names
    retain deterministic URL order. This does not infer prerequisites or a missing TOC.
    Never leave a stale ingestible pair when a new audit accepts no pages.
    """
    if not records:
        for filename in ("source.json", "document.json"):
            (directory / filename).unlink(missing_ok=True)
        return
    ordered = sorted(
        records,
        key=lambda record: re.sub(
            r"\d+", lambda match: f"{int(match.group()):012d}", unquote(record["source_uri"])
        ),
    )
    version = hashlib.sha256(
        "\n".join(
            record["source_uri"]
            + " "
            + record["sha256"]
            + " "
            + hashlib.sha256(record["text"].encode()).hexdigest()
            for record in ordered
        ).encode()
    ).hexdigest()
    source = {
        "subject_slug": book.subject_slug or book.slug,
        "subject_name_vi": book.subject_name_vi or book.title,
        "subject_name_en": book.subject_name_en or book.title,
        "title": book.title,
        "license": "; ".join(sorted({record["license"] for record in records})),
        "url": book.start_url,
        "version": version,
    }
    document = {
        "blocks": [
            {
                "chapter": book.title,
                "section": unquote(urlsplit(record["source_uri"]).path.rsplit("/", 1)[-1])
                or book.title,
                "kind": "text",
                "text": record["text"],
                "source_uri": record["source_uri"],
                "page": None,
            }
            for record in ordered
        ]
    }
    # Publish document first; source.json is P1's discovery marker.
    for filename, payload in (("document.json", document), ("source.json", source)):
        temporary = directory / (filename + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(directory / filename)


def audit_export(book: Book, root: Path) -> dict[str, object]:
    """Inspect P1's real chunker output, never embed or write a database."""
    from app.rag.library import load_book
    from app.rag.notebook import MAX_CHARS
    from app.schemas import ParsedDocument

    folder = root / book.slug
    loaded = load_book(folder)
    document = ParsedDocument.model_validate_json((folder / "document.json").read_text("utf-8"))
    chunks = loaded.chunks
    lengths = sorted(len(chunk.content) for chunk in chunks)
    uris = list(dict.fromkeys(block.source_uri for block in document.blocks))
    expected_uris = sorted(
        uris,
        key=lambda uri: re.sub(r"\d+", lambda match: f"{int(match.group()):012d}", unquote(uri)),
    )
    before = re.sub(r"\s+", "", "".join(block.text for block in document.blocks))
    after = re.sub(r"\s+", "", "".join(chunk.content for chunk in chunks))
    chrome = ("Skip to main content", "Table of Contents menu", "Request Instructor Account")
    checks = {
        "translated_label": loaded.info.subject_name_vi == book.subject_name_vi
        and bool(book.subject_name_vi),
        "subject_slug": loaded.info.subject_slug == (book.subject_slug or book.slug),
        "natural_page_order": uris == expected_uris,
        "non_whitespace_content_retained": before == after,
        "source_uris_retained": set(uris) == {chunk.source_uri for chunk in chunks},
        "source_scope": all(within_book(uri, book.page_prefix) for uri in uris),
        "chunk_size_bound": all(0 < length <= MAX_CHARS for length in lengths),
        "html_pages_have_no_invented_pdf_number": all(chunk.page is None for chunk in chunks),
        "no_site_chrome": not any(
            marker in block.text for marker in chrome for block in document.blocks
        ),
    }
    indexes = sorted({0, len(chunks) // 4, len(chunks) // 2, len(chunks) * 3 // 4, len(chunks) - 1})
    return {
        "book": book.slug,
        "subject_name_vi": loaded.info.subject_name_vi,
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "blocks": len(document.blocks),
        "source_pages": len(uris),
        "chunks": len(chunks),
        "chunk_characters": {
            "min": lengths[0],
            "median": lengths[len(lengths) // 2],
            "p95": lengths[(len(lengths) - 1) * 95 // 100],
            "max": lengths[-1],
            "limit": MAX_CHARS,
            "under_200": sum(n < 200 for n in lengths),
        },
        "page_metadata": "HTML has section URLs; PDF page numbers are not applicable",
        "order_sample": uris[:16],
        "samples": [
            {
                "index": i,
                "source_uri": chunks[i].source_uri,
                "section": chunks[i].section,
                "page": chunks[i].page,
                "characters": len(chunks[i].content),
                "excerpt": chunks[i].content[:500],
            }
            for i in indexes
        ],
        "semantic_retrieval": "pending real indexed TEI evaluation of P1's Vietnamese queries",
    }


def audit_query_labels(folder: Path, queries: Path) -> dict[str, object]:
    """Confirm P1 labels exist in local text, without ranking or tuning held-out cases."""
    from app.rag.evaluate import load_eval_set
    from app.rag.library import load_book
    from app.schemas import Citation

    book, evaluation = load_book(folder), load_eval_set(queries)
    if evaluation.subject != book.info.subject_slug:
        raise ValueError("Query subject does not match the exported library subject")
    passages = [
        Citation(
            chunk_id=f"local-audit-{i}",
            source_title=book.info.title,
            license=book.info.license,
            source_uri=c.source_uri,
            content=c.content,
            page=c.page,
            section=c.section,
            score=0,
        )
        for i, c in enumerate(book.chunks)
    ]
    rows = []
    all_present = True
    expected_sections = confirmed_sections = 0
    for question in evaluation.questions:
        labels = []
        section = re.search(r"\((\d+)\.(\d+)\)", question.note or "")
        prefix = f"{int(section[1])}.{int(section[2]):02d}:" if section else None
        confirmed: dict[str, str | None] = {}
        for criterion in question.relevant:
            matching = [passage for passage in passages if criterion.matches(passage)]
            confirmed.update(
                {
                    passage.source_uri: criterion.contains
                    for passage in matching
                    if prefix and (passage.section or "").startswith(prefix)
                }
            )
            all_present = all_present and bool(matching)
            labels.append(
                {
                    **criterion.model_dump(exclude_none=True),
                    "present": bool(matching),
                    "matching_chunks": len(matching),
                    "sources": [
                        {
                            "source_uri": uri,
                            "sections": sorted(
                                {p.section or "" for p in matching if p.source_uri == uri}
                            ),
                        }
                        for uri in dict.fromkeys(p.source_uri for p in matching)
                    ],
                }
            )
        if prefix:
            expected_sections += 1
            confirmed_sections += bool(confirmed)
        rows.append(
            {
                "id": question.id,
                "question_vi": question.question_vi,
                "p1_note": question.note,
                "labels": labels,
                "expected_section_present": bool(confirmed) if prefix else None,
                "confirmed_relevant": [
                    {"source_uri": uri, "contains": snippet} for uri, snippet in confirmed.items()
                ],
            }
        )
    return {
        "scope": (
            "P1 label presence in audited local text; no vector search, ranking or model tuning"
        ),
        "subject": evaluation.subject,
        "total_queries": len(rows),
        "all_snippets_present": all_present,
        "expected_sections": expected_sections,
        "expected_sections_confirmed": confirmed_sections,
        "held_out_policy": "q06-q10 checked for source existence only; not used to tune k/models",
        "queries": rows,
    }


def _audit_page(path: Path, *, book: Book) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("Invalid metadata object")
        uri, checksum = metadata.get("source_uri"), metadata.get("sha256")
        if not isinstance(uri, str) or not isinstance(checksum, str):
            raise ValueError("Missing provenance")
        if not within_book(uri, book.page_prefix):
            raise ValueError("Source URL outside book scope")
        raw = path.with_suffix(".html").read_bytes()
        if hashlib.sha256(raw).hexdigest() != checksum:
            raise ValueError("Source hash mismatch")
        stored = metadata.get("license")
        if metadata.get("license_origin") == "book" and isinstance(stored, str):
            license_name, _ = page_license(html_text(raw), stored)
        else:
            license_name = detect_license(html_text(raw))
        text = html_content(raw)
        if sum(char.isalnum() for char in text) < 40:
            raise ValueError("Page has insufficient book content")
        return {
            "url": canonical_url(uri),
            "source_uri": uri,
            "title": book.title,
            "publisher": book.publisher,
            "license": license_name,
            "license_url": book.license_url,
            "sha256": checksum,
            "text": text,
        }, None
    except (ValueError, OSError, SourceError) as exc:
        return None, {"file": path.name, "reason": str(exc)}


async def _fetch(reader: SafeReader, url: str) -> Download:
    for attempt in range(3):
        try:
            return await reader.fetch(url)
        except SourceError as exc:
            if not exc.retryable or attempt == 2:
                raise
            await asyncio.sleep(0.2 * 2**attempt)
    raise AssertionError("Unreachable retry state")


async def download_book(book: Book, root: Path, reader: SafeReader) -> dict[str, object]:
    """Store raw HTML and provenance JSON per page, plus a completeness/failure report."""
    if reader.allowlist is None:
        raise ValueError("Library downloads require an allowlist")
    if reader.allowlist.publisher(book.start_url).name != book.publisher:
        raise ValueError("Manifest publisher does not match the allowlist")
    if reader.allowlist.publisher(book.license_url).name != book.publisher:
        raise ValueError("License page must belong to the same publisher")
    if not within_book(book.start_url, book.page_prefix):
        raise ValueError("Start URL is outside the book prefix")
    license_page = await _fetch(reader, book.license_url)
    if reader.allowlist.publisher(license_page.url).name != book.publisher:
        raise ValueError("License page redirected to a different publisher")
    license_name = detect_license(html_text(license_page.body))
    directory = root / book.slug
    directory.mkdir(parents=True, exist_ok=True)
    queue = deque([canonical_url(book.start_url)])
    seen: set[str] = set()
    failures: list[dict[str, str]] = []
    downloaded = cached = 0
    truncated = False
    while queue and len(seen) < book.max_pages:
        url = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        key = hashlib.sha256(url.encode()).hexdigest()
        html_path, metadata_path = directory / f"{key}.html", directory / f"{key}.json"
        try:
            cache_valid = False
            if html_path.exists() and metadata_path.exists():
                raw = html_path.read_bytes()
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    cache_valid = (
                        metadata.get("sha256") == hashlib.sha256(raw).hexdigest()
                        and metadata.get("url") == url
                    )
                except (ValueError, AttributeError):
                    cache_valid = False
            if cache_valid:
                cached += 1
            else:
                response = await _fetch(reader, url)
                if not within_book(response.url, book.page_prefix):
                    raise SourceError("Trang chuyển hướng ra ngoài giáo trình.")
                if response.content_type.partition(";")[0] not in {
                    "text/html",
                    "application/xhtml+xml",
                }:
                    raise SourceError("Trang giáo trình không phải HTML.")
                raw = response.body
                page_licence, licence_origin = page_license(html_text(raw), license_name)
                text = html_content(raw)
                if sum(c.isalnum() for c in text) < 40:
                    raise SourceError("Trang không có đủ văn bản để lập chỉ mục.")
                metadata = {
                    "url": url,
                    "source_uri": response.url,
                    "title": book.title,
                    "publisher": book.publisher,
                    "license": page_licence,
                    "license_origin": licence_origin,
                    "license_url": license_page.url,
                    "text": text,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
                html_path.write_bytes(raw)
                metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
                downloaded += 1
            parser = _Links()
            parser.feed(raw.decode("utf-8", errors="replace"))
            for link in parser.links:
                next_url = canonical_url(urljoin(url, link))
                if (
                    within_book(next_url, book.page_prefix)
                    and next_url not in seen
                    and next_url not in queue
                ):
                    if len(queue) < book.max_pages:
                        queue.append(next_url)
                    else:
                        truncated = True
        except SourceError as exc:
            failures.append({"url": url, "error_vi": str(exc)})
        await asyncio.sleep(0)  # Let worker cancellation/deadlines interrupt between cached pages.
    report: dict[str, object] = {
        "book": book.slug,
        "license": license_name,
        "downloaded": downloaded,
        "cached": cached,
        "failures": failures,
        "discovery_exhausted": not queue and not truncated,
        "complete": not queue and not truncated and not failures,
    }
    (directory / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report
