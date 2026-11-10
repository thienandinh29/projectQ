"""Actual PostgreSQL adapter/trigger tests. --no-db skips these explicitly.

Model responses here are fake fixtures and never establish real content quality.
"""

import asyncio
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from app.config import Settings
from app.content.demo import install_schema, local_only
from app.content.learning import graph_revision
from app.content.repository import Repository
from app.content.runtime import create_app
from app.db import create_pool
from app.guardrails.answerability import verify_item
from app.services.topics import TopicsService
from app.uploads.reader import Document, Page
from tests.content.fakes import FakeGateway, topic


class ConfirmedGraphs:
    """Test-only approvals: never grant confirmation to an unrelated session."""

    def __init__(self) -> None:
        self.approved: set[tuple[str, str, str]] = set()

    def __call__(self, learner: str, subject: str, revision: str) -> bool:
        return (learner, subject, revision) in self.approved

    def confirm(self, store: Repository, learner: str, subject: str) -> None:
        with store.transaction() as conn:
            revision = graph_revision(store.graph(conn, subject))
        self.approved.add((learner, subject, revision))


@pytest.fixture
def confirmed_graphs() -> ConfirmedGraphs:
    return ConfirmedGraphs()


@pytest.fixture
def store(database_url: str) -> Iterator[Repository]:
    with psycopg.connect(database_url) as conn:
        conn.execute("delete from subjects where slug='python-conditions'")
    with create_pool(database_url) as pool:
        repo = Repository(lambda: pool)
        sources, chunks, graph, items = topic()
        repo.save_material("python-conditions", sources, chunks)
        repo.save_graph("python-conditions", graph)
        checked = []
        for item in items:
            fake = FakeGateway()
            fake.item = item
            fake.chunks = [c for c in chunks if c.chunk_id in item.chunk_ids]
            checked.append(asyncio.run(verify_item(item, chunks, fake)))
        repo.save_items("python-conditions", checked)
        yield repo


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    # This module never alters the base suite's migrated database.
    admin_url = os.environ.get(
        "TEST_DATABASE_ADMIN_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
    )
    local_only(admin_url, admin=True)
    name = "nodetrail_test_p4_" + uuid4().hex
    with psycopg.connect(admin_url, autocommit=True, connect_timeout=2) as admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        url = admin_url.rsplit("/", 1)[0] + "/" + name
        try:
            install_schema(url)
            yield url
        finally:
            admin.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))


def test_repository_preserves_ids_and_retry_does_not_duplicate(store: Repository) -> None:
    with store.transaction() as conn:
        ids = store.item_ids(conn, "python-conditions")
        bundles = [store.current(conn, key) for key in ids]
        assert all(b is not None for b in bundles)
    store.save_items("python-conditions", [b.item for b in bundles if b])
    with store.transaction() as conn:
        assert store.item_ids(conn, "python-conditions") == ids
        assert conn.execute(
            "select count(*) from items where external_id=any(%s)", (ids,)
        ).fetchone() == (15,)
        _, chunks, _, _ = topic()
        actual = {
            r[0]
            for r in conn.execute(
                "select id from chunks where id=any(%s)", ([c.chunk_id for c in chunks],)
            )
        }
        assert actual == {c.chunk_id for c in chunks}


@pytest.mark.parametrize(
    "mutation",
    [
        "option_label",
        "option_key",
        "option_insert",
        "option_delete",
        "chunk_text",
        "chunk_relation",
        "concept_citation",
        "prompt",
    ],
)
def test_content_edits_atomically_invalidate_items_and_hint_cache(
    store: Repository, mutation: str
) -> None:
    from psycopg.types.json import Jsonb

    with store.transaction() as conn:
        bundle = store.current(conn, "python-conditions-001")
        assert bundle
        learner = uuid4()
        conn.execute("insert into learners(id,display_name) values(%s,'Test')", (learner,))
        conn.execute(
            "insert into p4_hint_cache(item_id,learner_id,cache_key,item_hash,level,attempt) "
            "values(%s,%s,%s,%s,1,%s)",
            (bundle.db_id, learner, str(learner), bundle.fingerprint, Jsonb({"fixture": True})),
        )
        if mutation == "option_label":
            conn.execute(
                "update item_options set label=label||' sửa' where item_id=%s", (bundle.db_id,)
            )
        elif mutation == "option_key":
            conn.execute(
                "update item_options set is_correct=not is_correct,misconception_id=null "
                "where item_id=%s",
                (bundle.db_id,),
            )
        elif mutation == "option_insert":
            conn.execute(
                "insert into item_options(item_id,label,is_correct,position) "
                "values(%s,'Mới',false,99)",
                (bundle.db_id,),
            )
        elif mutation == "option_delete":
            conn.execute(
                "delete from item_options where item_id=%s and position=0", (bundle.db_id,)
            )
        elif mutation == "chunk_text":
            conn.execute(
                "update chunks set content=content||' sửa' where id=%s", (bundle.item.chunk_ids[0],)
            )
        elif mutation == "chunk_relation":
            conn.execute("update items set chunk_ids=%s where id=%s", ([], bundle.db_id))
        elif mutation == "concept_citation":
            conn.execute(
                "delete from concept_sources where concept_id=(select concept"
                "_id from items where id=%s)",
                (bundle.db_id,),
            )
        else:
            conn.execute("update items set prompt=prompt||' sửa' where id=%s", (bundle.db_id,))
        assert conn.execute("select status from items where id=%s", (bundle.db_id,)).fetchone() == (
            "needs_review",
        )
        assert conn.execute(
            "select invalidated_at is not null from p4_hint_cache where item_id=%s", (bundle.db_id,)
        ).fetchone() == (True,)
        assert conn.execute(
            "select count(*)>0 from p4_verification_history where item_id"
            "=%s and kind='invalidation'",
            (bundle.db_id,),
        ).fetchone() == (True,)
    with store.transaction() as conn:
        assert store.current(conn, bundle.item.id) is None


