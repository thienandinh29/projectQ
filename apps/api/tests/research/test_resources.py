import asyncio
from collections.abc import Sequence

import pytest

from app.research.agent import ResearchAgent, SearchResult
from app.research.reader import (
    Allowlist,
    Publisher,
    SafeReader,
    SourceError,
    resource_chapter_links,
    resource_pdf_links,
)
from app.uploads.reader import Document, Page

PARENT = "https://ocw.mit.edu/courses/calculus/resources/chapter02_pdf/"
PDF = "https://ocw.mit.edu/courses/calculus/chapter02.pdf"
INDEX = "https://ocw.mit.edu/courses/calculus/pages/open-textbook/"


def test_textbook_contents_discovers_only_observed_same_course_chapters() -> None:
    index = "https://ocw.mit.edu/courses/calculus/pages/open-textbook/"
    body = (
        f'<a href="{PARENT}">Chapter 2: Derivatives</a>'
        '<a href="https://evil.example/courses/calculus/resources/x_pdf">External</a>'
        '<a href="/courses/other/resources/x_pdf">Other course</a>'
    ).encode()
    assert resource_chapter_links(body, index) == (("Chapter 2: Derivatives", PARENT),)
    assert resource_chapter_links(body, index.replace("https:", "http:")) == ()
    assert resource_chapter_links(body, index.replace("open-textbook", "syllabus")) == ()


def test_resource_links_only_follow_observed_exact_same_course_pdf() -> None:
    body = (
        f'<a href="{PDF}">Download</a><a href="{PDF}">Again</a>'
        '<a href="https://evil.example/chapter02.pdf">External</a>'
        '<a href="/courses/other/chapter02.pdf">Other course</a>'
        '<a href="/courses/calculus/unrelated.pdf">Other file</a>'
        '<a href="http://ocw.mit.edu/courses/calculus/chapter02.pdf">HTTP</a>'
    ).encode()
    assert resource_pdf_links(body, PARENT) == (PDF,)
    assert (
        resource_pdf_links(body, "https://evil.example/courses/calculus/resources/chapter02_pdf/")
        == ()
    )
    assert resource_pdf_links(body, PARENT.replace("https:", "http:")) == ()


@pytest.mark.parametrize("via_index", [False, True])
@pytest.mark.parametrize("pdf_first", [False, True])
@pytest.mark.parametrize(
    "max_reads,grant,restriction,success",
    [
        (12, "CC BY-NC-SA 4.0", "", True),
        (3, "CC BY-NC-SA 4.0", "", False),
        (12, "CC BY-ND 4.0", "", False),
        (12, "CC BY 4.0", "All rights reserved.", False),
        (12, "CC BY 4.0", "CC BY-ND 4.0", False),
    ],
)
def test_resource_download_counts_budget_and_retains_license_provenance(
    monkeypatch: pytest.MonkeyPatch,
    max_reads: int,
    grant: str,
    restriction: str,
    success: bool,
    via_index: bool,
    pdf_first: bool,
) -> None:
    calls: list[str] = []
    events: list[dict[str, str]] = []
    allowed = Allowlist(
        publishers=[
            Publisher(name="A", domains=["books.example"]),
            Publisher(name="MIT", domains=["ocw.mit.edu"]),
        ]
    )

    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        if domains[0] == "books.example":
            return [SearchResult("Lesson", f"https://books.example/{n}") for n in range(2)]
        return ([SearchResult("Derivative PDF", PDF)] if pdf_first else []) + [
            SearchResult("Derivative chapter", INDEX if via_index else PARENT)
        ]

    async def read(url: str, reader: SafeReader, *, pdf_page_limit: int | None = None) -> Document:
        assert pdf_page_limit == 40
        calls.append(url)
        if url == INDEX:
            return Document(
                url,
                (Page(1, "Textbook contents. CC BY-NC-SA 4.0"),),
                True,
                "text/html",
                chapter_links=(("Derivative chapter", PARENT),),
            )
        if url == PARENT:
            return Document(
                url,
                (Page(1, "Download the derivative chapter. " + grant),),
                True,
                "text/html",
                resource_links=(PDF,),
            )
        text = "A derivative describes the rate of change of a function. " + restriction
        return Document(
            url,
            (Page(1, text if url == PDF else text + " CC BY 4.0"),),
            True,
            "application/pdf" if url == PDF else "text/html",
        )

    async def event(data: dict[str, str]) -> None:
        events.append(data)

    monkeypatch.setattr("app.research.agent.read_link", read)
    agent = ResearchAgent(search, allowlist=allowed, max_reads=max_reads)
    if success:
        sources = asyncio.run(agent.research("learn derivatives", event))
        assert len(sources) == 3 and sources[-1].url == PDF
        assert sources[-1].license_source_url == PARENT
        assert sources[-1].license == "CC BY-NC-SA 4.0" and sources[-1].pages[0].number == 1
    else:
        with pytest.raises(SourceError):
            asyncio.run(agent.research("learn derivatives", event))
    assert len(calls) <= max_reads
    assert calls.count(PDF) <= 1
    if (max_reads == 3 or "ND" in grant) and not pdf_first:
        assert PDF not in calls
    if not success and max_reads != 3:
        assert any("Bỏ qua nguồn:" in e["text_vi"] for e in events)
