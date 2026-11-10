import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.research.library import Book, Manifest, _fetch, download_book, export_library
from app.research.reader import Allowlist, Publisher, SafeReader


def test_library_resume_and_provenance(tmp_path: Path) -> None:
    requests: list[str] = []
    allowlist = Allowlist(publishers=[Publisher(name="Book", domains=["books.example"])])

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        text = "<p>CC BY-SA 4.0 Educational textbook content for learning with citations.</p>"
        if request.url.path == "/book/1":
            text += '<a href="/book/2">Next</a><a href="https://evil.example/">No</a>'
        return httpx.Response(200, text=text, headers={"content-type": "text/html"})

    reader = SafeReader(
        allowlist=allowlist, resolver=resolve, transport=httpx.MockTransport(handler)
    )
    book = Book(
        slug="book",
        title="Book",
        publisher="Book",
        start_url="https://books.example/book/1",
        license_url="https://books.example/license",
        page_prefix="https://books.example/book/",
    )
    first = asyncio.run(download_book(book, tmp_path, reader))
    assert first["downloaded"] == 2 and first["complete"]
    assert len(list((tmp_path / "book").glob("*.html"))) == 2
    requests.clear()
    second = asyncio.run(download_book(book, tmp_path, reader))
    assert second["cached"] == 2
    assert requests == ["/license"]
    # A corrupted cached file must be downloaded again.
    next((tmp_path / "book").glob("*.html")).write_bytes(b"corrupt")
    third = asyncio.run(download_book(book, tmp_path, reader))
    assert third["downloaded"] == 1
    report = export_library(Manifest(books=[book]), tmp_path)
    assert report[0]["accepted_pages"] == 2
    assert len((tmp_path / "book/index.jsonl").read_text(encoding="utf-8").splitlines()) == 2
    source = json.loads((tmp_path / "book/source.json").read_text(encoding="utf-8"))
    document = json.loads((tmp_path / "book/document.json").read_text(encoding="utf-8"))
    assert source["subject_slug"] == "book" and source["license"] == "CC BY-SA 4.0"
    assert len(document["blocks"]) == 2
    assert all(block["source_uri"].startswith(book.page_prefix) for block in document["blocks"])
    repeated = export_library(Manifest(books=[book]), tmp_path)
    assert repeated[0]["accepted_pages"] == 2 and repeated[0]["rejected"] == []
    # Index export must never trust metadata when the source bytes have changed.
    next((tmp_path / "book").glob("*.html")).write_bytes(b"tampered")
    audited = export_library(Manifest(books=[book]), tmp_path)
    assert audited[0]["accepted_pages"] == 1 and audited[0]["rejected"]
    assert len(json.loads((tmp_path / "book/document.json").read_text())["blocks"]) == 1
    for page in (tmp_path / "book").glob("*.html"):
        page.write_bytes(b"tampered")
    assert export_library(Manifest(books=[book]), tmp_path)[0]["accepted_pages"] == 0
    assert not (tmp_path / "book/source.json").exists()
    assert not (tmp_path / "book/document.json").exists()


def test_transient_http_error_is_retried() -> None:
    calls = 0

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429 if calls == 1 else 200, text="ok")

    reader = SafeReader(resolver=resolve, transport=httpx.MockTransport(handler))
    assert asyncio.run(_fetch(reader, "https://books.example/page")).body == b"ok"
    assert calls == 2


def test_export_keeps_numeric_chapters_and_sections_in_reading_order(tmp_path: Path) -> None:
    from app.rag.library import load_book
    from app.research.library import _export_p1

    book = Book(
        slug="book",
        title="Book",
        publisher="Publisher",
        start_url="https://books.example/book",
        license_url="https://books.example/license",
        page_prefix="https://books.example/book",
    )
    paths = ["10:_Chapter", "2:_Chapter/10:_Section", "2:_Chapter/2:_Section", "2:_Chapter"]
    records = [
        {
            "source_uri": f"https://books.example/book/{path}",
            "text": f"Paragraph in {path}",
            "license": "CC BY 4.0",
            "sha256": path,
        }
        for path in paths
    ]
    _export_p1(book, tmp_path, records)
    loaded = load_book(tmp_path)
    assert [chunk.source_uri.rsplit("/book/", 1)[1] for chunk in loaded.chunks] == [
        "2:_Chapter",
        "2:_Chapter/2:_Section",
        "2:_Chapter/10:_Section",
        "10:_Chapter",
    ]


def test_manifest_has_explicit_translated_subject_labels() -> None:
    from app.research.library import load_manifest

    manifest = load_manifest(Path(__file__).resolve().parents[4] / "data/sources/library.yaml")
    assert len(manifest.books) == 8
    for book in manifest.books:
        assert book.subject_slug == book.slug
        assert book.subject_name_vi and book.subject_name_vi != book.slug
        assert book.subject_name_en


