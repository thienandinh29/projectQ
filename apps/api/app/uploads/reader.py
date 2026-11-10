"""Bounded PDF/DOCX/HTML text extraction with page provenance; no OCR."""

import asyncio
import unicodedata
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.research.reader import (
    SafeReader,
    SourceError,
    html_content,
    html_license_text,
    resource_chapter_links,
    resource_pdf_links,
)

MAX_BYTES = 20_000_000
MAX_PAGES = 200
MAX_TEXT = 2_000_000
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class Page:
    number: int
    text: str


@dataclass(frozen=True)
class Document:
    source_uri: str
    pages: tuple[Page, ...]
    text_ok: bool
    media_type: str = "text/plain"
    resource_links: tuple[str, ...] = ()
    license_text: str = ""
    chapter_links: tuple[tuple[str, str], ...] = ()
    total_pages: int | None = None


def _document(uri: str, pages: list[Page], media_type: str = "text/plain") -> Document:
    normalized = tuple(Page(p.number, unicodedata.normalize("NFC", p.text)) for p in pages)
    text = "\n".join(p.text for p in normalized)
    if len(text) > MAX_TEXT:
        raise SourceError("Văn bản vượt giới hạn xử lý.")
    useful = sum(char.isalnum() for char in text)
    text_ok = useful >= 40 and text.count("\ufffd") <= max(1, len(text) // 100)
    return Document(uri, normalized, text_ok, media_type)


def read_file(
    filename: str, body: bytes, source_uri: str, *, pdf_page_limit: int | None = None
) -> Document:
    if pdf_page_limit is not None and not 1 <= pdf_page_limit <= MAX_PAGES:
        raise ValueError("PDF page sample must stay within the extraction limit")
    if not body or len(body) > MAX_BYTES:
        raise SourceError("Tệp rỗng hoặc vượt giới hạn 20 MB.")
    suffix = PurePosixPath(filename).suffix.lower()
    try:
        if suffix == ".pdf":
            if not body.startswith(b"%PDF-"):
                raise SourceError("Nội dung tệp không phải PDF.")
            reader = PdfReader(BytesIO(body))
            if reader.is_encrypted:
                raise SourceError("PDF được mã hóa; vui lòng dùng tệp không có mật khẩu.")
            if len(reader.pages) > MAX_PAGES and pdf_page_limit is None:
                raise SourceError("Tài liệu vượt giới hạn 200 trang.")
            pages: list[Page] = []
            size = 0
            for index, page in enumerate(reader.pages[:pdf_page_limit], 1):
                text = page.extract_text() or ""
                size += len(text)
                if size > MAX_TEXT:
                    raise SourceError("Văn bản vượt giới hạn xử lý.")
                pages.append(Page(index, text))
            document = _document(source_uri, pages, "application/pdf")
            return replace(document, total_pages=len(reader.pages)) if pdf_page_limit else document
        if suffix == ".docx":
            with ZipFile(BytesIO(body)) as archive:
                entries = archive.infolist()
                if (
                    len(entries) > 2000
                    or sum(e.file_size for e in entries) > 40_000_000
                    or any(e.flag_bits & 1 for e in entries)
                ):
                    raise SourceError("DOCX vượt giới hạn giải nén hoặc được mã hóa.")
                xml = archive.read("word/document.xml")
            if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise SourceError("Cấu trúc DOCX không được hỗ trợ.")
            root = ElementTree.fromstring(xml)
            # DOCX pagination depends on Word layout; only explicit page breaks are reliable.
            segments: list[list[str]] = [[]]
            for element in root.iter():
                if element.tag == W + "t" and element.text:
                    segments[-1].append(element.text)
                elif element.tag in {W + "tab", W + "br"}:
                    if element.get(W + "type") == "page":
                        segments.append([])
                    else:
                        segments[-1].append("\n")
                elif element.tag == W + "p":
                    segments[-1].append("\n")
                if len(segments) > MAX_PAGES:
                    raise SourceError("Tài liệu vượt giới hạn 200 trang.")
            return _document(
                source_uri,
                [Page(index, "".join(parts)) for index, parts in enumerate(segments, 1)],
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
    except (PdfReadError, BadZipFile, KeyError, ElementTree.ParseError, ValueError):
        raise SourceError("Tệp bị hỏng hoặc không thể đọc văn bản.") from None
    raise SourceError("Chỉ hỗ trợ tệp PDF hoặc DOCX.")


async def read_link(
    url: str, reader: SafeReader | None = None, *, pdf_page_limit: int | None = None
) -> Document:
    download = await (reader or SafeReader()).fetch(url)
    media = download.content_type.partition(";")[0].strip().lower()
    if media == "application/pdf" or download.body.startswith(b"%PDF-"):
        return await asyncio.to_thread(
            read_file, "upload.pdf", download.body, download.url, pdf_page_limit=pdf_page_limit
        )
    if media == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return await asyncio.to_thread(read_file, "upload.docx", download.body, download.url)
    if media not in {"text/html", "application/xhtml+xml", "text/plain"}:
        raise SourceError(
            "Đường dẫn không trả về tài liệu được hỗ trợ.", code="unsupported_document"
        )
    text = (
        download.body.decode("utf-8-sig", errors="replace")
        if media == "text/plain"
        else html_content(download.body)
    )
    return replace(
        _document(download.url, [Page(1, text)], media),
        resource_links=resource_pdf_links(download.body, download.url)
        if media != "text/plain"
        else (),
        license_text=html_license_text(download.body) if media != "text/plain" else "",
        chapter_links=resource_chapter_links(download.body, download.url)
        if media != "text/plain"
        else (),
    )
