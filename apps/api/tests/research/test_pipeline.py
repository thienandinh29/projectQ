import asyncio
from collections.abc import Sequence
from typing import Any

import pytest

from app.api.topics import TopicInput
from app.graders.mcq import Item
from app.research.agent import ChosenSource, OnEvent
from app.research.pipeline import GraphDraft, PreparedChunk, Progress, TopicPipeline, marked_chunks
from app.research.reader import SourceError
from app.schemas import Citation
from app.uploads.reader import Document, Page
from tests.graders.test_mcq import item


class Ports:
    def __init__(self) -> None:
        self.upload = Document("private/uploads/u1.pdf", (Page(1, "Nguồn học tập"),), True)
        self.items = [
            item().model_copy(update={"id": f"q{i}", "source": "https://books.example/a"})
            for i in range(6)
        ]
        self.graph_saved = self.items_saved = False
        self.supported = True

    async def load_upload(self, upload_id: str) -> Document | None:
        return self.upload if upload_id == "u1" else None

    async def quick_sources(self, goal: str) -> Sequence[ChosenSource]:
        return [ChosenSource("Book", "Publisher", "https://books.example/a", "CC BY 4.0", "text")]

    async def index(
        self, sources: Sequence[ChosenSource], upload: Document | None
    ) -> Sequence[PreparedChunk]:
        return [
            PreparedChunk(id="chunk-1", text="Nguồn", source_uri="https://books.example/a", page=1)
        ]

    async def build_graph(
        self, goal: str, chunks: Sequence[PreparedChunk], tier: str
    ) -> GraphDraft:
        return GraphDraft(
            subject_slug="biology",
            graph={
                "concepts": [
                    {
                        "slug": "biology",
                        "name_vi": "Sinh học",
                        "name_en": "Biology",
                        "sources": [chunks[0].source_uri],
                    }
                ],
                "edges": [],
            },
            supported=self.supported,
        )

    async def save_graph(self, graph: GraphDraft) -> None:
        self.graph_saved = True

    async def build_items(
        self,
        graph: GraphDraft,
        chunks: Sequence[PreparedChunk],
        tier: str,
        count: int,
    ) -> Sequence[Item]:
        return self.items

    async def save_items(self, subject_slug: str, items: Sequence[Item]) -> None:
        self.items_saved = True


def test_quick_upload_pipeline_never_searches_and_publishes_only_after_persistence() -> None:
    ports = Ports()
    states: list[Progress] = []

    async def progress(value: Progress) -> None:
        if value.graph_ready:
            assert ports.graph_saved and ports.items_saved
        if value.items_ready:
            assert ports.items_saved
        states.append(value)

    async def event(value: dict[str, str]) -> None:
        pytest.fail("Quick mode must never search")

    result = asyncio.run(
        pipeline(ports).run(
            TopicInput(upload_id="u1", mode="quick", tier="free"),
            progress,
            event,
        )
    )
    assert result.subject_slug == "biology" and len(result.item_ids) == 6
    assert [s.status for s in states] == ["researching", "indexing", "graph", "items", "ready"]


@pytest.mark.parametrize("failure", ["pending", "citation", "duplicate", "graph"])
def test_pipeline_does_not_publish_invalid_items_or_graph(failure: str) -> None:
    ports = Ports()
    if failure == "pending":
        ports.items[0] = ports.items[0].model_copy(update={"status": "needs_review"})
    elif failure == "citation":
        ports.items[0] = ports.items[0].model_copy(update={"chunk_ids": ["foreign-chunk"]})
    elif failure == "duplicate":
        ports.items[0] = ports.items[1]
    else:
        ports.supported = False
    states: list[Progress] = []

    async def progress(value: Progress) -> None:
        states.append(value)

    async def event(value: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError):
        asyncio.run(
            pipeline(ports).run(
                TopicInput(goal_vi="biology", mode="quick", tier="free"),
                progress,
                event,
            )
        )
    assert states[-1].status == "failed" and not ports.items_saved
    assert all(not state.graph_ready for state in states)
    assert all(not state.items_ready for state in states)


def test_deadline_cancels_job_and_reports_failed() -> None:
    class SlowPorts(Ports):
        async def quick_sources(self, goal: str) -> Sequence[ChosenSource]:
            await asyncio.sleep(100)
            return []

    states: list[Progress] = []

    async def progress(value: Progress) -> None:
        states.append(value)

    async def event(value: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError, match="hết thời gian"):
        asyncio.run(
            pipeline(SlowPorts(), quick_seconds=0.01).run(
                TopicInput(goal_vi="biology", mode="quick", tier="free"),
                progress,
                event,
            )
        )
    assert states[-1].status == "failed"


