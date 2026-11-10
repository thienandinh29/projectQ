from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Timer
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.jobs.queue import claim, enqueue, finish, snapshot
from app.jobs.worker import run_once
from app.main import create_app
from app.services.learning import save_attempt, save_mastery, save_review


def test_claim_skips_locked_job(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        ids = {enqueue(conn, "Một", "free"), enqueue(conn, "Hai", "pro")}
    with psycopg.connect(database_url) as first:
        job = claim(first)
        assert job is not None
        with ThreadPoolExecutor() as executor:

            def other_claim():  # type: ignore[no-untyped-def]
                with psycopg.connect(database_url) as second:
                    return claim(second)

            other = executor.submit(other_claim).result(timeout=5)
        assert other is not None
        assert {job["id"], other["id"]} == ids
    with psycopg.connect(database_url) as conn:
        conn.execute("delete from topic_jobs")


def test_worker_fixture_and_missing_pipeline(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        real_id = enqueue(conn, "Học Python", "free")
        fixture_id = enqueue(conn, "Mô phỏng", "pro", fixture=True)
    assert run_once(database_url, allow_fixture=True)
    assert run_once(database_url, allow_fixture=True)
    assert not run_once(database_url)
    with psycopg.connect(database_url) as conn:
        real = snapshot(conn, real_id)
        fixture = snapshot(conn, fixture_id)
        assert real is not None and real["status"] == "failed"
        assert fixture is not None and fixture["status"] == "ready"
        assert not fixture["graph_ready"] and not fixture["items_ready"]
    with TestClient(create_app(Settings(database_url=database_url, api_key="local"))) as client:
        assert client.get(f"/topics/{fixture_id}").status_code == 401
        headers = {"X-API-Key": "local"}
        response = client.get(f"/topics/{fixture_id}", headers=headers)
        assert response.json() == fixture
        assert response.headers["x-data-fixture"] == "true"
        assert response.headers["x-request-id"]
        # Reconnect always receives the current snapshot, even with a stale cursor.
        for _ in range(2):
            events = client.get(
                f"/topics/{fixture_id}/events",
                headers={
                    **headers,
                    "Last-Event-ID": "old",
                },
            )
            assert '"status": "ready"' in events.text
            assert "event: state\n" in events.text
        assert client.get(f"/topics/{uuid4()}", headers=headers).status_code == 404
        assert client.get("/topics/cached", headers=headers).json() == {"topics": []}
        assert (
            client.post("/learners", json={"display_name": "  "}, headers=headers).status_code
            == 422
        )
        assert (
            client.post("/learners", json={"display_name": "An"}, headers=headers).status_code
            == 200
        )
        preflight = client.options(
            "/learners",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "X-API-Key",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"
    with psycopg.connect(database_url) as conn:
        conn.execute("delete from topic_jobs")


def test_learning_writes_atomic(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        learner = conn.execute(
            "insert into learners(display_name) values ('Test') returning id"
        ).fetchone()
        subject = conn.execute(
            "insert into subjects(slug,name_vi,name_en) "
            "values ('service-test','Test','Test') returning id"
        ).fetchone()
        assert learner and subject
        concept = conn.execute(
            "insert into concepts(subject_id,slug,name_vi,name_en) "
            "values (%s,'c','C','C') returning id",
            (subject[0],),
        ).fetchone()
        assert concept
        item = conn.execute(
            "insert into items(concept_id,kind,prompt) values (%s,'mcq','?') returning id",
            (concept[0],),
        ).fetchone()
        assert item
        with pytest.raises(ValueError), conn.transaction():
            save_attempt(conn, learner_id=learner[0], item_id=item[0], answer={}, correct=True)
            save_mastery(conn, learner[0], concept[0], 2)
        assert conn.execute(
            "select count(*) from attempts where learner_id=%s", (learner[0],)
        ).fetchone() == (0,)
        save_mastery(conn, learner[0], concept[0], 0.3)
        save_mastery(conn, learner[0], concept[0], 0.9)
        now = datetime.now(UTC)
        save_review(conn, learner[0], concept[0], {"state": 1}, now)
        save_review(conn, learner[0], concept[0], {"state": 2}, now)
        assert conn.execute(
            "select fsrs_state from review_cards where learner_id=%s", (learner[0],)
        ).fetchone() == ({"state": 2},)
        assert conn.execute(
            "select count(*) from mastery where learner_id=%s", (learner[0],)
        ).fetchone() == (1,)


def test_sse_heartbeat_and_progress(database_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.main.HEARTBEAT_SECONDS", 0)
    with psycopg.connect(database_url) as conn:
        topic_id = enqueue(conn, "Heartbeat fixture", "free", fixture=True)

    def complete() -> None:
        with psycopg.connect(database_url) as conn:
            conn.execute("update topic_jobs set status='researching' where id=%s", (topic_id,))
            finish(conn, topic_id, fixture=True)

    with TestClient(
        create_app(
            Settings(
                _env_file=None, database_url=database_url, allow_unauthenticated_local_dev=True
            )
        )
    ) as client:
        timer = Timer(0.2, complete)
        timer.start()
        try:
            response = client.get(f"/topics/{topic_id}/events")
        finally:
            timer.join()
        assert "event: heartbeat" in response.text
        assert '"status": "queued"' in response.text
        assert '"status": "ready"' in response.text
    with psycopg.connect(database_url) as conn:
        conn.execute("delete from topic_jobs where id=%s", (topic_id,))
