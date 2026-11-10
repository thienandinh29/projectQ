import asyncio
from collections.abc import Sequence
from typing import Any, cast

import httpx
import pytest

from app.content.gateway import ModelReply
from app.research.agent import ChosenSource, ResearchAgent, SearchResult
from app.research.reader import Allowlist, Publisher, SafeReader, SourceError
from app.research.relevance import ResearchRelevance
from tests.content.fakes import FakeGateway


class RelevanceModels(FakeGateway):
    async def generate(self, **kwargs: Any) -> ModelReply:
        self.calls.append(kwargs)
        content: dict[str, Any]
        if kwargs["task"] == "plan_research":
            content = {"query": "beginner English verb be lessons", "scope_vi": "Beginner lesson"}
        elif kwargs["task"] == "assess_research_plan":
            content = {"preserves_goal": True, "reason_vi": "Fixture plan"}
        elif "candidates" in kwargs["payload"]:
            content = {"urls": [r["url"] for r in kwargs["payload"]["candidates"]]}
        else:
            payload = kwargs["payload"]
            # Content matters even when the title promises the right subject.
            content = {
                "teaches_goal": any("English lesson" in e["text"] for e in payload["excerpts"]),
                "reason_vi": "Fixture",
                "teaching_excerpt_id": payload["excerpts"][0]["id"],
            }
        return ModelReply(content=content, identity=self.item.generator)


def test_plan_preserves_goal_as_data_and_source_check_uses_actual_content() -> None:
    models = RelevanceModels()
    policy = ResearchRelevance(models)
    plan = asyncio.run(policy.plan("hoc tieng anh"))
    assert plan.query == "beginner English verb be lessons"
    assert models.calls[0]["payload"] == {"learning_goal": "hoc tieng anh"}
    for text, expected in [
        ("English lesson: Use am with I, is with he or she, and are with they.", True),
        ("Chinese textbook", False),
        ("Bilingual child development", False),
        ("Project evaluation", False),
    ]:
        source = ChosenSource("Learn English", "Publisher", "https://a.example", "CC BY 4.0", text)
        assert asyncio.run(policy.supports("hoc tieng anh", source)) is expected


def test_agent_rejects_licensed_but_irrelevant_pages_before_selecting_sources() -> None:
    allowlist = Allowlist(publishers=[Publisher(name="A", domains=["a.example"])])
    models = RelevanceModels()
    events = []

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        assert "beginner English" in query and "hoc tieng anh" not in query
        return [SearchResult("Learn English", "https://a.example/wrong")]

    async def event(data: dict[str, str]) -> None:
        events.append(data)

    reader = SafeReader(
        allowlist=allowlist,
        resolver=resolve,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<p>Chinese textbook content. CC BY 4.0</p>" * 10,
            )
        ),
    )
    with pytest.raises(SourceError, match="Chưa đủ"):
        asyncio.run(
            ResearchAgent(
                search, allowlist=allowlist, reader=reader, relevance=ResearchRelevance(models)
            ).research("hoc tieng anh", event)
        )
    assert not any(e["kind"] == "select" for e in events)
    assert any("chưa được xác nhận" in e["text_vi"] for e in events)


def test_agent_reads_ranked_html_lessons_before_whole_book_pdfs() -> None:
    allowed = Allowlist(publishers=[], allow_public=True)
    reads: list[str] = []

    async def resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        return [
            SearchResult("Whole book", "https://book.example/textbook.pdf"),
            SearchResult("Lesson", "https://one.example/lesson"),
            SearchResult("Lesson", "https://two.example/lesson"),
            SearchResult("Lesson", "https://three.example/lesson"),
        ]

    def handler(request: httpx.Request) -> httpx.Response:
        reads.append(str(request.url))
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="English lesson: I am, she is, they are. CC BY 4.0. " * 10,
        )

    async def event(data: dict[str, str]) -> None:
        pass

    sources = asyncio.run(
        ResearchAgent(
            search,
            allowlist=allowed,
            reader=SafeReader(
                allowlist=allowed, resolver=resolve, transport=httpx.MockTransport(handler)
            ),
            relevance=ResearchRelevance(RelevanceModels()),
            open_web=True,
        ).research("hoc tieng anh", event)
    )
    assert len(sources) == 3 and len(reads) == 3
    assert not any(url.endswith(".pdf") for url in reads)


def test_long_source_samples_middle_teaching_without_increasing_context_budget() -> None:
    models = RelevanceModels()
    text = "Contents and preface. " * 1200
    text += "English lesson: I am, she is, they are. " * 500
    text += "Index and bibliography. " * 1200
    source = ChosenSource("Book", "Publisher", "https://a.example", "CC BY 4.0", text)
    assert asyncio.run(ResearchRelevance(models).supports("hoc tieng anh", source))
    excerpts = cast(dict[str, Any], models.calls[-1]["payload"])["excerpts"]
    assert sum(len(e["text"]) for e in excerpts) <= 24000
    assert all(e["text"] in text for e in excerpts)


def test_invalid_relevance_reply_fails_closed() -> None:
    class Invalid(RelevanceModels):
        async def generate(self, **kwargs: Any) -> ModelReply:
            return ModelReply(content={"teaches_goal": "yes"}, identity=self.item.generator)

    policy = ResearchRelevance(Invalid())
    source = ChosenSource(
        "Title",
        "Publisher",
        "https://a.example",
        "CC BY 4.0",
        "Actual instructional source text for model validation. " * 3,
    )
    with pytest.raises(SourceError):
        asyncio.run(policy.supports("English", source))


