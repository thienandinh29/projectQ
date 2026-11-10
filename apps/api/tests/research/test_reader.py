import asyncio

import httpx
import pytest

from app.research.agent import detect_license
from app.research.reader import (
    Allowlist,
    Publisher,
    SafeReader,
    SourceError,
    html_content,
    html_text,
    validate_url,
)


async def public(host: str) -> list[str]:
    return ["93.184.216.34"]


def allowlist() -> Allowlist:
    return Allowlist(publishers=[Publisher(name="Book", domains=["books.example"])])


@pytest.mark.parametrize(
    "url",
    [
        "http://books.example/a",
        "https://user:pass@books.example/a",
        "https://books.example:444/a",
        "https://books.example./a",
        "https://books.example/\n",
    ],
)
def test_invalid_urls(url: str) -> None:
    with pytest.raises(SourceError):
        validate_url(url)


def test_domain_boundaries() -> None:
    assert allowlist().publisher("https://sub.books.example/a").name == "Book"
    with pytest.raises(SourceError):
        allowlist().publisher("https://books.example.attacker.example/a")


def test_redirect_is_revalidated_before_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "books.example"
        assert request.extensions["sni_hostname"] == "books.example"
        return httpx.Response(302, headers={"location": "https://evil.example/secret"})

    reader = SafeReader(
        allowlist=allowlist(), resolver=public, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(SourceError, match="danh sách"):
        asyncio.run(reader.fetch("https://books.example/start"))
    assert calls == 1


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.2",
        "::1",
        "169.254.169.254",
        "64:ff9b::7f00:1",
        "64:ff9b::a00:2",
        "::127.0.0.1",
        "::93.184.216.34",
    ],
)
def test_private_dns_never_reaches_transport(address: str) -> None:
    async def resolver(host: str) -> list[str]:
        return [address]

    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("A private IP must never be requested")

    reader = SafeReader(resolver=resolver, transport=httpx.MockTransport(handler))
    with pytest.raises(SourceError, match="nội bộ"):
        asyncio.run(reader.fetch("https://example.com/a"))


def test_body_limit() -> None:
    reader = SafeReader(
        max_bytes=4,
        resolver=public,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"too large")),
    )
    with pytest.raises(SourceError, match="dung lượng"):
        asyncio.run(reader.fetch("https://example.com/a"))


def test_html_excludes_active_content_and_normalizes_unicode() -> None:
    assert (
        html_text("<h1>Học</h1><script>secret</script><p>nội dung</p>".encode()) == "Học\nnội dung"
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("CC BY-SA 4.0", "CC BY-SA 4.0"),
        ("https://creativecommons.org/licenses/by-nc-sa/4.0/", "CC BY-NC-SA 4.0"),
        ("CC0 1.0", "CC0 1.0"),
    ],
)
def test_license_detection(text: str, expected: str) -> None:
    assert detect_license(text) == expected


@pytest.mark.parametrize("text", ["copyright only", "CC BY-ND 4.0", "CC BY-NC-ND 4.0"])
def test_unknown_or_nd_license_rejected(text: str) -> None:
    with pytest.raises(SourceError):
        detect_license(text)


def test_explicit_llm_restriction_requires_review() -> None:
    with pytest.raises(SourceError, match="chấp thuận"):
        detect_license(
            "CC BY-NC-SA 4.0. This book may not be used in the training of large language "
            "models or otherwise be ingested into large language models without prior permission."
        )


def test_full_license_name() -> None:
    assert (
        detect_license(
            "Licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 license."
        )
        == "CC BY-NC-SA 4.0"
    )


def test_book_content_excludes_libretexts_chrome_and_preserves_python_indent() -> None:
    body = b"""<header>Search this book</header><article>
      <section class="other mt-content-container">
        <h2>Functions</h2><p>A function has a body.</p>
        <pre>def greet():
    print("hello")</pre><br><p>After the example.</p>
        <script>ignore()</script>
      </section><footer>CC BY-SA 4.0</footer></article>"""
    text = html_content(body)
    assert "Search this book" not in text and "ignore()" not in text
    assert 'def greet():\n    print("hello")' in text
    assert "After the example." in text
    assert detect_license(html_text(body)) == "CC BY-SA 4.0"


def test_book_content_falls_back_for_other_publishers() -> None:
    assert html_content(b"<p>Textbook</p>") == "Textbook"
