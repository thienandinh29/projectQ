"""Focused offline guards. No provider or PostgreSQL success is implied."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api import tutor
from app.content.backends import TutorBackend
from app.content.models import Item
from app.content.pipeline import generate_items
from app.content.repository import Repository, StoredItem
from app.guardrails.answerability import blind_request, invalidate_stale, verify_item
from app.jobs.worker import run_once
from app.tutor.hints import HintDraft, obvious_leak
from tests.content.fakes import FakeGateway, topic


def test_generation_permission_checked_even_when_graph_already_exists() -> None:
    sources, chunks, graph, _ = topic("fractions")
    gateway = FakeGateway()
    with pytest.raises(ValueError, match="permission"):
        asyncio.run(generate_items(graph, chunks, sources, gateway, count=6))
    assert gateway.calls == []


def test_generator_option_ids_cannot_leak_the_answer_into_blind_request() -> None:
    fake = FakeGateway()
    data = fake.item.model_dump(mode="json")
    correct = next(o for o in data["options"] if o["correct"])
    correct["id"] = data["answer_id"] = "THIS_IS_THE_CORRECT_ANSWER"
    item = Item.model_validate(data)
    request = blind_request(item, fake.chunks)
    assert "THIS_IS_THE_CORRECT_ANSWER" not in request.model_dump_json()
    assert [o.id for o in request.options] == [f"choice-{i}" for i in range(4)]


def test_old_audits_survive_reverification_and_invalidation() -> None:
    fake = FakeGateway()
    first = asyncio.run(verify_item(fake.item, fake.chunks, fake))
    second = asyncio.run(verify_item(first, fake.chunks, fake))
    assert first.verification in second.verification_history
    stale = invalidate_stale(second.model_copy(update={"prompt_vi": "Đề đã sửa"}), fake.chunks)
    assert stale.status == "needs_review"
    assert stale.verification == second.verification
    assert stale.verification_history == second.verification_history


def test_opaque_choice_identifier_is_also_a_hint_leak() -> None:
    fake = FakeGateway()
    assert obvious_leak(
        fake.item, HintDraft(hint_vi="Hãy chọn choice-0.", chunk_ids=fake.item.chunk_ids)
    )


def test_p2_worker_passes_committed_claim_to_content_processor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        active = False

        def __enter__(self) -> "Connection":
            self.active = True
            return self

        def __exit__(self, *args: object) -> None:
            self.active = False

    connection = Connection()
    job = {"id": uuid4(), "fixture": False, "tier": "free"}
    monkeypatch.setattr("app.jobs.worker.psycopg.connect", lambda url: connection)
    monkeypatch.setattr("app.jobs.worker.claim", lambda conn: job)

    def processor(actual: dict[str, Any]) -> None:
        assert not connection.active  # P2 transaction closed before long model work.
        assert actual is job

    assert run_once("not-a-real-database", processor=processor)


def test_hint_publication_rechecks_revision_after_model_await() -> None:
    sources, chunks, _, items = topic()
    old = StoredItem(uuid4(), "python", items[0], chunks, sources, 1)
    changed = StoredItem(old.db_id, old.subject, old.item, old.chunks, old.sources, 2)

    class Store(Repository):
        def current(self, conn: Any, external_id: str) -> StoredItem:
            return changed

    fake = FakeGateway()
    assert not Store(lambda: None).save_hint(None, old, uuid4(), "cache", 1, None)  # type: ignore[arg-type,return-value]
    assert fake.calls == []


def test_tutor_backend_never_releases_unverified_content() -> None:
    class Connection:
        def execute(self, *args: object) -> "Connection":
            return self

        def fetchone(self) -> tuple[int]:
            return (1,)

    class Store:
        @contextmanager
        def transaction(self) -> Iterator[Connection]:
            yield Connection()

        def servable(self, *args: object) -> None:
            return None

    backend = TutorBackend(Store(), FakeGateway())  # type: ignore[arg-type]
    with pytest.raises(HTTPException) as failure:
        asyncio.run(
            backend.hint(
                tutor.HintInput(learner_id=str(uuid4()), item_id="pending", level=1, tier="free")
            )
        )
    assert failure.value.status_code == 503


def test_runtime_factory_binds_existing_p3_routes_without_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings
    from app.content.runtime import create_app

    class Pool:
        def close(self) -> None:
            pass

    class Store:
        def require_schema(self) -> None:
            pass

    monkeypatch.setattr("app.main.create_pool", lambda url: Pool())
    app = create_app(
        Settings(allow_unauthenticated_local_dev=True, _env_file=None),
        repository=Store(),  # type: ignore[arg-type]
        gateway=FakeGateway(),
    )
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
        assert "/tutor/hint" in schema["paths"] and "/topics" in schema["paths"]
        assert app.state.p4_repository.__class__ is Store
        assert "fixture" not in schema["info"]["title"].casefold()


@pytest.mark.parametrize("ready", [False, True])
def test_partial_topic_job_is_not_servable(ready: bool) -> None:
    sources, chunks, _, items = topic()
    bundle = StoredItem(uuid4(), "topic-unit", items[0], chunks, sources, 0)

    class Store(Repository):
        def __init__(self) -> None:
            pass

        def current(self, *args: Any) -> StoredItem:
            return bundle

    class Connection:
        def execute(self, *args: object) -> "Connection":
            return self

        def fetchone(self) -> tuple[int] | None:
            return (1,) if ready else None

    result = Store().servable(Connection(), bundle.item.id)  # type: ignore[arg-type]
    assert (result is not None) is ready