def test_positive_source_claim_without_real_teaching_quote_is_rejected() -> None:
    class Fabricated(RelevanceModels):
        async def generate(self, **kwargs: Any) -> ModelReply:
            return ModelReply(
                content={
                    "teaches_goal": True,
                    "reason_vi": "Untrusted model claim",
                    "teaching_excerpt_id": "invented-excerpt",
                },
                identity=self.item.generator,
            )

    source = ChosenSource(
        "English course",
        "Publisher",
        "https://a.example",
        "CC BY 4.0",
        "This is only a list of links and course objectives.",
    )
    assert not asyncio.run(ResearchRelevance(Fabricated()).supports("English", source))


def test_math_source_evidence_uses_server_text_without_rewriting_formulas() -> None:
    raw = "The derivative is the limit.\n f'(x) = lim\n h→0\n (f(x+h)\u2212f(x))/h. " * 3

    class Math(RelevanceModels):
        async def generate(self, **kwargs: Any) -> ModelReply:
            excerpts = kwargs["payload"]["excerpts"]
            assert excerpts[0]["text"] == raw
            return ModelReply(
                content={
                    "teaches_goal": True,
                    "reason_vi": "Derivative lesson",
                    "teaching_excerpt_id": excerpts[0]["id"],
                },
                identity=self.item.generator,
            )

    assert asyncio.run(
        ResearchRelevance(Math()).supports(
            "learn derivatives",
            ChosenSource("Derivative", "MIT", "https://a.example", "CC BY 4.0", raw),
        )
    )


def test_ranking_cannot_introduce_urls_or_duplicate_candidates() -> None:
    class Ranked(RelevanceModels):
        async def generate(self, **kwargs: Any) -> ModelReply:
            return ModelReply(
                content={
                    "urls": [
                        "https://evil.example/fabricated",
                        "https://a.example/lesson",
                        "https://a.example/lesson",
                    ]
                },
                identity=self.item.generator,
            )

    candidates = [SearchResult("Lesson", "https://a.example/lesson", "Actual snippet")]
    assert asyncio.run(ResearchRelevance(Ranked()).rank("English", candidates)) == candidates


def test_query_variants_share_the_existing_search_budget() -> None:
    class Plans(RelevanceModels):
        async def generate(self, **kwargs: Any) -> ModelReply:
            if kwargs["task"] != "plan_research":
                return await super().generate(**kwargs)
            return ModelReply(
                content={
                    "query": "English sentences",
                    "alternate_query": "English grammar",
                    "scope_vi": "Beginner",
                },
                identity=self.item.generator,
            )

    calls = []

    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        calls.append((query, domains[0]))
        return []

    async def event(data: dict[str, str]) -> None:
        pass

    allowed = Allowlist(
        publishers=[Publisher(name=str(n), domains=[f"p{n}.example"]) for n in range(5)]
    )
    with pytest.raises(SourceError):
        asyncio.run(
            ResearchAgent(
                search, allowlist=allowed, max_searches=3, relevance=ResearchRelevance(Plans())
            ).research("goal", event)
        )
    assert calls == [
        ("English sentences", "p0.example"),
        ("English grammar", "p0.example"),
        ("English sentences", "p1.example"),
    ]


def test_rank_sees_both_full_search_pages_and_keeps_only_supplied_urls() -> None:
    candidates = [SearchResult(str(n), f"https://a.example/{n}", "x" * 1600) for n in range(24)]

    class LastCandidate(RelevanceModels):
        async def generate(self, **kwargs: Any) -> ModelReply:
            supplied = kwargs["payload"]["candidates"]
            assert len(supplied) == 24
            assert all(len(row["snippet"]) == 800 for row in supplied)
            return ModelReply(
                content={"urls": [candidates[-1].url, "https://evil.example/invented"]},
                identity=self.item.generator,
            )

    assert asyncio.run(ResearchRelevance(LastCandidate()).rank("goal", candidates)) == [
        candidates[-1]
    ]


def test_resource_publisher_search_uses_short_planned_topic() -> None:
    class Plans(RelevanceModels):
        async def generate(self, **kwargs: Any) -> ModelReply:
            if kwargs["task"] != "plan_research":
                return await super().generate(**kwargs)
            return ModelReply(
                content={
                    "query": "derivative definition tangent slope",
                    "topic_query": "introductory derivatives",
                    "scope_vi": "Introduction",
                },
                identity=self.item.generator,
            )

    calls = []

    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        calls.append(query)
        return []

    async def event(data: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError):
        asyncio.run(
            ResearchAgent(
                search,
                allowlist=Allowlist(publishers=[Publisher(name="MIT", domains=["ocw.mit.edu"])]),
                relevance=ResearchRelevance(Plans()),
            ).research("learn derivatives", event)
        )
    assert calls == ["introductory derivatives chapter textbook resource"]


def test_changed_subject_plan_is_blocked_before_any_search() -> None:
    class ChangedSubject(RelevanceModels):
        async def generate(self, **kwargs: Any) -> ModelReply:
            content = (
                {"query": "beginner English grammar", "scope_vi": "English language"}
                if kwargs["task"] == "plan_research"
                else {"preserves_goal": False, "reason_vi": "DSA was replaced by language learning"}
            )
            return ModelReply(content=content, identity=self.item.generator)

    async def search(query: str, domains: Sequence[str]) -> list[SearchResult]:
        pytest.fail("A changed subject must not spend search credits")

    async def event(value: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError) as caught:
        asyncio.run(
            ResearchAgent(
                search, relevance=ResearchRelevance(ChangedSubject()), open_web=True
            ).research("Cau truc du lieu va giai thuatj", event)
        )
    assert caught.value.code == "research_goal_mismatch"
