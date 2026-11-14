"""Essays through the API and the worker (specs/writing/step-2.1.md)."""

import json
from collections.abc import Callable, Iterator
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
    svc: WritingService,
    learner: str,
    db: str,
    step: GrammarStep,
    text: str,
    now: datetime = NOW,
) -> dict[str, Any]:
    essay_id = svc.submit(learner, "t2-plastic-ban", text, CONSENT, now=now)
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


# --- step 2.4a: model feedback, budgeted and checked (specs/writing/step-2.4.md) --------------


class FakeDeepSeek:
    """Scripted replies by task; counts calls. The first feedback reply is invalid JSON."""

    def __init__(self, *, feedback_bands: float = 6.0, invalid_first: bool = False) -> None:
        self.calls: list[str] = []
        self.bands = feedback_bands
        self.invalid_first = invalid_first

    async def generate(self, route: Any, system: str, messages: Any, schema: Any) -> Any:
        from app.llm.gateway import ProviderReply

        task = "correct" if "minimal" in system or "few words" in system else "feedback"
        self.calls.append(task)
        body: dict[str, Any]
        if task == "correct":
            body = {"fixes": [{"index": 0, "corrected": None}]}
        else:
            if self.invalid_first and self.calls.count("feedback") == 1:
                return ProviderReply("not json", 100, 10)
            p = {"kind": "issue", "point_vi": "Câu này cần chia động từ theo chủ ngữ.",
                 "quotes": ["She go to school", "words that are not there"]}  # fmt: skip
            body = {c: {"band": self.bands, "points": [p]} for c in ("tr", "cc", "lr", "gra")}
        return ProviderReply(json.dumps(body), 1000, 200)


def writing_model(db: str, fake: FakeDeepSeek, cap: float = 1.0, calls: int = 30) -> Any:
    from app.llm.gateway import Gateway, Route, Routing
    from app.services.budget import Budget
    from app.writing.model_calls import Prices, WritingModel

    route = Route(provider="deepseek", model="deepseek-test", family="deepseek")
    routing = Routing(tiers={"free": {"writing_feedback": [route], "writing_correct": [route]}})
    return WritingModel(Gateway(routing, {"deepseek": fake}), db, Budget(cap, calls),
                        Prices(1.0, 4.0), clock=lambda: NOW)  # fmt: skip


def test_feedback_for_a_draft_learner_is_checked_recorded_and_never_shows_the_model_band(
    setup: Setup,
) -> None:
    svc, learner, db = setup
    fake = FakeDeepSeek(invalid_first=True)
    step = replace(step_for(learner), model=writing_model(db, fake))
    essay = own_essay(svc, learner, db, step, FIXTURES["smoke"]["text"])
    r = essay["result"]
    fb = r["feedback"]
    assert r["feedback_unavailable_vi"] is None and fb["model"] == "deepseek-test"
    assert all(p["quotes"] == ["She go to school"] for ps in fb["criteria"].values() for p in ps)
    assert (fb["quotes_checked"], fb["quotes_kept"], fb["dropped"]) == (8, 4, 0)
    assert "_llm_bands" not in r and "band" not in json.dumps(fb)  # stored, never sent
    assert r.get("llm_corrections") in (None, {"kept": 0, "discarded": 0})
    with psycopg.connect(db) as conn:
        rows = conn.execute(
            "select task, success, input_tokens, output_tokens, cost_usd::float from llm_calls "
            "where learner_id=%s order by created_at, success",
            (learner,),
        ).fetchall()
        stored = conn.execute("select result->'_llm_bands' from essays where id=%s",
                              (essay["id"],)).fetchone()  # fmt: skip
    # the invalid reply was paid for too: recorded as a failed attempt
    assert [(t, ok) for t, ok, *_ in rows].count(("writing_feedback", False)) == 1
    # cost = tokens x the configured prices (US$1 and US$4 per million)
    assert all(c == pytest.approx((i * 1 + o * 4) / 1e6) for *_, i, o, c in rows)
    assert {(i, o) for _, ok, i, o, _ in rows if ok} == {(1000, 200)}
    assert stored and stored[0]["overall"] == 6.0


def test_feedback_is_hidden_from_other_learners_and_stops_at_the_budget(setup: Setup) -> None:
    svc, learner, db = setup
    fake = FakeDeepSeek()
    hidden = replace(step_for(learner, draft=False), model=writing_model(db, fake))
    r = own_essay(svc, learner, db, hidden, FIXTURES["smoke"]["text"])["result"]
    assert r["feedback"] is None and "chưa mở" in r["feedback_unavailable_vi"] and not fake.calls
    broke = replace(step_for(learner), model=writing_model(db, fake, calls=0))
    r = own_essay(svc, learner, db, broke, FIXTURES["smoke"]["text"])["result"]
    assert r["feedback"] is None and "hết lượt" in r["feedback_unavailable_vi"]
    assert not fake.calls  # the budget is checked before any call
    off = replace(step_for(learner), model=None)
    tomorrow = NOW + timedelta(days=1)  # the fixture allows 2 essays a day
    r = own_essay(svc, learner, db, off, FIXTURES["smoke"]["text"], now=tomorrow)["result"]
    assert "DEEPSEEK_API_KEY" in r["feedback_unavailable_vi"]


