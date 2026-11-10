import asyncio
import json
from collections.abc import Sequence

import httpx
import pytest

from app.research.agent import ResearchAgent, SearchResult
from app.research.failures import failure_report
from app.research.reader import (
    Allowlist,
    Publisher,
    SafeReader,
    SourceError,
    resource_chapter_links,
    resource_pdf_links,
)
from app.research.search import BraveSearch, TavilySearch
from app.schemas import TopicFailure


@pytest.mark.parametrize("adapter", [BraveSearch, TavilySearch])
def test_open_search_omits_domain_restriction_but_filters_unsafe_urls(adapter: type) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        entries = [
            {"title": "New publisher", "url": "https://new.example/lesson"},
            {"title": "Unsafe", "url": "http://new.example/lesson"},
        ]
        if adapter is TavilySearch:
            payload = json.loads(request.content)
            assert "include_domains" not in payload and "include_domains_mode" not in payload
            assert payload["search_depth"] == "basic" and payload["auto_parameters"] is False
            return httpx.Response(200, json={"results": entries})
        assert "site:" not in request.url.params["q"]
        return httpx.Response(200, json={"web": {"results": entries}})

    result = asyncio.run(
        adapter("test-key", transport=httpx.MockTransport(handler))("algorithms", [])
    )
    assert [r.url for r in result] == ["https://new.example/lesson"]


@pytest.mark.parametrize("licensed", [True, False])
def test_open_research_uses_new_publishers_and_keeps_license_gate(licensed: bool) -> None:
    allowed = Allowlist(
        publishers=[Publisher(name="Seed", domains=["seed.example"])], allow_public=True
    )
    searches = []
    reads = []
    events = []

    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        searches.append(domains)
        return (
            [
                SearchResult("Lesson", f"https://{host}/{n}")
                for n, host in enumerate(["one.example", "sub.one.example", "two.example"])
            ]
            if not domains
            else []
        )

    async def public(host: str) -> list[str]:
        return ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        reads.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<p>"
            + "An array stores elements by index. " * 10
            + ("CC BY 4.0" if licensed else "")
            + "</p>",
        )

    async def event(value: dict[str, str]) -> None:
        events.append(value)

    agent = ResearchAgent(
        search,
        allowlist=allowed,
        open_web=True,
        reader=SafeReader(
            allowlist=allowed, resolver=public, transport=httpx.MockTransport(handler)
        ),
    )
    if licensed:
        sources = asyncio.run(agent.research("arrays", event))
        assert len(sources) == 3 and {s.publisher for s in sources} == {
            "one.example",
            "two.example",
        }
        assert [r.headers["host"] for r in reads[:2]] == ["one.example", "two.example"]
    else:
        with pytest.raises(SourceError) as caught:
            asyncio.run(agent.research("arrays", event))
        assert caught.value.code == "research_sources_insufficient"
        assert any(e.get("code") == "license_missing" for e in events)
    assert searches[0] == [] and len(searches) <= 15 and len(reads) <= 12


def test_open_reader_still_blocks_private_redirect_targets() -> None:
    allowed = Allowlist(publishers=[], allow_public=True)
    calls = []

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"] if host == "new.example" else ["127.0.0.1"]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://internal.example/admin"})

    with pytest.raises(SourceError, match="nội bộ"):
        asyncio.run(
            SafeReader(
                allowlist=allowed, resolver=resolve, transport=httpx.MockTransport(handler)
            ).fetch("https://new.example/lesson")
        )
    assert len(calls) == 1


def test_lecture_pdf_download_is_observed_same_course_not_filename_guessed() -> None:
    page = "https://ocw.mit.edu/courses/algorithms/resources/mit6_006s20_lec2/"
    pdf = "https://ocw.mit.edu/courses/algorithms/hash_MIT6_006S20_lec2.pdf"
    html = (
        f'<a class="download-file" href="{pdf}">Download</a>'
        '<a class="download-file" href="/courses/another/notes.pdf">Other</a>'
    ).encode()
    assert resource_pdf_links(html, page) == (pdf,)
    assert resource_pdf_links(html.replace(b"download-file", b"other"), page) == ()


def test_failure_report_keeps_stage_actions_and_latest_rejections_only() -> None:
    report = failure_report(
        "Not ready",
        [
            {"code": "license_missing", "outcome": "rejected", "text_vi": "Previous run"},
            {"code": "research_started"},
            {
                "code": "license_nd",
                "outcome": "rejected",
                "text_vi": "ND source",
                "url": "https://new.example/nd",
            },
            {
                "code": "research_sources_insufficient",
                "outcome": "failed",
                "stage": "research",
                "text_vi": "Only 1/3 sources",
                "action_vi": "Provide permitted material",
            },
        ],
    )
    checked = TopicFailure.model_validate(report)
    assert checked.stage == "research" and checked.action_vi == "Provide permitted material"
    assert [r.code for r in checked.rejected_sources] == ["license_nd"]


