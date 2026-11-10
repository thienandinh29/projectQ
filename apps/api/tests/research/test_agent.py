import asyncio
from collections.abc import Sequence

import httpx
import pytest

from app.research.agent import ResearchAgent, SearchResult
from app.research.reader import Allowlist, Publisher, SafeReader, SourceError


def test_research_selects_three_sources_from_two_publishers() -> None:
    allowlist = Allowlist(
        publishers=[
            Publisher(name="A", domains=["a.example"]),
            Publisher(name="B", domains=["b.example"]),
        ]
    )
    calls: list[str] = []
    events: list[dict[str, str]] = []

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    async def search(query: str, domains: Sequence[str]) -> Sequence[SearchResult]:
        calls.append(query)
        host = "a.example" if "site:a.example" in query else "b.example"
        return [
            SearchResult("Untrusted", "https://evil.example/book"),
            SearchResult("Textbook 1", f"https://{host}/1"),
            SearchResult("Textbook 2", f"https://{host}/2"),
        ]

    async def on_event(event: dict[str, str]) -> None:
        events.append(event)

    reader = SafeReader(
        allowlist=allowlist,
        resolver=resolve,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<p>Educational textbook chapter " * 4 + "CC BY-SA 4.0</p>",
            )
        ),
    )
    result = asyncio.run(
        ResearchAgent(search, allowlist=allowlist, reader=reader).research("Sinh học", on_event)
    )
    assert len(result) == 3
    assert {source.publisher for source in result} == {"A", "B"}
    assert len(calls) == 2
    assert sum(event["kind"] == "select" for event in events) == 3


def test_search_count_limit_and_insufficient_sources() -> None:
    allowlist = Allowlist(
        publishers=[
            Publisher(name=str(index), domains=[f"p{index}.example"]) for index in range(20)
        ]
    )
    searches = 0

    async def search(query: str, domains: Sequence[str]) -> Sequence[SearchResult]:
        nonlocal searches
        searches += 1
        return []

    async def event(data: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError, match="Chưa đủ"):
        asyncio.run(ResearchAgent(search, allowlist=allowlist).research("goal", event))
    assert searches == 15


def test_deadline_cancels_slow_search() -> None:
    async def search(query: str, domains: Sequence[str]) -> Sequence[SearchResult]:
        await asyncio.sleep(100)
        return []

    async def event(data: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError, match="hết thời gian"):
        asyncio.run(ResearchAgent(search, deadline_seconds=0.01).research("goal", event))


def test_contract_limits_cannot_be_increased() -> None:
    async def search(query: str, domains: Sequence[str]) -> Sequence[SearchResult]:
        return []

    with pytest.raises(ValueError):
        ResearchAgent(search, max_searches=16)
    with pytest.raises(ValueError):
        ResearchAgent(search, max_reads=13)
    with pytest.raises(ValueError):
        ResearchAgent(search, deadline_seconds=481)
