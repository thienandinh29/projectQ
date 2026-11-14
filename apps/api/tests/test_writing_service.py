"""Essays through the API and the worker (specs/writing/step-2.1.md)."""

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from app.api import writing as writing_routes
from app.services.budget import Budget, spent_today
from app.services.writing import (
    CONSENT,
    GrammarStep,
    WritingService,
    load_grammar_step,
    process_next_essay,
)
from app.writing.languagetool import LanguageToolClient, Match, parse_matches

WRITING = Path(__file__).resolve().parents[3] / "data" / "writing"
NOW = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)
ESSAY = "Cities are crowded. However, buses help.\n\nIn conclusion, plan better."
Setup = tuple[WritingService, str, str]


def drain(db: str, writing_dir: Path, step: "GrammarStep | None" = None) -> int:
    """Process every queued essay: the test database is shared, so older essays may be waiting."""
    n = 0
    while process_next_essay(db, writing_dir, step):
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


# --- step 2.2: grammar check and evidence (specs/writing/step-2.2.md) --------------------------

FIXTURES = json.loads(
    (Path(__file__).parent / "writing" / "fixtures" / "lt-6.8.json").read_text("utf-8")
)
COURSES = Path(__file__).resolve().parents[3] / "data" / "courses"


class RecordedLanguageTool(LanguageToolClient):
    """Answers with LanguageTool 6.8's recorded responses; `down` simulates an outage."""

    def __init__(self, down: bool = False) -> None:
        super().__init__("http://languagetool.invalid")
        self.down = down

    def check(self, text: str, language: str) -> list[Match]:
        if self.down:
            raise httpx.ConnectError("down")
        recorded = next(f for f in FIXTURES.values() if f["text"] == text)
        return parse_matches(recorded[language])


@cache
def grammar_step(draft_learners: str) -> GrammarStep:
    return load_grammar_step(WRITING, COURSES, "", draft_learners)


def step_for(learner: str, *, draft: bool = True, down: bool = False) -> GrammarStep:
    step = replace(grammar_step(learner if draft else ""), client=RecordedLanguageTool(down))
    return step


def p_known(db: str, learner: str) -> dict[str, float]:
    with psycopg.connect(db) as conn:
        rows = conn.execute(
            "select c.slug, m.p_known from mastery m join concepts c on c.id=m.concept_id "
            "where m.learner_id=%s",
            (learner,),
        ).fetchall()
    return {r[0]: float(r[1]) for r in rows}


def own_essay(
    svc: WritingService, learner: str, db: str, step: GrammarStep, text: str
) -> dict[str, Any]:
    essay_id = svc.submit(learner, "t2-plastic-ban", text, CONSENT, now=NOW)
    drain(db, WRITING, step)
    return svc.get(learner, essay_id)


def test_mapped_errors_move_mastery_for_a_draft_learner_once(setup: Setup) -> None:
    svc, learner, db = setup
    step = step_for(learner)
    essay = own_essay(svc, learner, db, step, FIXTURES["sample"]["text"])
    r = essay["result"]
    assert essay["status"] == "done" and r["version"] == 2 and r["grammar_unavailable_vi"] is None
    issues = r["grammar"]["issues"]
    assert len(issues) == 8 and r["complexity"]["sentences"] == 8
    first = issues[0]
    assert first["sentence"][first["start"] - first["sentence_start"] :].startswith("go")
    assert first["node_vi"] == "Thì hiện tại đơn"
    moved = r["evidence"]
    # plural-nouns has two errors, so it comes first; at most 3, one per node
    assert [e["node"] for e in moved] == ["plural-nouns", "present-simple", "be-present"]
    assert all(e["p_before"] == 0.2 and e["p_after"] < 0.2 for e in moved)
    assert sorted(i["id"] for i in issues if i["evidence"]) == sorted(e["issue_id"] for e in moved)
    assert p_known(db, learner) == pytest.approx({e["node"]: e["p_after"] for e in moved}, abs=1e-4)
    with psycopg.connect(db) as conn:
        traces = conn.execute(
            "select kind, evidence->>'item_id', rule_vi from decision_traces "
            "where learner_id=%s and rule='writing.error'",
            (learner,),
        ).fetchall()
    assert len(traces) == 3 and all(t[0] == "bkt_update" for t in traces)
    assert all(t[1].startswith(f"essay:{essay['id']}:") for t in traces)
    assert all("She go" not in t[2] for t in traces)  # traces never hold the essay's text
    assert process_next_essay(db, WRITING, step) is False  # nothing is counted twice


def test_errors_are_shown_but_move_nothing_while_the_map_is_draft(setup: Setup) -> None:
    svc, learner, db = setup
    essay = own_essay(svc, learner, db, step_for(learner, draft=False), FIXTURES["sample"]["text"])
    assert len(essay["result"]["grammar"]["issues"]) == 8
    assert essay["result"]["evidence"] == [] and p_known(db, learner) == {}
    assert not any(i["evidence"] for i in essay["result"]["grammar"]["issues"])


def test_a_reviewed_map_moves_mastery_for_everyone(setup: Setup) -> None:
    svc, learner, db = setup
    base = step_for(learner, draft=False)
    reviewed = replace(base, error_map=base.error_map.model_copy(update={"status": "reviewed"}))
    essay = own_essay(svc, learner, db, reviewed, FIXTURES["smoke"]["text"])
    assert [e["node"] for e in essay["result"]["evidence"]] == ["present-simple"]


def test_without_languagetool_the_page_says_grammar_was_not_checked(setup: Setup) -> None:
    svc, learner, db = setup
    off = replace(step_for(learner), client=None)
    r = own_essay(svc, learner, db, off, FIXTURES["smoke"]["text"])["result"]
    assert r["grammar"] is None and "LANGUAGETOOL_URL" in r["grammar_unavailable_vi"]
    assert r["words"] == 6 and r["complexity"]["sentences"] == 1
    down = own_essay(svc, learner, db, step_for(learner, down=True), FIXTURES["clean"]["text"])
    assert down["status"] == "done" and down["result"]["grammar"] is None
    assert "không phản hồi" in down["result"]["grammar_unavailable_vi"]
    assert p_known(db, learner) == {}
