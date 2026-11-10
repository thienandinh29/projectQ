from io import BytesIO
from zipfile import ZipFile

import pytest
from pypdf import PdfWriter

from app.research.reader import SourceError
from app.uploads.reader import MAX_BYTES, read_file


def docx(xml: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return buffer.getvalue()


def test_docx_preserves_explicit_pages_and_unicode() -> None:
    text = "Kiến thức nền tảng giúp người học hiểu và vận dụng bài học."
    data = docx(
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:body><w:p><w:r><w:t>{text}</w:t><w:br w:type="page"/>'
        f"<w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    document = read_file("syllabus.docx", data, "storage/syllabus.docx")
    assert document.text_ok
    assert len(document.pages) == 2
    assert document.pages[1].number == 2
    assert text in document.pages[0].text
    assert document.source_uri == "storage/syllabus.docx"
    assert document.media_type.endswith("wordprocessingml.document")


def test_scanned_pdf_returns_text_not_ok() -> None:
    buffer = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(buffer)
    document = read_file("scan.pdf", buffer.getvalue(), "storage/scan.pdf")
    assert len(document.pages) == 1
    assert not document.text_ok
    assert document.media_type == "application/pdf"


def test_pdf_page_limit() -> None:
    buffer = BytesIO()
    writer = PdfWriter()
    for _ in range(201):
        writer.add_blank_page(width=100, height=100)
    writer.write(buffer)
    with pytest.raises(SourceError, match="200 trang"):
        read_file("big.pdf", buffer.getvalue(), "storage/big.pdf")


@pytest.mark.parametrize(
    "filename,body",
    [
        ("bad.pdf", b"not a pdf"),
        ("bad.docx", b"not a zip"),
        ("script.exe", b"executable"),
        ("empty.pdf", b""),
    ],
)
def test_invalid_files(filename: str, body: bytes) -> None:
    with pytest.raises(SourceError):
        read_file(filename, body, "storage/file")


def test_oversized_file() -> None:
    with pytest.raises(SourceError, match="20 MB"):
        read_file("big.pdf", b"x" * (MAX_BYTES + 1), "storage/big.pdf")


def test_docx_dtd_rejected() -> None:
    with pytest.raises(SourceError, match="không được hỗ trợ"):
        read_file("bad.docx", docx('<!DOCTYPE x [<!ENTITY a "x">]><x/>'), "storage/bad.docx")
