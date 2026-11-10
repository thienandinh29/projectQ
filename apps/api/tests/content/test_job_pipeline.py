"""Real orchestration with in-memory test ports/fake models; not a live-model demo."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.content.gateway import ModelReply
from app.content.models import Graph, Item, ModelIdentity
from app.content.ports import process_claimed_job
from app.content.repository import ContentUnavailable, Repository, StoredItem
from app.guardrails.answerability import is_currently_verified
from app.research.reader import SourceError
from app.schemas import Citation
from tests.content.fakes import FakeGateway, topic


class MemoryRepository(Repository):
    """Test double for SQL storage. Database guarantees are tested separately."""

    def __init__(self) -> None:
        self.sources, self.chunks, self.kg, self.fixture_items = topic()
        self.saved: dict[str, Item] = {}
        self.graph_saved = False
        self.progress: list[tuple[object, ...]] = []
        self.fail_save = False

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        yield self

    def execute(self, query: str, params: tuple[object, ...] = ()) -> "MemoryRepository":
        self.query, self.params = query, params
        if query.startswith("update topic_jobs set status="):
            if params[0] == "ready":
                assert len(self.saved) >= 6
                assert (
                    sum(is_currently_verified(item, self.chunks) for item in self.saved.values())
                    >= 6
                )
            self.progress.append(params)
        return self

    def fetchall(self) -> list[Any]:
        if "s.slug,r.p4_metadata" in self.query:
            source = self.sources[0]
            return [
                (
                    "python-conditions",
                    source.model_dump(mode="json"),
                    source.source_id,
                    source.title,
                    source.author,
                    source.url,
                    source.license,
                    source.version,
                )
            ]
        if "select c.id" in self.query:
            return [
                (c.chunk_id, next(s.url for s in self.sources if s.source_id == c.source_id))
                for c in self.chunks
            ]
        raise AssertionError(self.query)

    def __iter__(self) -> Iterator[Any]:
        return iter(self.fetchall())

    def material(self, conn: Any, ids: list[Any]):  # type: ignore[no-untyped-def]
        assert set(ids) == {c.chunk_id for c in self.chunks}
        return self.sources, self.chunks

    def graph(self, conn: Any, subject: str) -> Graph:
        if not self.graph_saved:
            raise ContentUnavailable("graph not ready")
        return self.kg

    def save_graph(self, subject: str, graph: Graph) -> None:
        self.kg, self.graph_saved = graph, True

    def item_ids(self, conn: Any, subject: str) -> list[str]:
        return list(self.saved)

    def current(self, conn: Any, external_id: str) -> StoredItem | None:
        item = self.saved.get(external_id)
        if item and is_currently_verified(item, self.chunks):
            return StoredItem(uuid4(), "unit-subject", item, self.chunks, self.sources, 0)
        return None

    def save_items(self, subject: str, items: list[Item]) -> None:
        if self.fail_save:
            raise ContentUnavailable("Simulated SQL transaction failure")
        self.saved.update({item.id: item for item in items})

    def misconception_descriptions(self, conn: Any, subject: str) -> dict[tuple[str, str], str]:
        return {
            (i.concept, m.slug): m.description_vi
            for i in self.saved.values()
            for m in i.misconceptions
        }


class Model(FakeGateway):
    def __init__(self) -> None:
        super().__init__()
        self.generate_count = 0
        self.reject = False

    async def generate(
        self,
        *,
        task: str,
        tier: str,
        system: str,
        payload: dict[str, object],
        schema: type[BaseModel],
        exclude_family: str | None = None,
    ) -> ModelReply:
        _, chunks, graph, items = topic()
        if task in {"extract_graph", "generate_items"}:
            if task == "extract_graph":
                data: object = graph.model_dump(mode="json", by_alias=True)
                if "learning_goal" in payload:
                    data = {"relevant_to_goal": True, "graph": data, "reason_vi": "Test only"}
            else:
                self.generate_count += 1
                selected = [items[i] for i in [0, 3, 6, 9, 12, 1]]
                data = {
                    "items": [
                        item.model_dump(
                            mode="json",
                            exclude={
                                "kind",
                                "status",
                                "generator",
                                "verification",
                                "verification_history",
                                "human_review",
                            },
                        )
                        for item in selected
                    ]
                }
            return ModelReply(
                content=data,
                identity=ModelIdentity(
                    provider="fake", model="fake-gemini", family="gemini", identity_source="gateway"
                ),
            )
        if task == "verify_item":
            self.item = next(item for item in items if item.prompt_vi == payload["question"])
            self.chunks = [c for c in chunks if c.chunk_id in self.item.chunk_ids]
            self.overrides = {"supported": False} if self.reject else {}
        return await super().generate(
            task=task,
            tier=tier,
            system=system,
            payload=payload,
            schema=schema,
            exclude_family=exclude_family,
        )


def test_claimed_job_runs_p3_pipeline_p4_generation_gate_and_idempotent_retry() -> None:
    repo, models = MemoryRepository(), Model()
    job: dict[str, object] = {
        "id": uuid4(),
        "goal_vi": "Tôi muốn học Python",
        "tier": "free",
        "mode": "quick",
    }
    asyncio.run(
        process_claimed_job(
            repo, models, job, retriever=Retrieval(repo), retrieval_subject="python"
        )
    )
    first = set(repo.saved)
    assert len(first) == 6 and repo.progress[-1][0] == "ready"
    assert models.generate_count == 1
    asyncio.run(
        process_claimed_job(
            repo, models, job, retriever=Retrieval(repo), retrieval_subject="python"
        )
    )
    assert set(repo.saved) == first and models.generate_count == 1
    assert all("item-" in key for key in first)


@pytest.mark.parametrize("failure", ["rejected", "save_error"])
def test_job_never_becomes_ready_before_verified_content_is_saved(failure: str) -> None:
    repo, models = MemoryRepository(), Model()
    models.reject = failure == "rejected"
    repo.fail_save = failure == "save_error"
    with pytest.raises(SourceError):
        asyncio.run(
            process_claimed_job(
                repo,
                models,
                {"id": uuid4(), "goal_vi": "Python", "tier": "free"},
                retriever=Retrieval(repo),
                retrieval_subject="python",
            )
        )
    assert repo.progress[-1][0] == "failed"
    assert not any(row[0] == "ready" for row in repo.progress)


class Retrieval:
    def __init__(self, repo: MemoryRepository) -> None:
        self.repo = repo

    async def search(self, query: str, subject: str, k: int = 5) -> list[Citation]:
        return [
            Citation(
                chunk_id=str(c.chunk_id),
                source_title="Book",
                license=c.license,
                source_uri=next(s.url for s in self.repo.sources if s.source_id == c.source_id),
                page=c.page,
                content=c.content,
                score=0.8,
            )
            for c in self.repo.chunks[:k]
        ]


@pytest.mark.parametrize("chosen", ["python-conditions", None, "not-in-catalog"])
def test_auto_library_selection_validates_catalog_and_never_falls_back(chosen: str | None) -> None:
    from app.content.ports import ContentPorts

    class Selector(FakeGateway):
        async def generate(self, **kwargs: object) -> ModelReply:
            assert kwargs["task"] == "select_library"
            assert kwargs["payload"]["learning_goal"] == "Requested subject"  # type: ignore[index]
            return ModelReply(
                content={"subject": chosen, "reason_vi": "Test only"}, identity=self.item.generator
            )

    ports = ContentPorts(MemoryRepository(), Selector(), "new-topic", library_subject="auto")
    if chosen == "python-conditions":
        assert asyncio.run(ports.quick_sources("Requested subject"))
        assert ports.library_subject == chosen
    else:
        with pytest.raises(SourceError):
            asyncio.run(ports.quick_sources("Requested subject"))
        assert ports.library_subject == "auto"


def test_one_content_repair_fills_missing_concept_without_overwriting_good_items() -> None:
    class RepairModel(Model):
        async def generate(self, **kwargs: Any) -> ModelReply:
            payload = kwargs["payload"]
            _, _, _, items = topic()
            if kwargs["task"] == "generate_items" and payload["count"] != 6:
                self.generate_count += 1
                targets = {c["slug"] for c in payload["graph"]["concepts"]}
                candidates = [i for i in items if i.concept in targets][: payload["count"]]
                return ModelReply(
                    content={
                        "items": [
                            i.model_dump(
                                mode="json",
                                exclude={
                                    "kind",
                                    "status",
                                    "generator",
                                    "verification",
                                    "verification_history",
                                    "human_review",
                                },
                            )
                            for i in candidates
                        ]
                    },
                    identity=items[0].generator,
                )
            reply = await super().generate(**kwargs)
            if kwargs["task"] == "verify_item" and self.generate_count == 1:
                original = next(i for i in items if i.prompt_vi == payload["question"])
                if original.concept == "elif-order":
                    reply = reply.model_copy(
                        update={
                            "content": {**cast(dict[str, Any], reply.content), "supported": False}
                        }
                    )
            return reply

    repo, models = MemoryRepository(), RepairModel()
    asyncio.run(
        process_claimed_job(
            repo,
            models,
            {"id": uuid4(), "goal_vi": "Python", "tier": "free", "mode": "quick"},
            retriever=Retrieval(repo),
            retrieval_subject="python",
        )
    )
    assert models.generate_count == 2
    assert repo.progress[-1][0] == "ready"
    assert len(repo.saved) == 8
    verified = [i for i in repo.saved.values() if is_currently_verified(i, repo.chunks)]
    assert len(verified) == 7
    assert {i.concept for i in verified} == {c.slug for c in repo.kg.concepts}


@pytest.mark.parametrize("always_invalid", [False, True])
def test_provenance_failure_uses_only_one_repair_and_never_publishes_invalid_items(
    always_invalid: bool,
) -> None:
    class InvalidProvenance(Model):
        async def generate(self, **kwargs: Any) -> ModelReply:
            if kwargs["task"] == "generate_items" and self.generate_count == 1:
                assert "source_ids must exactly" in kwargs["payload"]["repair_feedback"]
            reply = await super().generate(**kwargs)
            if kwargs["task"] == "generate_items" and (always_invalid or self.generate_count == 1):
                cast(dict[str, Any], reply.content)["items"][0]["source_ids"] = ["invented-source"]
            return reply

    repo, models = MemoryRepository(), InvalidProvenance()
    work = process_claimed_job(
        repo,
        models,
        {"id": uuid4(), "goal_vi": "Python", "tier": "free", "mode": "quick"},
        retriever=Retrieval(repo),
        retrieval_subject="python",
    )
    if always_invalid:
        with pytest.raises(SourceError, match="cấu trúc"):
            asyncio.run(work)
        assert repo.progress[-1][0] == "failed" and not repo.saved
    else:
        asyncio.run(work)
        assert repo.progress[-1][0] == "ready"
        assert all(is_currently_verified(i, repo.chunks) for i in repo.saved.values())
    assert models.generate_count == 2


@pytest.mark.parametrize("checkpoint", [False, True])
def test_limited_first_lesson_keeps_six_verified_questions_for_three_concepts(
    checkpoint: bool,
) -> None:
    class SmallLesson(Model):
        async def generate(self, **kwargs: Any) -> ModelReply:
            reply = await super().generate(**kwargs)
            if kwargs["task"] == "generate_items":
                targets = {c["slug"] for c in kwargs["payload"]["graph"]["concepts"]}
                candidates = [
                    i
                    for i in cast(dict[str, Any], reply.content)["items"]
                    if i["concept"] in targets
                ]
                cast(dict[str, Any], reply.content)["items"] = [
                    {**candidates[n % len(candidates)], "id": f"draft-{n}"}
                    for n in range(kwargs["payload"]["count"])
                ]
            return reply

    repo = MemoryRepository()
    repo.graph_saved = checkpoint
    asyncio.run(
        process_claimed_job(
            repo,
            SmallLesson(),
            {"id": uuid4(), "goal_vi": "Python", "tier": "free", "mode": "quick"},
            retriever=Retrieval(repo),
            retrieval_subject="python",
            max_concepts=3,
        )
    )
    assert repo.progress[-1][0] == "ready" and len(repo.kg.concepts) == 3
    assert len(repo.saved) == 6
    assert {i.concept for i in repo.saved.values()} == {c.slug for c in repo.kg.concepts}
    assert all(is_currently_verified(i, repo.chunks) for i in repo.saved.values())
