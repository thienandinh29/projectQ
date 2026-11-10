import pytest

from app.research.agent import detect_license
from app.research.library import within_book
from app.research.reader import SourceError, html_text


def test_footer_license_evidence_is_kept() -> None:
    text = html_text(
        b"<main>Chapter content</main><footer>Shared under a "
        b'<a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a>'
        b"</footer>"
    )
    assert detect_license(text) == "CC BY-SA 4.0"


def test_thumbnail_license_is_not_a_grant_for_an_undeclared_page() -> None:
    with pytest.raises(SourceError, match="công bố"):
        detect_license("Thumbnail CC BY 4.0. This page is shared under a not declared license.")


def test_book_boundary_handles_encoded_paths_and_excludes_siblings() -> None:
    root = "https://books.example/Book_(Author)"
    assert within_book("https://books.example/Book_%28Author%29/01:_Intro", root)
    assert not within_book("https://books.example/Book_(Author)_Other/1", root)
    assert not within_book("https://evil.example/Book_(Author)/1", root)
    assert not within_book(root + "?action=edit", root)
    assert not within_book(root + "/%2e%2e/OtherBook/1", root)
    assert within_book("https://books.example/Map%3A_Book/1", "https://books.example/Map%253A_Book")