def test_http_learning_and_verified_hint_use_real_repository_with_fake_models(
    store: Repository, database_url: str, confirmed_graphs: ConfirmedGraphs
) -> None:
    fake = FakeGateway()
    app = create_app(
        Settings(database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None),
        repository=store,
        gateway=fake,
        confirmation=confirmed_graphs,
    )
    with TestClient(app) as client:
        learner = client.post("/learners", json={"display_name": "P4 DB test"}).json()["learner_id"]
        confirmed_graphs.confirm(store, learner, "python-conditions")
        placement = client.post(
            "/placement/next", json={"learner_id": learner, "subject": "python-conditions"}
        )
        assert placement.status_code == 200
        public = placement.json()["item"]
        assert set(public) == {"id", "kind", "prompt_vi", "options"}
        with store.transaction() as conn:
            bundle = store.current(conn, public["id"])
            assert bundle
        fake.item = bundle.item
        fake.chunks = bundle.chunks
        wrong = next(i for i, o in enumerate(bundle.item.options) if not o.correct)
        attempt = client.post(
            "/attempts",
            json={"learner_id": learner, "item_id": public["id"], "answer": wrong, "hints_used": 0},
        )
        assert attempt.status_code == 200 and attempt.json()["correct"] is False
        assert attempt.json()["traces"]
        assert "remediation" not in attempt.json()
        with store.transaction() as conn:
            assert conn.execute(
                "select remediation_origin from p4_learning_sessions where learner_id=%s",
                (learner,),
            ).fetchone() == (None,)
        hint = client.post(
            "/tutor/hint",
            json={"learner_id": learner, "item_id": public["id"], "level": 1, "tier": "free"},
        )
        assert hint.status_code == 200 and hint.json()["citations"]
        assert set(hint.json()) == {"hint_vi", "citations"}
        fake.overrides = {"no_answer_leak": False}
        denied = client.post(
            "/tutor/hint",
            json={"learner_id": learner, "item_id": public["id"], "level": 2, "tier": "free"},
        )
        assert denied.status_code == 503


def test_practice_exhaustion_reuses_oldest_answered_item(
    store: Repository, database_url: str, confirmed_graphs: ConfirmedGraphs
) -> None:
    _, chunks, graph, items = topic()
    graph = graph.model_copy(update={"concepts": [graph.concepts[0]], "edges": []})
    store.save_graph("python-conditions", graph)
    checked = []
    for item, difficulty in zip(items[:2], (0.3, 0.6), strict=True):
        item = item.model_copy(update={"difficulty": difficulty})
        fake = FakeGateway()
        fake.item = item
        fake.chunks = [c for c in chunks if c.chunk_id in item.chunk_ids]
        checked.append(asyncio.run(verify_item(item, chunks, fake)))
    store.save_items("python-conditions", checked)
    with store.transaction() as conn:
        conn.execute("update items set status='needs_review' where external_id=%s", (items[2].id,))
    app = create_app(
        Settings(database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None),
        repository=store,
        gateway=FakeGateway(),
        confirmation=confirmed_graphs,
    )
    with TestClient(app) as client:
        learner = client.post("/learners", json={"display_name": "Exhaustion"}).json()["learner_id"]
        confirmed_graphs.confirm(store, learner, "python-conditions")
        served = []
        for _ in range(4):
            response = client.get(
                "/next-item", params={"learner_id": learner, "subject": "python-conditions"}
            )
            assert response.status_code == 200, response.text
            key = response.json()["item"]["id"]
            served.append(key)
            item = next(i for i in checked if i.id == key)
            wrong = next(n for n, option in enumerate(item.options) if not option.correct)
            result = client.post(
                "/attempts", json={"learner_id": learner, "item_id": key, "answer": wrong}
            )
            assert result.status_code == 200, result.text
        assert served == [checked[0].id, checked[1].id, checked[0].id, checked[1].id]


