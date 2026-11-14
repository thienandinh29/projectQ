"""Essays through the API and the worker (specs/writing/step-2.1.md)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from app.api import writing as writing_routes
from app.services.budget import Budget, spent_today
from app.services.writing import CONSENT, WritingService, process_next_essay

WRITING = Path(__file__).resolve().parents[3] / "data" / "writing"
NOW = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)
ESSAY = "Cities are crowded. However, buses help.\n\nIn conclusion, plan better."
Setup = tuple[WritingService, str, str]


def drain(db: str, writing_dir: Path) -> int:
    """Process every queued essay: the test database is shared, so older essays may be waiting."""
    n = 0
    while process_next_essay(db, writing_dir):
        n += 1
    return n


@pytest.fixture
def setup(database_url: str) -> Iterator[Setup]:
    pool = ConnectionPool(database_url, open=True)
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "insert into learners(display_name) values ('W') returning id"
        ).fetchone()
        assert row
    learner = str(row[0])
    yield (
        WritingService(lambda: pool, WRITING, draft_learners=learner, daily_essays=2),
        learner,
        database_url,
    )
    pool.close()


def test_draft_prompts_only_for_permitted_learners(setup: Setup, database_url: str) -> None:
    svc, learner, _ = setup
    assert svc.prompts(learner)  # the owner sees the draft starter prompts
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "insert into learners(display_name) values ('X') returning id"
        ).fetchone()
        assert row
    assert svc.prompts(str(row[0])) == []  # nobody else, until reviewed
    with pytest.raises(HTTPException) as err:
        svc.submit(str(row[0]), "t2-plastic-ban", ESSAY, CONSENT)
    assert err.value.status_code == 404


def test_an_essay_is_queued_then_analysed_by_the_worker(setup: Setup) -> None:
    svc, learner, db = setup
    essay_id = svc.submit(learner, "t2-plastic-ban", ESSAY, CONSENT, now=NOW)
    queued = svc.get(learner, essay_id)
    assert queued["status"] == "queued" and queued["result"] is None
    assert queued["prompt"]["id"] == "t2-plastic-ban"
    assert drain(db, WRITING) >= 1
    assert process_next_essay(db, WRITING) is False  # nothing left
    done = svc.get(learner, essay_id)
    assert done["status"] == "done"
    assert done["result"]["words"] == 10 and done["result"]["paragraphs"] == 2
    assert done["result"]["long_enough"] is False and "note_vi" in done["result"]
    assert svc.list(learner)[0] == {**svc.list(learner)[0], "id": essay_id, "words": 10}


def test_consent_length_and_the_daily_limit(setup: Setup) -> None:
    svc, learner, _ = setup
    for text, consent, code in [
        (ESSAY, "no", 422),
        ("   ", CONSENT, 422),
        ("x" * 12_001, CONSENT, 422),
    ]:
        with pytest.raises(HTTPException) as err:
            svc.submit(learner, "t2-plastic-ban", text, consent, now=NOW)
        assert err.value.status_code == code
    svc.submit(learner, "t2-plastic-ban", ESSAY, CONSENT, now=NOW)
    svc.submit(learner, "t2-city-traffic", ESSAY, CONSENT, now=NOW)
    with pytest.raises(HTTPException) as err:
        svc.submit(learner, "t2-city-traffic", ESSAY, CONSENT, now=NOW + timedelta(hours=1))
    assert err.value.status_code == 429 and "2 bài" in str(err.value.detail)
    svc.submit(learner, "t2-city-traffic", ESSAY, CONSENT, now=NOW + timedelta(days=1))  # tomorrow


def test_essays_are_private_and_deletable(setup: Setup, database_url: str) -> None:
    svc, learner, _ = setup
    essay_id = svc.submit(learner, "t2-plastic-ban", ESSAY, CONSENT, now=NOW)
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "insert into learners(display_name) values ('Y') returning id"
        ).fetchone()
        assert row
    other = str(row[0])
    for call in (lambda: svc.get(other, essay_id), lambda: svc.delete(other, essay_id),
                 lambda: svc.get(learner, "not-a-uuid")):  # fmt: skip
        with pytest.raises(HTTPException) as err:
            call()
        assert err.value.status_code == 404
    svc.delete(learner, essay_id)
    with pytest.raises(HTTPException):
        svc.get(learner, essay_id)
    with psycopg.connect(database_url) as conn:
        left = conn.execute("select count(*) from essays where id=%s", (essay_id,)).fetchone()
    assert left == (0,)


def test_a_failed_analysis_is_reported_not_hidden(setup: Setup, tmp_path: Path) -> None:
    svc, learner, db = setup
    essay_id = svc.submit(learner, "t2-plastic-ban", ESSAY, CONSENT, now=NOW)
    assert drain(db, tmp_path) >= 1  # no prompts or linking files there
    failed = svc.get(learner, essay_id)
    assert failed["status"] == "failed" and failed["failure_vi"]


def test_the_daily_budget(setup: Setup) -> None:
    from uuid import UUID

    _, learner, db = setup
    budget = Budget(cost_cap_usd=0.05, calls_per_learner=2)
    with psycopg.connect(db) as conn:
        assert spent_today(conn, UUID(learner), now=NOW).allows(budget)
        for cost in (0.01, 0.02):
            conn.execute(
                "insert into llm_calls(tier,model,latency_ms,cost_usd,success,learner_id,"
                "created_at) values ('free','m',10,%s,true,%s,%s)",
                (cost, learner, NOW),
            )
        conn.execute(
            "insert into llm_calls(tier,model,latency_ms,cost_usd,success,created_at) "
            "values ('free','m',10,0.01,true,%s)",
            (NOW - timedelta(days=1),),  # yesterday: not counted
        )
        spent = spent_today(conn, UUID(learner), now=NOW)
    assert spent.learner_calls == 2 and round(spent.cost_usd, 2) == 0.03
    assert not spent.allows(budget)  # this learner's calls are used up
    assert spent.allows(Budget(cost_cap_usd=0.05, calls_per_learner=5))
    assert not spent.allows(Budget(cost_cap_usd=0.03, calls_per_learner=5))  # the service cap


def test_routes(setup: Setup) -> None:
    svc, learner, db = setup
    app = FastAPI()
    app.include_router(writing_routes.create_router(svc))
    with TestClient(app) as client:
        prompts = client.get("/writing/prompts", params={"learner_id": learner})
        assert prompts.status_code == 200 and prompts.json()[0]["status"] == "draft"
        body = {
            "learner_id": learner,
            "prompt_id": "t2-plastic-ban",
            "text": ESSAY,
            "consent": CONSENT,
        }
        r = client.post("/essays", json=body)
        assert r.status_code == 202 and r.json()["status"] == "queued"
        essay_id = r.json()["essay_id"]
        drain(db, WRITING)
        got = client.get(f"/essays/{essay_id}", params={"learner_id": learner})
        assert got.status_code == 200 and got.json()["result"]["words"] == 10
        assert client.get("/essays", params={"learner_id": learner}).json()[0]["id"] == essay_id
        assert client.post("/essays", json={**body, "extra": 1}).status_code == 422
        gone = client.delete(f"/essays/{essay_id}", params={"learner_id": learner})
        assert gone.status_code == 204
        assert client.get(f"/essays/{essay_id}", params={"learner_id": learner}).status_code == 404
