"""HTTPS reader with allowlist checks, pinned public DNS and bounded redirects/body."""

import asyncio
import ipaddress
import re
import socket
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field


class SourceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        code: str = "source_error",
        action_vi: str = "",
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.code = code
        self.action_vi = action_vi


class Publisher(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    domains: list[str] = Field(min_length=1)
    fallback_only: bool = False


class Allowlist(BaseModel):
    model_config = ConfigDict(extra="forbid")
    publishers: list[Publisher]
    allow_public: bool = False

    def publisher(self, url: str, *, include_fallback: bool = False) -> Publisher:
        host = validate_url(url)
        for publisher in self.publishers:
            if publisher.fallback_only and not include_fallback:
                continue
            if any(host == domain or host.endswith("." + domain) for domain in publisher.domains):
                return publisher
        if self.allow_public:
            if any(
                p.fallback_only and any(host == d or host.endswith("." + d) for d in p.domains)
                for p in self.publishers
            ):
                raise SourceError("Nguồn này chỉ được dùng làm tham khảo bổ sung.")
            # Conservative publisher grouping: shared-hosting subdomains count as one source owner.
            domain = ".".join(host.split(".")[-2:])
            return Publisher(name=domain, domains=[domain])
        raise SourceError("Nguồn này không nằm trong danh sách được phép.")


def load_allowlist(path: Path | None = None) -> Allowlist:
    path = path or Path(__file__).resolve().parents[4] / "data/sources/allowlist.yaml"
    return Allowlist.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def validate_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            raise ValueError
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        if host.endswith(".") or any(ord(char) < 33 for char in url) or "\\" in url:
            raise ValueError
        return host
    except (ValueError, UnicodeError):
        raise SourceError("Đường dẫn HTTPS không hợp lệ.") from None


async def resolve_public(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        records = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise SourceError("Không thể phân giải địa chỉ nguồn.", retryable=True) from None
    return list(dict.fromkeys(str(record[4][0]) for record in records))


@dataclass(frozen=True)
class Download:
    url: str
    body: bytes
    content_type: str


_TRANSITION_NETWORKS = (
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("::/96"),
)


def _public_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_global and not any(
        ip.version == network.version and ip in network for network in _TRANSITION_NETWORKS
    )


class SafeReader:
    def __init__(
        self,
        *,
        allowlist: Allowlist | None = None,
        max_bytes: int = 20_000_000,
        timeout: float = 30,
        max_redirects: int = 4,
        resolver: Callable[[str], Awaitable[list[str]]] = resolve_public,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if max_bytes < 1 or timeout <= 0 or max_redirects < 0:
            raise ValueError("Invalid HTTP reader limits")
        self.allowlist = allowlist
        self.max_bytes, self.timeout, self.max_redirects = max_bytes, timeout, max_redirects
        self.resolver, self.transport = resolver, transport

    async def fetch(self, url: str) -> Download:
        try:
            async with (
                asyncio.timeout(self.timeout),
                httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
            ):
                for _ in range(self.max_redirects + 1):
                    host = validate_url(url)
                    if self.allowlist:
                        self.allowlist.publisher(url)
                    addresses = await self.resolver(host)
                    if not addresses or any(not _public_address(address) for address in addresses):
                        raise SourceError("Không được truy cập địa chỉ mạng nội bộ.")
                    # Connect to the checked IP, retaining TLS SNI/certificate validation.
                    target = httpx.URL(url).copy_with(host=addresses[0])
                    async with client.stream(
                        "GET",
                        target,
                        headers={"Host": host, "User-Agent": "NodeTrail/0.1 (educational reader)"},
                        extensions={"sni_hostname": host},
                    ) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("location")
                            if not location:
                                raise SourceError("Nguồn chuyển hướng không hợp lệ.")
                            url = urljoin(url, location)
                            continue
                        response.raise_for_status()
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > self.max_bytes:
                                raise SourceError("Tài liệu vượt giới hạn dung lượng.")
                        return Download(url, bytes(body), response.headers.get("content-type", ""))
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise SourceError(
                f"Nguồn trả về lỗi HTTP {status}.",
                retryable=status in {408, 429} or status >= 500,
                code=f"source_http_{status}",
            ) from None
        except (httpx.HTTPError, TimeoutError):
            raise SourceError(
                "Không thể tải tài liệu trong thời gian cho phép.", retryable=True
            ) from None
        raise SourceError("Nguồn chuyển hướng quá nhiều lần.")


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "noscript", "svg"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr", "pre"}:
            self.parts.append("\n")
        if tag == "a" and not self.hidden:
            for name, value in attrs:
                if (
                    name == "href"
                    and value
                    and value.startswith(
                        (
                            "https://creativecommons.org/licenses/",
                            "https://creativecommons.org/publicdomain/",
                            "http://creativecommons.org/licenses/",
                            "http://creativecommons.org/publicdomain/",
                        )
                    )
                ):
                    self.parts.append(" " + value + " ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "noscript", "svg"}:
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in {"p", "div", "li", "h1", "h2", "h3", "tr", "pre"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def html_text(body: bytes) -> str:
    parser = _HTMLText()
    parser.feed(body.decode("utf-8-sig", errors="replace"))
    text = "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())
    return unicodedata.normalize("NFC", text)


def html_license_text(body: bytes) -> str:
    """Keep document restrictions, excluding explicitly labelled related-resource lists."""

    class LicenseText(_HTMLText):
        def __init__(self) -> None:
            super().__init__()
            self.related: list[str] = []
            self.malformed = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            classes = (dict(attrs).get("class") or "").split()
            if self.related or (tag in {"ul", "ol", "aside"} and "related" in classes):
                if tag not in _BookContent._void:
                    self.related.append(tag)
                return
            super().handle_starttag(tag, attrs)

        def handle_endtag(self, tag: str) -> None:
            if self.related:
                if tag in self.related:
                    last = len(self.related) - 1 - self.related[::-1].index(tag)
                    del self.related[last:]
                elif tag in {
                    "html",
                    "body",
                    "main",
                    "footer",
                    "article",
                    "section",
                    "div",
                    "aside",
                    "ul",
                    "ol",
                }:
                    self.malformed = True
                return
            super().handle_endtag(tag)

        def handle_data(self, data: str) -> None:
            if not self.related:
                super().handle_data(data)

    parser = LicenseText()
    parser.feed(body.decode("utf-8-sig", errors="replace"))
    if parser.related or parser.malformed:
        return html_text(body)
    return unicodedata.normalize(
        "NFC",
        "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip()),
    )


def resource_chapter_links(body: bytes, base_url: str) -> tuple[tuple[str, str], ...]:
    """Observed chapters from book contents or MIT notes, never guessed URLs."""
    parsed = urlsplit(base_url)
    parts = parsed.path.strip("/").split("/")
    mit_index = (
        parsed.hostname == "ocw.mit.edu"
        and len(parts) == 4
        and parts[0] == "courses"
        and parts[2] == "pages"
        and parts[3] in {"open-textbook", "lecture-notes"}
    )
    book_index = len(parts) == 1 and bool(parts[0])
    if parsed.scheme != "https" or not (mit_index or book_index):
        return ()

    class Chapters(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.links: dict[str, str] = {}
            self.active: str | None = None

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag != "a":
                return
            self.active = None
            target = urljoin(base_url, dict(attrs).get("href") or "")
            p = urlsplit(target)
            segments = p.path.strip("/").split("/")
            if (
                p.scheme == "https"
                and p.netloc == parsed.netloc
                and (
                    (
                        mit_index
                        and len(segments) == 4
                        and segments[:3] == ["courses", parts[1], "resources"]
                        and (parts[3] == "lecture-notes" or segments[3].endswith("_pdf"))
                    )
                    or (book_index and len(segments) == 3 and segments[:2] == [parts[0], "chapter"])
                )
                and not p.query
                and len(self.links) < 12
            ):
                self.active = target
                self.links.setdefault(target, "")

        def handle_data(self, data: str) -> None:
            if self.active:
                self.links[self.active] += data[: max(0, 200 - len(self.links[self.active]))]

        def handle_endtag(self, tag: str) -> None:
            if tag == "a":
                self.active = None

    parser = Chapters()
    parser.feed(body.decode("utf-8-sig", errors="replace"))
    return tuple((title.strip()[:200], url) for url, title in parser.links.items())


def resource_pdf_links(body: bytes, base_url: str) -> tuple[str, ...]:
    """Follow observed files in supported publisher download layouts, never guessed URLs."""
    try:
        validate_url(base_url)
    except SourceError:
        return ()
    parsed = urlsplit(base_url)
    parts = parsed.path.strip("/").split("/")
    mit_resource = (
        parsed.hostname == "ocw.mit.edu"
        and len(parts) == 4
        and parts[0] == "courses"
        and parts[2] == "resources"
    )
    ods_resource = parsed.hostname in {
        "opendatastructures.org",
        "www.opendatastructures.org",
    } and parsed.path in {"", "/"}
    if not (mit_resource or ods_resource):
        return ()
    expected_path = f"/courses/{parts[1]}/{parts[3][:-4]}.pdf" if mit_resource else ""

    class Links(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.urls: list[str] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            href = dict(attrs).get("href")
            if tag != "a" or not href:
                return
            target = urljoin(base_url, href)
            try:
                host = validate_url(target)
            except SourceError:
                return
            p = urlsplit(target)
            if (
                host == parsed.hostname
                and (
                    (mit_resource and parts[3].endswith("_pdf") and p.path == expected_path)
                    or (
                        mit_resource
                        and "download-file" in (dict(attrs).get("class") or "").split()
                        and p.path.startswith(f"/courses/{parts[1]}/")
                        and len(p.path.strip("/").split("/")) == 3
                        and p.path.lower().endswith(".pdf")
                    )
                    or (
                        ods_resource
                        and re.fullmatch(r"/ods-(?:python|java|cpp)(?:-screen)?\.pdf", p.path)
                    )
                )
                and not p.query
                and not self.urls
            ):
                self.urls.append(target)

    parser = Links()
    parser.feed(body.decode("utf-8-sig", errors="replace"))
    return tuple(dict.fromkeys(parser.urls))


class _BookContent(HTMLParser):
    """Extract LibreTexts' explicit content region, excluding its surrounding UI."""

    _void = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.region_depth: int | None = None
        self.found = False
        self.text = _HTMLText()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if (
            self.region_depth is None
            and "mt-content-container" in (dict(attrs).get("class") or "").split()
        ):
            self.region_depth = len(self.stack)
            self.found = True
        if self.region_depth is not None:
            self.text.handle_starttag(tag, attrs)
        if tag not in self._void:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.region_depth is not None:
            self.text.handle_endtag(tag)
        if tag in self.stack:
            last = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[last:]
        if self.region_depth is not None and len(self.stack) <= self.region_depth:
            self.region_depth = None

    def handle_data(self, data: str) -> None:
        if self.region_depth is not None:
            self.text.handle_data(data)


def html_content(body: bytes) -> str:
    """Book text for indexing; licence evidence is checked separately on full HTML."""
    parser = _BookContent()
    parser.feed(body.decode("utf-8-sig", errors="replace"))
    if not parser.found:
        return html_license_text(body)
    # Keep leading whitespace in preformatted Python examples.
    text = "\n".join(
        line.rstrip() for line in "".join(parser.text.parts).splitlines() if line.strip()
    )
    return unicodedata.normalize("NFC", text)