def test_practice_skips_a_concept_without_usable_items(
    store: Repository, database_url: str, confirmed_graphs: ConfirmedGraphs
) -> None:
    _, _, graph, _ = topic()
    graph = graph.model_copy(update={"concepts": graph.concepts[:2], "edges": []})
    store.save_graph("python-conditions", graph)
    # Rebuilding a graph invalidates its items; re-verify only comparison.
    _, chunks, _, items = topic()
    checked = []
    for item in items[3:6]:
        fake = FakeGateway()
        fake.item = item
        fake.chunks = [c for c in chunks if c.chunk_id in item.chunk_ids]
        checked.append(asyncio.run(verify_item(item, chunks, fake)))
    store.save_items("python-conditions", checked)
    app = create_app(
        Settings(database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None),
        repository=store,
        gateway=FakeGateway(),
        confirmation=confirmed_graphs,
    )
    with TestClient(app) as client:
        learner = client.post("/learners", json={"display_name": "Skip empty"}).json()["learner_id"]
        confirmed_graphs.confirm(store, learner, "python-conditions")
        response = client.get(
            "/next-item", params={"learner_id": learner, "subject": "python-conditions"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["item"]["id"] in {i.id for i in checked}


def test_retried_attempt_replays_once_under_concurrency(
    store: Repository, database_url: str, confirmed_graphs: ConfirmedGraphs
) -> None:
    app = create_app(
        Settings(database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None),
        repository=store,
        gateway=FakeGateway(),
        confirmation=confirmed_graphs,
    )
    with TestClient(app) as client:
        learner = client.post("/learners", json={"display_name": "Retry"}).json()["learner_id"]
        confirmed_graphs.confirm(store, learner, "python-conditions")
        item = client.post(
            "/placement/next", json={"learner_id": learner, "subject": "python-conditions"}
        ).json()["item"]
        body = {
            "learner_id": learner,
            "item_id": item["id"],
            "answer": 0,
            "client_attempt_id": str(uuid4()),
        }
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: client.post("/attempts", json=body), range(2)))
        assert [r.status_code for r in responses] == [200, 200]
        assert responses[0].json() == responses[1].json()
        assert client.post("/attempts", json=body | {"answer": 1}).status_code == 409
        with store.transaction() as conn:
            conn.execute(
                "update items set prompt=prompt||' edited' where external_id=%s", (item["id"],)
            )
        assert client.post("/attempts", json=body).json() == responses[0].json()
        assert client.post("/attempts", json=body | {"answer": 1}).status_code == 409
    with store.transaction() as conn:
        assert conn.execute(
            "select count(*) from attempts where learner_id=%s", (learner,)
        ).fetchone() == (1,)
        assert conn.execute(
            "select count(*) from attempt_replays where learner_id=%s", (learner,)
        ).fetchone() == (1,)


@pytest.mark.parametrize("demo_enabled", [False, True])
@pytest.mark.parametrize("consented", [False, True])
def test_uploaded_topic_hints_require_demo_mode_and_stored_consent(
    store: Repository,
    database_url: str,
    demo_enabled: bool,
    consented: bool,
    confirmed_graphs: ConfirmedGraphs,
) -> None:
    sources, chunks, _, items = topic()
    sources = [source.model_copy(update={"version": "uploaded document"}) for source in sources]
    store.save_material("python-conditions", sources, chunks)
    fake = FakeGateway()
    fake.item = items[0]
    fake.chunks = [c for c in chunks if c.chunk_id in fake.item.chunk_ids]
    checked = asyncio.run(verify_item(fake.item, chunks, fake))
    store.save_items("python-conditions", [checked])
    for source in sources:
        with store.transaction() as conn:
            conn.execute("delete from uploads where source_uri=%s", (source.url,))
        asyncio.run(
            TopicsService(store.pool).persist_upload(
                Document(source.url, (Page(1, "Public synthetic upload material."),), True),
                None,
                None,
                demo_consent=consented,
            )
        )
    fake.calls.clear()
    app = create_app(
        Settings(
            database_url=database_url,
            allow_unauthenticated_local_dev=True,
            demo_uploads_enabled=demo_enabled,
            _env_file=None,
        ),
        repository=store,
        gateway=fake,
        confirmation=confirmed_graphs,
    )
    with TestClient(app) as client:
        learner = client.post("/learners", json={"display_name": "Consent check"}).json()[
            "learner_id"
        ]
        confirmed_graphs.confirm(store, learner, "python-conditions")
        response = client.post(
            "/tutor/hint",
            json={
                "learner_id": learner,
                "item_id": checked.id,
                "level": 1,
                "tier": "free",
            },
        )
    if demo_enabled and consented:
        assert response.status_code == 200, response.text
        assert fake.calls
    else:
        assert response.status_code == 403
        assert not fake.calls
