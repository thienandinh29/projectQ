from io import BytesIO

import pytest
from pypdf import PdfWriter

from app.research.agent import detect_license
from app.research.reader import SourceError, html_content, html_license_text, resource_pdf_links
from app.uploads.reader import read_file


def test_related_book_license_does_not_override_the_document_license() -> None:
    html = b"""<p>This book is released under a
      <a href="http://creativecommons.org/licenses/by/2.5/ca/">
        Creative Commons Attribution License</a>.</p>
      <ul class="related"><li><a href="https://other.example/book">Other book CC-BY-NC-ND</a>
      <li><a href="https://other.example/another">Another</a></a></li></ul>
      <footer>Author attribution</footer>"""
    assert detect_license(html_license_text(html)) == "CC BY 2.5"
    assert "CC-BY-NC-ND" not in html_content(html)
    assert "Author attribution" in html_license_text(html)


@pytest.mark.parametrize(
    "restriction,code",
    [
        ("CC BY-ND 4.0", "license_nd"),
        (
            "Creative Commons license, Attribution-Noncommercial-No\nDerivative Works 2.5 Canada",
            "license_nd",
        ),
        ("This text may not be ingested into large language models", "ai_permission_required"),
    ],
)
def test_own_document_restrictions_are_preserved(restriction: str, code: str) -> None:
    html = (
        '<p>CC BY 4.0</p><ul class="related"><li>Other book CC BY 4.0</li></ul>'
        f"<footer>{restriction}</footer>"
    ).encode()
    with pytest.raises(SourceError) as caught:
        detect_license(html_license_text(html))
    assert caught.value.code == code


def test_unclosed_related_region_keeps_the_full_conservative_license_check() -> None:
    html = b'<p>CC BY 4.0</p><ul class="related"><li>Other work</li><footer>CC BY-ND 4.0</footer>'
    with pytest.raises(SourceError):
        detect_license(html_license_text(html))


def test_author_book_download_links_are_observed_and_not_inherited_by_other_books() -> None:
    root = "https://opendatastructures.org/"
    html = b"""<a href="ods-python.pdf">PDF</a><a href="mcs.pdf">Another book</a>
               <a href="https://other.example/ods-python.pdf">External</a>"""
    assert resource_pdf_links(html, root) == (root + "ods-python.pdf",)
    assert resource_pdf_links(b'<a href="mcs.pdf">Other book</a>', root) == ()
    assert resource_pdf_links(html, "https://other.example/") == ()


def test_research_pdf_sample_is_bounded_and_uploads_still_reject_long_files() -> None:
    buffer = BytesIO()
    writer = PdfWriter()
    for _ in range(201):
        writer.add_blank_page(width=100, height=100)
    writer.write(buffer)
    data = buffer.getvalue()
    with pytest.raises(SourceError, match="200"):
        read_file("book.pdf", data, "https://books.example/book.pdf")
    sampled = read_file("book.pdf", data, "https://books.example/book.pdf", pdf_page_limit=2)
    assert sampled.total_pages == 201
    assert [p.number for p in sampled.pages] == [1, 2]
    assert not sampled.text_ok  # Sampling never makes a scanned/empty file usable.
    with pytest.raises(ValueError):
        read_file("book.pdf", data, "https://books.example/book.pdf", pdf_page_limit=201)