def test_long_context_markers_preserve_ids_and_provenance() -> None:
    text = marked_chunks(
        [PreparedChunk(id="c1", text="Nội dung", source_uri="private/u.pdf", page=3)]
    )
    assert "[chunk_id=c1]" in text and "page: 3" in text and "private/u.pdf" in text


def test_deep_pipeline_uses_research_and_preserves_source_summaries() -> None:
    ports = Ports()
    states: list[Progress] = []
    events: list[dict[str, str]] = []

    async def deep(goal: str, event: OnEvent) -> list[ChosenSource]:
        await event({"kind": "search", "text_vi": "Đang tìm nguồn…"})
        return [
            ChosenSource(
                f"Book {i}",
                f"Publisher {i % 2}",
                f"https://books.example/{i}",
                "CC BY 4.0",
                "source",
            )
            for i in range(3)
        ]

    async def progress(value: Progress) -> None:
        states.append(value)

    async def event(value: dict[str, str]) -> None:
        events.append(value)

    result = asyncio.run(
        pipeline(ports, research_runner=deep).run(
            TopicInput(goal_vi="biology", mode="deep", tier="pro"),
            progress,
            event,
        )
    )
    assert len(result.sources) == 3 and len(states[-1].sources) == 3
    assert "at" in events[0]
    assert not hasattr(states[-1].sources[0], "text")


def test_missing_upload_and_internal_failure_are_not_reported_ready() -> None:
    states: list[Progress] = []

    async def progress(value: Progress) -> None:
        states.append(value)

    async def event(value: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError, match="Không tìm thấy"):
        asyncio.run(
            pipeline(Ports()).run(
                TopicInput(upload_id="missing", mode="quick", tier="free"),
                progress,
                event,
            )
        )
    assert states[-1].status == "failed"


def test_worker_shutdown_propagates_cancellation_without_failed_write() -> None:
    class CancelledPorts(Ports):
        async def quick_sources(self, goal: str) -> Sequence[ChosenSource]:
            raise asyncio.CancelledError

    states: list[Progress] = []

    async def progress(value: Progress) -> None:
        states.append(value)

    async def event(value: dict[str, str]) -> None:
        pass

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            pipeline(CancelledPorts()).run(
                TopicInput(goal_vi="biology", mode="quick", tier="free"),
                progress,
                event,
            )
        )
    assert all(state.status != "failed" for state in states)


def test_progress_sink_failure_does_not_expose_internal_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def progress(value: Progress) -> None:
        raise RuntimeError("secret database connection details")

    async def event(value: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError) as caught:
        asyncio.run(
            pipeline(Ports()).run(
                TopicInput(goal_vi="biology", mode="quick", tier="free"),
                progress,
                event,
            )
        )
    assert "secret" not in str(caught.value)
    assert "secret" not in caplog.text
    assert "research pipeline failed at research (RuntimeError)" in caplog.text
    assert "progress:" in caplog.text


def test_question_failure_names_stage_without_leaking_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FailingQuestions(Ports):
        async def build_items(
            self, graph: GraphDraft, chunks: Sequence[PreparedChunk], tier: str, count: int
        ) -> Sequence[Item]:
            raise RuntimeError("secret provider response")

    states: list[Progress] = []

    async def progress(value: Progress) -> None:
        states.append(value)

    async def event(value: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError, match="sinh, kiểm chứng hoặc lưu câu hỏi"):
        asyncio.run(
            pipeline(FailingQuestions()).run(
                TopicInput(goal_vi="biology", mode="quick", tier="free"), progress, event
            )
        )
    assert "secret" not in caplog.text
    assert "failed at questions (RuntimeError)" in caplog.text
    assert not states[-1].graph_ready and not states[-1].items_ready


class Retrieved:
    def __init__(self, chunks: Sequence[PreparedChunk]) -> None:
        from app.schemas import Citation

        self.citations = [
            Citation(
                chunk_id=c.id,
                content=c.text,
                source_uri=c.source_uri,
                page=c.page,
                source_title="Book",
                license="CC BY 4.0",
                score=0.8,
            )
            for c in chunks
        ]
        self.calls: list[tuple[str, str, int]] = []

    async def search(self, query: str, subject: str, k: int = 5) -> list[Citation]:
        self.calls.append((query, subject, k))
        return self.citations


def test_retrieval_restores_reading_order() -> None:
    from app.research.pipeline import retrieve_chunks

    chunks = [
        PreparedChunk(
            id=f"c{i}", text=f"paragraph {i}", source_uri="https://books.example/a", page=i
        )
        for i in range(1, 4)
    ]
    retriever = Retrieved([chunks[2], chunks[0]])
    result = asyncio.run(retrieve_chunks(retriever, "goal", "biology", chunks, 2))
    assert [c.id for c in result] == ["c1", "c3"]
    assert retriever.calls == [("goal", "biology", 2)]