def test_content_changes_invalidate_export_version(tmp_path: Path) -> None:
    from app.research.library import _export_p1

    book = Book(
        slug="book",
        title="Book",
        publisher="Publisher",
        start_url="https://books.example/book",
        license_url="https://books.example/license",
        page_prefix="https://books.example/book",
    )
    record = {"source_uri": book.start_url, "text": "Old", "license": "CC BY 4.0", "sha256": "raw"}
    _export_p1(book, tmp_path, [record])
    before = json.loads((tmp_path / "source.json").read_text())["version"]
    record["text"] = "New extraction from unchanged raw HTML"
    _export_p1(book, tmp_path, [record])
    assert json.loads((tmp_path / "source.json").read_text())["version"] != before


def test_pre_index_audit_reports_real_chunk_sizes_and_source_retention(tmp_path: Path) -> None:
    from app.research.library import _export_p1, audit_export

    book = Book(
        slug="book",
        title="Book",
        publisher="Publisher",
        subject_slug="book",
        subject_name_vi="Sách",
        subject_name_en="Book",
        start_url="https://books.example/book",
        license_url="https://books.example/license",
        page_prefix="https://books.example/book",
    )
    folder = tmp_path / book.slug
    folder.mkdir()
    _export_p1(
        book,
        folder,
        [
            {
                "source_uri": book.start_url,
                "text": "Reading content. " * 300,
                "license": "CC BY 4.0",
                "sha256": "raw",
            }
        ],
    )
    report = audit_export(book, tmp_path)
    assert report["status"] == "pass" and report["source_pages"] == 1
    assert report["chunks"] == 3
    document = json.loads((folder / "document.json").read_text())
    document["blocks"][0]["text"] += " Skip to main content"
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    assert audit_export(book, tmp_path)["status"] == "fail"


def test_p1_label_audit_requires_matching_text_and_page(tmp_path: Path) -> None:
    from app.research.library import _export_p1, audit_query_labels

    book = Book(
        slug="book",
        title="Book",
        publisher="Publisher",
        start_url="https://books.example/book",
        license_url="https://books.example/license",
        page_prefix="https://books.example/book",
    )
    _export_p1(
        book,
        tmp_path,
        [
            {
                "source_uri": book.start_url,
                "text": "A boolean expression.",
                "license": "CC BY 4.0",
                "sha256": "raw",
            }
        ],
    )
    queries = tmp_path / "queries.yaml"
    data: dict[str, Any] = {
        "subject": "book",
        "questions": [
            {
                "id": "q01",
                "question_vi": "Boolean?",
                "relevant": [{"contains": "BOOLEAN expression", "source_uri": book.start_url}],
            }
        ],
    }
    queries.write_text(json.dumps(data), encoding="utf-8")
    assert audit_query_labels(tmp_path, queries)["all_snippets_present"]
    data["questions"][0]["relevant"][0]["source_uri"] = "https://books.example/wrong"
    queries.write_text(json.dumps(data), encoding="utf-8")
    assert not audit_query_labels(tmp_path, queries)["all_snippets_present"]


def test_pages_without_their_own_licence_inherit_the_verified_book_licence(tmp_path: Path) -> None:
    """Cause of the "Chưa xác định được giấy phép" failures: pages that print no licence."""
    allowlist = Allowlist(publishers=[Publisher(name="Book", domains=["books.example"])])

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    body = "Educational textbook content for learning with citations and enough words."
    pages = {
        "/license": "<p>This book is shared under a CC BY-SA 4.0 license.</p>",
        "/book/1": f"<p>{body}</p>" + "".join(f'<a href="/book/{n}">{n}</a>' for n in "234"),
        "/book/2": f"<p>{body} This page is licensed CC BY 4.0.</p>",
        "/book/3": f"<p>{body} This page is shared under a not declared license.</p>",
        "/book/4": f"<p>{body} Licensed CC BY-ND 4.0.</p>",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text=pages[request.url.path], headers={"content-type": "text/html"}
        )

    reader = SafeReader(
        allowlist=allowlist, resolver=resolve, transport=httpx.MockTransport(handler)
    )
    book = Book(
        slug="book",
        title="Book",
        publisher="Book",
        start_url="https://books.example/book/1",
        license_url="https://books.example/license",
        page_prefix="https://books.example/book/",
    )
    report = asyncio.run(download_book(book, tmp_path, reader))
    assert report["downloaded"] == 2
    failures = report["failures"]
    assert isinstance(failures, list)
    failed = {f["url"].rsplit("/", 1)[-1] for f in failures}
    assert failed == {"3", "4"}  # explicitly undeclared and ND are still refused
    stored = {
        json.loads(p.read_text(encoding="utf-8"))["url"].rsplit("/", 1)[-1]: json.loads(
            p.read_text(encoding="utf-8")
        )
        for p in (tmp_path / "book").glob("*.json")
        if p.name != "report.json"
    }
    assert (stored["1"]["license"], stored["1"]["license_origin"]) == ("CC BY-SA 4.0", "book")
    assert (stored["2"]["license"], stored["2"]["license_origin"]) == ("CC BY 4.0", "page")
    exported = export_library(Manifest(books=[book]), tmp_path)
    assert exported[0]["accepted_pages"] == 2
