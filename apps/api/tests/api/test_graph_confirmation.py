"""Real SQL confirmation through HTTP/P4 guards; model calls are fake fixtures."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.content.learning import graph_revision
from app.content.repository import Repository
from app.main import create_content_app as create_app
from app.services.graph_confirmation import GraphConfirmations
from app.services.learner_sessions import COOKIE_NAME
from tests.content.fakes import FakeGateway, topic
from tests.content.test_runtime_database import database_url as database_url
from tests.content.test_runtime_database import store as store


@dataclass
class Harness:
    client: TestClient
    store: Repository
    learner: str
    models: FakeGateway

    def review(self, subject: str = "python-conditions") -> dict[str, object]:
        response = self.client.get("/graph/review", params={"subject": subject})
        assert response.status_code == 200, response.text
        return response.json()  # type: ignore[no-any-return]

    def body(self) -> dict[str, object]:
        return {
            "subject": "python-conditions",
            "graph_revision": self.review()["graph_revision"],
        }


@pytest.fixture
def harness(store: Repository, database_url: str) -> Iterator[Harness]:
    models = FakeGateway()
    app = create_app(
        Settings(database_url=database_url, api_key="test-key", _env_file=None),
        repository=store,
        gateway=models,
    )
    with TestClient(app, headers={"X-API-Key": "test-key"}) as client:
        response = client.post("/learners", json={"display_name": "Confirmation test"})
        assert response.status_code == 200
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=lax" in response.headers["set-cookie"]
        yield Harness(client, store, response.json()["learner_id"], models)


def test_review_does_not_confirm_or_unlock_learning_and_hint(harness: Harness) -> None:
    review = harness.review()
    assert review["confirmed"] is False
    assert "concepts" in review["graph"]  # type: ignore[operator]
    assert (
        harness.client.post(
            "/placement/next", json={"learner_id": harness.learner, "subject": "python-conditions"}
        ).status_code
        == 409
    )
    assert (
        harness.client.post(
            "/tutor/hint",
            json={
                "learner_id": harness.learner,
                "item_id": "python-conditions-001",
                "level": 1,
                "tier": "free",
            },
        ).status_code
        == 409
    )
    assert harness.models.calls == []


def test_confirmation_is_retry_safe_durable_and_used_by_p4(
    harness: Harness, database_url: str
) -> None:
    body = harness.body()
    first = harness.client.post("/graph/confirm", json=body)
    assert first.status_code == 200, first.text
    assert harness.client.post("/graph/confirm", json=body).json() == first.json()
    assert harness.review()["confirmed"] is True
    # A new application/service instance reads the same persisted record.
    app = create_app(
        Settings(database_url=database_url, api_key="test-key", _env_file=None),
        repository=harness.store,
        gateway=harness.models,
    )
    with TestClient(
        app,
        headers={"X-API-Key": "test-key"},
        cookies={COOKIE_NAME: harness.client.cookies[COOKIE_NAME]},
    ) as reloaded:
        review = reloaded.get(
            "/graph/review", params={"learner_id": harness.learner, "subject": "python-conditions"}
        )
        assert review.json()["confirmed"] is True
        placement = reloaded.post(
            "/placement/next", json={"learner_id": harness.learner, "subject": "python-conditions"}
        )
        assert placement.status_code == 200, placement.text
    approvals = GraphConfirmations(database_url)
    assert approvals(harness.learner, "python-conditions", str(body["graph_revision"]))
    assert not approvals(str(uuid4()), "python-conditions", str(body["graph_revision"]))


def test_changed_graph_rejects_stale_confirmation(harness: Harness) -> None:
    old = harness.body()
    assert harness.client.post("/graph/confirm", json=old).status_code == 200
    with harness.store.transaction() as conn:
        graph = harness.store.graph(conn, "python-conditions").model_copy(deep=True)
    graph.concepts[0].description_vi += " revised"
    harness.store.save_graph("python-conditions", graph)
    current = harness.review()
    assert current["graph_revision"] == graph_revision(graph)
    assert current["graph_revision"] != old["graph_revision"]
    assert current["confirmed"] is False
    stale = harness.client.post("/graph/confirm", json=old)
    assert stale.status_code == 409
    assert (
        harness.client.post(
            "/placement/next", json={"learner_id": harness.learner, "subject": "python-conditions"}
        ).status_code
        == 409
    )
    assert (
        harness.client.post(
            "/graph/confirm", json={**old, "graph_revision": current["graph_revision"]}
        ).status_code
        == 200
    )
    assert harness.review()["confirmed"] is True


def test_confirmation_does_not_transfer_to_another_learner_or_subject(harness: Harness) -> None:
    assert harness.client.post("/graph/confirm", json=harness.body()).status_code == 200
    other = harness.client.post("/learners", json={"display_name": "Other"}).json()["learner_id"]
    response = harness.client.get(
        "/graph/review", params={"learner_id": harness.learner, "subject": "python-conditions"}
    )
    assert response.json()["confirmed"] is False
    assert response.json()["learner_id"] == other
    sources, chunks, graph, _ = topic("fractions")
    harness.store.save_material("fractions", sources, chunks)
    harness.store.save_graph("fractions", graph)
    assert harness.review("fractions")["confirmed"] is False


def test_concurrent_confirmation_creates_one_record(harness: Harness) -> None:
    body = harness.body()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(lambda _: harness.client.post("/graph/confirm", json=body), range(2))
        )
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    with harness.store.transaction() as conn:
        assert conn.execute(
            "select count(*) from learner_graph_confirmations where learner_id=%s",
            (UUID(harness.learner),),
        ).fetchone() == (1,)
        assert conn.execute(
            "select relrowsecurity from pg_class where oid='learner_graph_confirmations'::regclass"
        ).fetchone() == (True,)


def test_invalid_confirmation_does_not_write(harness: Harness) -> None:
    body = harness.body()
    assert (
        harness.client.post("/graph/confirm", json={**body, "graph_revision": "bad"}).status_code
        == 422
    )
    assert (
        harness.client.post("/graph/confirm", json={**body, "learner_id": str(uuid4())}).status_code
        == 422
    )
    assert (
        harness.client.post("/graph/confirm", json={**body, "subject": "missing"}).status_code
        == 404
    )
    assert harness.review()["confirmed"] is False
    assert (
        harness.client.post("/graph/confirm", json=body, headers={"X-API-Key": ""}).status_code
        == 401
    )


def test_session_is_required_hashed_and_expirable(harness: Harness) -> None:
    import hashlib

    token = harness.client.cookies[COOKIE_NAME]
    with harness.store.transaction() as conn:
        row = conn.execute(
            "select token_hash from learner_api_sessions where learner_id=%s",
            (UUID(harness.learner),),
        ).fetchone()
        assert row == (hashlib.sha256(token.encode()).hexdigest(),)
        conn.execute(
            "update learner_api_sessions set issued_at=now()-interval '2 days', "
            "expires_at=now()-interval '1 day' where learner_id=%s",
            (UUID(harness.learner),),
        )
    assert (
        harness.client.post(
            "/graph/confirm", json={"subject": "python-conditions", "graph_revision": "a" * 64}
        ).status_code
        == 401
    )
    harness.client.cookies.clear()
    assert (
        harness.client.get("/graph/review", params={"subject": "python-conditions"}).status_code
        == 401
    )
    harness.client.cookies.set(COOKIE_NAME, "forged")
    assert (
        harness.client.get("/graph/review", params={"subject": "python-conditions"}).status_code
        == 401
    )