def test_a_model_far_from_the_scorer_makes_the_band_uncertain(setup: Setup) -> None:
    from tests.writing.test_band import CALIBRATED, FakeScorer

    svc, learner, db = setup
    long_text = (FIXTURES["clean"]["text"] + " ") * 12  # over 150 words, so a band is computed
    step = replace(
        step_for(learner),
        model=writing_model(db, FakeDeepSeek(feedback_bands=8.5)),
        scorer=FakeScorer(4.0),
        scorer_config=CALIBRATED,
        client=None,
    )  # fmt: skip  (no LanguageTool: this text is not recorded)
    r = own_essay(svc, learner, db, step, long_text)["result"]
    # the scorer says 5.5-7.0 (middle 6.25); the model's overall is 8.5: more than a band apart
    assert r["score"]["uncertain"] and "khác nhau hơn 1 band" in r["score"]["uncertain_reason"]


# --- step 2.4a: hint first, then the answer (no model call) ---------------------------------


class SentenceChecker(LanguageToolClient):
    """Flags a sentence that still contains the error ("go to"); everything else is clean."""

    def __init__(self) -> None:
        super().__init__("http://languagetool.invalid")

    def matches(self, text: str) -> list[Match]:
        at = text.find(" go to ")
        return [] if at < 0 else [Match(at + 1, 2, "HE_VERB_AGR", "GRAMMAR", "m", ("goes",))]


def corrector(svc: WritingService, lt: LanguageToolClient | None = None) -> WritingService:
    return WritingService(svc.pool, WRITING, draft_learners=",".join(map(str, svc.draft_learners)),
                          daily_essays=5, languagetool=lt or SentenceChecker(),
                          courses_dir=COURSES)  # fmt: skip


def counted_issue(svc: WritingService, learner: str, db: str, now: datetime) -> tuple[str, int]:
    essay = own_essay(svc, learner, db, step_for(learner), FIXTURES["smoke"]["text"], now=now)
    issue = next(i for i in essay["result"]["grammar"]["issues"] if i["evidence"])
    return essay["id"], issue["id"]


def test_two_wrong_tries_show_the_answer_and_move_nothing(setup: Setup) -> None:
    svc, learner, db = setup
    essay_id, issue = counted_issue(svc, learner, db, NOW)
    fixer = corrector(svc)
    before = p_known(db, learner)
    first = fixer.correct(learner, essay_id, issue, "She go to school every day!", now=NOW)
    assert first["accepted"] is False and first["tries"] == 1 and first["answer"] is None
    assert first["feedback_vi"] == "Câu vẫn còn lỗi ngữ pháp hoặc chính tả. Thử lại nhé."
    # "went" and no "to": LanguageTool is satisfied, but it is further from the correction
    second = fixer.correct(learner, essay_id, issue, "She went school every day.", now=NOW)
    assert second["tries"] == 2 and second["answer"] == "She goes to school every day."
    assert p_known(db, learner) == before
    with pytest.raises(HTTPException) as err:
        fixer.correct(learner, essay_id, issue, "She goes to school every day.", now=NOW)
    assert err.value.status_code == 409
    state = svc.get(learner, essay_id)["corrections"][str(issue)]
    assert state == {"tries": 2, "accepted": False, "answer_shown": True}


def test_a_correct_fix_after_the_hint_is_aided_evidence(setup: Setup) -> None:
    from app.engine import bkt

    svc, learner, db = setup
    essay_id, issue = counted_issue(svc, learner, db, NOW)
    p = p_known(db, learner)["present-simple"]  # after the essay's error
    out = corrector(svc).correct(learner, essay_id, issue, "She goes to school every day.",
                                 now=NOW)  # fmt: skip
    assert out["accepted"] and out["tries"] == 1 and out["answer"]
    params = bkt.params_with_help(load_grammar_step(WRITING, COURSES, "").error_map.params(), 1)
    assert p_known(db, learner)["present-simple"] == pytest.approx(bkt.update(p, True, params))
    with psycopg.connect(db) as conn:
        rule = conn.execute(
            "select rule_vi from decision_traces where learner_id=%s and "
            "rule='writing.self_correction'", (learner,)).fetchone()  # fmt: skip
    assert rule and "gợi ý" in rule[0]


def test_showing_the_answer_and_what_cannot_be_corrected(setup: Setup) -> None:
    svc, learner, db = setup
    essay_id, issue = counted_issue(svc, learner, db, NOW)
    fixer = corrector(svc)
    shown = fixer.correct(learner, essay_id, issue, None, show_answer=True, now=NOW)
    assert shown["answer"] == "She goes to school every day." and shown["tries"] == 0
    cases: list[tuple[Callable[[], object], int]] = [
        (lambda: fixer.correct(learner, essay_id, 99, "x", now=NOW), 404),
        (lambda: fixer.correct(learner, essay_id, issue, "x", now=NOW), 409),
        (lambda: fixer.correct(learner, "nope", issue, "x", now=NOW), 404),
    ]
    other_id, other_issue = counted_issue(svc, learner, db, NOW + timedelta(days=1))
    no_lt = WritingService(svc.pool, WRITING, courses_dir=COURSES)
    cases += [
        (lambda: no_lt.correct(learner, other_id, other_issue, "She goes.", now=NOW), 503),
        (lambda: fixer.correct(learner, other_id, other_issue, "  ", now=NOW), 422),
    ]
    for call, code in cases:
        with pytest.raises(HTTPException) as err:
            call()
        assert err.value.status_code == code