@pytest.mark.parametrize("failure", ["empty", "foreign", "text", "uri", "page", "duplicate"])
def test_retrieval_rejects_inconsistent_provenance(failure: str) -> None:
    from app.research.pipeline import retrieve_chunks

    chunk = PreparedChunk(id="c1", text="paragraph", source_uri="https://books.example/a")
    retriever = Retrieved([chunk])
    changes: dict[str, dict[str, str | int]] = {
        "foreign": {"chunk_id": "other"},
        "text": {"content": "changed"},
        "uri": {"source_uri": "https://evil.example"},
        "page": {"page": 2},
    }
    if failure == "empty":
        retriever.citations = []
    elif failure == "duplicate":
        retriever.citations *= 2
    else:
        retriever.citations[0] = retriever.citations[0].model_copy(update=changes[failure])
    with pytest.raises(SourceError):
        asyncio.run(retrieve_chunks(retriever, "goal", "biology", [chunk], 5))


@pytest.mark.parametrize("failure", ["empty-graph", "foreign-source", "item-source", "retrieval"])
def test_pipeline_rejects_bad_canonical_content_before_publication(failure: str) -> None:
    class BadPorts(Ports):
        async def build_graph(
            self, goal: str, chunks: Sequence[PreparedChunk], tier: str
        ) -> GraphDraft:
            result = await super().build_graph(goal, chunks, tier)
            if failure == "empty-graph":
                result.graph["concepts"] = []
            if failure == "foreign-source":
                result.graph["concepts"] = [
                    {
                        "slug": "biology",
                        "name_vi": "Sinh học",
                        "name_en": "Biology",
                        "sources": ["https://evil.example"],
                    }
                ]
            return result

    ports = BadPorts()
    if failure == "item-source":
        ports.items[0] = ports.items[0].model_copy(update={"source": "https://evil.example"})
    retriever = (
        Retrieved([])
        if failure == "retrieval"
        else Retrieved(
            [
                PreparedChunk(
                    id="chunk-1", text="Ngu\u1ed3n", source_uri="https://books.example/a", page=1
                )
            ]
        )
    )
    states: list[Progress] = []

    async def progress(state: Progress) -> None:
        states.append(state)

    async def event(value: dict[str, str]) -> None:
        pass

    with pytest.raises(SourceError):
        asyncio.run(
            pipeline(ports, retriever=retriever, retrieval_subject="biology").run(
                TopicInput(goal_vi="biology", mode="quick", tier="free"), progress, event
            )
        )
    assert not ports.items_saved
    if failure != "item-source":
        assert not ports.graph_saved
    assert states[-1].status == "failed"


def test_pipeline_calls_injected_retriever_before_graph() -> None:
    class SelectedPorts(Ports):
        async def build_graph(
            self, goal: str, chunks: Sequence[PreparedChunk], tier: str
        ) -> GraphDraft:
            assert retriever.calls == [("biology", "library-biology", 12)]
            assert [c.id for c in chunks] == ["chunk-1"]
            return await super().build_graph(goal, chunks, tier)

    retriever = Retrieved(
        [PreparedChunk(id="chunk-1", text="Nguồn", source_uri="https://books.example/a", page=1)]
    )

    async def ignore(value: object) -> None:
        pass

    asyncio.run(
        pipeline(SelectedPorts(), retriever=retriever, retrieval_subject="library-biology").run(
            TopicInput(goal_vi="biology", mode="quick", tier="free"), ignore, ignore
        )
    )


def pipeline(ports: Ports, **kwargs: Any) -> TopicPipeline:
    kwargs.setdefault(
        "retriever",
        Retrieved(
            [
                PreparedChunk(
                    id="chunk-1", text="Ngu\u1ed3n", source_uri="https://books.example/a", page=1
                )
            ]
        ),
    )
    kwargs.setdefault("retrieval_subject", "biology")
    return TopicPipeline(ports, **kwargs)


def test_pipeline_cannot_be_constructed_without_retrieval() -> None:
    with pytest.raises(TypeError):
        TopicPipeline(Ports())  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="blank"):
        TopicPipeline(Ports(), retriever=Retrieved([]), retrieval_subject=" ")


def test_failure_trail_sink_error_does_not_prevent_terminal_progress() -> None:
    ports = Ports()
    ports.supported = False
    states = []

    async def progress(value: Progress) -> None:
        states.append(value)

    async def event(value: dict[str, str]) -> None:
        raise RuntimeError("trail storage unavailable")

    with pytest.raises(SourceError):
        asyncio.run(
            pipeline(ports).run(
                TopicInput(goal_vi="biology", mode="quick", tier="free"), progress, event
            )
        )
    assert states[-1].status == "failed" and not states[-1].graph_ready