def test_failure_report_removes_recovered_pdf_license_rejection() -> None:
    url = "https://publisher.example/lesson.pdf"
    report = failure_report(
        "No items",
        [
            {"code": "license_missing", "outcome": "rejected", "text_vi": "Missing", "url": url},
            {"code": "license_verified", "url": url},
            {
                "code": "not_instructional",
                "outcome": "rejected",
                "text_vi": "Not a lesson",
                "url": url,
            },
            {"outcome": "failed", "stage": "items", "text_vi": "No items"},
        ],
    )
    assert report["stage"] == "items"
    assert [r["code"] for r in report["rejected_sources"]] == ["not_instructional"]


def test_book_contents_follow_only_observed_chapters_inside_the_same_book() -> None:
    root = "https://pressbooks.example/algorithms/"
    chapter = root + "chapter/arrays/"
    html = (
        f'<a href="{chapter}">Arrays and indexing</a>'
        '<a href="/another/chapter/arrays/">Other book</a>'
        '<a href="https://evil.example/algorithms/chapter/arrays/">External</a>'
    ).encode()
    assert resource_chapter_links(html, root) == (("Arrays and indexing", chapter),)
    assert resource_chapter_links(html, root + "chapter/intro/") == ()


@pytest.mark.parametrize("chapter_license", ["CC BY 4.0", ""])
def test_open_book_discovery_checks_each_chapter_permission_separately(
    chapter_license: str,
) -> None:
    allowed = Allowlist(publishers=[], allow_public=True)
    reads = []
    root = "https://pressbooks.example/algorithms/"

    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        return [
            SearchResult("Algorithms book", root),
            SearchResult("Lesson", "https://other.example/lesson"),
        ]

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        reads.append(str(request.url))
        if request.url.path == "/algorithms/":
            body = (
                "Contents. " * 20
                + " CC BY 4.0 "
                + "".join(f'<a href="{root}chapter/{n}/">Chapter {n}: arrays</a>' for n in range(2))
            )
        else:
            grant = chapter_license if request.url.path.startswith("/algorithms/") else "CC BY 4.0"
            body = "An array stores elements by index. " * 10 + grant
        return httpx.Response(200, headers={"content-type": "text/html"}, text=body)

    async def event(value: dict[str, str]) -> None:
        pass

    agent = ResearchAgent(
        search,
        allowlist=allowed,
        open_web=True,
        reader=SafeReader(
            allowlist=allowed, resolver=resolve, transport=httpx.MockTransport(handler)
        ),
    )
    if chapter_license:
        sources = asyncio.run(agent.research("arrays", event))
        assert len(sources) == 3 and all(s.url != root for s in sources)
    else:
        with pytest.raises(SourceError) as caught:
            asyncio.run(agent.research("arrays", event))
        assert caught.value.code == "research_sources_insufficient"
    assert len(reads) == 4


def test_insufficient_licensed_sources_triggers_a_second_unrestricted_scope() -> None:
    allowed = Allowlist(
        publishers=[Publisher(name="Seed", domains=["seed.example"])], allow_public=True
    )
    calls = []

    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        calls.append((query, list(domains)))
        if len(calls) == 1:
            return [SearchResult("No permission", f"https://blocked.example/{i}") for i in range(4)]
        if domains:
            return [SearchResult("Seed lesson", "https://seed.example/lesson")]
        return [SearchResult("New lesson", f"https://outside.example/{i}") for i in range(2)]

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    def handler(request: httpx.Request) -> httpx.Response:
        text = "Arrays store indexed elements. " * 10
        if request.headers["host"] != "blocked.example":
            text += "CC BY 4.0"
        return httpx.Response(200, headers={"content-type": "text/html"}, text=text)

    async def event(value: dict[str, str]) -> None:
        pass

    reader = SafeReader(allowlist=allowed, resolver=resolve, transport=httpx.MockTransport(handler))
    sources = asyncio.run(
        ResearchAgent(search, allowlist=allowed, reader=reader, open_web=True).research(
            "arrays", event
        )
    )
    assert len(sources) == 3
    assert [domains for _, domains in calls] == [[], ["seed.example"], []]
    assert calls[0][0] != calls[-1][0]


def test_search_outage_is_not_reported_as_missing_document_permission() -> None:
    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        raise SourceError("Search HTTP 429", code="search_http_429", retryable=True)

    async def event(value: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError) as caught:
        asyncio.run(ResearchAgent(search, open_web=True).research("arrays", event))
    assert caught.value.code == "research_search_unavailable"
    assert caught.value.action_vi
