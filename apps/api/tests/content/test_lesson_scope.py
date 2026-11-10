import asyncio
from typing import Any

import pytest

from app.content.gateway import ModelReply
from app.content.learning import first_lesson_graph
from app.content.pipeline import generate_graph
from tests.content.fakes import FakeGateway, topic


def test_small_lesson_preserves_all_prerequisites_and_source_references() -> None:
    _, _, graph, _ = topic()
    # Input order must not allow a child to enter the lesson before its prerequisites.
    graph = graph.model_copy(update={"concepts": list(reversed(graph.concepts))})
    lesson = first_lesson_graph(graph, 3)
    slugs = {c.slug for c in lesson.concepts}
    assert len(slugs) == 3
    assert all(e.prerequisite in slugs for e in graph.edges if e.to in slugs)
    assert all(c.chunk_ids and c.sources for c in lesson.concepts)


def test_empty_lesson_is_not_allowed() -> None:
    _, _, graph, _ = topic()
    with pytest.raises(ValueError):
        first_lesson_graph(graph, 0)


def test_generator_cannot_expand_the_requested_first_lesson_limit() -> None:
    sources, chunks, graph, _ = topic()

    class Oversized(FakeGateway):
        async def generate(self, **kwargs: Any) -> ModelReply:
            assert "at most 3" in kwargs["system"]
            return ModelReply(
                content={
                    "relevant_to_goal": True,
                    "graph": graph.model_dump(mode="json", by_alias=True),
                    "reason_vi": "Fixture",
                },
                identity=self.item.generator,
            )

    result = asyncio.run(
        generate_graph(chunks, sources, Oversized(), goal="Python", max_concepts=3)
    )
    assert len(result.concepts) == 3
