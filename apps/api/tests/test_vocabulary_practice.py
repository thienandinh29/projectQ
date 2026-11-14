"""Vocabulary practice with the database (specs/vocabulary): cards, sessions, limits, routes."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from app.api import vocab as vocab_routes
from app.config import Settings
from app.main import create_app
from app.services.vocabulary import VocabPractice, start_of_day
from app.vocabulary.items import build_item, item_id, parse_item_id, pick
from app.vocabulary.wordlist import load_wordlist

LISTS = Path(__file__).resolve().parents[3] / "data" / "vocabulary"
WL = load_wordlist(LISTS / "core-seed.yaml")
NOW = datetime(2026, 11, 20, 3, 0, tzinfo=UTC)  # 10:00 in Vietnam
Setup = tuple[VocabPractice, str, str]


@pytest.fixture
def setup(database_url: str) -> Iterator[Setup]:
    pool = ConnectionPool(database_url, open=True)
    practice = VocabPractice(lambda: pool, LISTS)
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "insert into learners(display_name) values ('Vocab') returning id"
        ).fetchone()
        assert row
    yield practice, str(row[0]), database_url
    pool.close()


def answer_correctly(practice: VocabPractice, learner: str, iid: str, now: datetime) -> None:
    _, key, kind, n = parse_item_id(iid)
    word = WL.get(key)
    assert word is not None
    item = build_item(WL, word, kind, n)
    assert practice.answer(learner, iid, item.accepted[0], now=now).correct


def test_a_new_learner_gets_new_words_taught_before_they_are_asked(setup: Setup) -> None:
    practice, learner, _ = setup
    s = practice.session(learner, "core-seed", now=NOW)
    assert len(s.entries) == 10 and s.due == 0 and s.new_left_today == 10
    first = s.entries[0]
    assert first.is_new and first.card is not None and first.item.kind == "meaning"
    assert first.card.definition and first.card.example  # taught first
    again = practice.session(learner, "core-seed", now=NOW)
    assert [e.item.id for e in s.entries] == [e.item.id for e in again.entries]  # deterministic
    assert next(e.card.lemma for e in s.entries if e.card) == WL.words[0].lemma  # list order


def test_a_right_answer_schedules_the_word_later_and_a_wrong_one_counts_a_lapse(
    setup: Setup,
) -> None:
    practice, learner, db = setup
    s = practice.session(learner, "core-seed", now=NOW)
    first_card = s.entries[0].card
    assert first_card is not None
    answer_correctly(practice, learner, s.entries[0].item.id, NOW)
    bad = practice.answer(learner, s.entries[1].item.id, "definitely-not-it", now=NOW)
    assert not bad.correct and bad.accepted and bad.card.definition
    assert bad.due_at > NOW  # even a wrong answer is scheduled (in days: no learning steps)
    with psycopg.connect(db) as conn:
        cards = conn.execute(
            "select reviews, lapses, due_at from vocab_cards where learner_id=%s", (learner,)
        ).fetchall()
        log = conn.execute(
            "select item_kind, correct, answer from vocab_reviews where learner_id=%s order by id",
            (learner,),
        ).fetchall()
        traces = conn.execute(
            "select kind from decision_traces where learner_id=%s", (learner,)
        ).fetchall()
    assert sorted((c[0], c[1]) for c in cards) == [(1, 0), (1, 1)]  # one lapse, the wrong answer
    assert all(c[2] > NOW for c in cards)
    assert log == [("meaning", True, first_card.lemma), ("meaning", False, "definitely-not-it")]
    assert traces == [("review",), ("review",)]
    assert bad.trace.kind == "review" and "ôn" in bad.trace.rule_vi.lower()


def test_answered_words_leave_the_session_until_due_then_come_first(setup: Setup) -> None:
    practice, learner, _ = setup
    s = practice.session(learner, "core-seed", new_limit=3, now=NOW)
    for e in s.entries:
        answer_correctly(practice, learner, e.item.id, NOW)
    same_day = practice.session(learner, "core-seed", new_limit=3, now=NOW + timedelta(hours=1))
    assert same_day.due == 0 and same_day.entries == [] and same_day.new_left_today == 0
    later = practice.session(learner, "core-seed", new_limit=3, now=NOW + timedelta(days=30))
    assert later.due == 3
    assert [e.is_new for e in later.entries][:3] == [False, False, False]  # due words come first
    assert all(e.card is None for e in later.entries if not e.is_new)  # a review never shows it
    kinds = {e.item.kind for e in later.entries if not e.is_new}
    assert kinds == {"gapfill"}  # the second time a word is asked, the kind has rotated on


def test_the_daily_new_word_limit_resets_at_midnight_in_vietnam(setup: Setup) -> None:
    practice, learner, _ = setup
    for e in practice.session(learner, "core-seed", new_limit=4, now=NOW).entries:
        answer_correctly(practice, learner, e.item.id, NOW)
    today = practice.session(learner, "core-seed", new_limit=4, now=NOW + timedelta(hours=2))
    assert today.new_today == 4 and today.new_left_today == 0
    assert not [e for e in today.entries if e.is_new]
    assert start_of_day(NOW) == datetime(2026, 11, 19, 17, 0, tzinfo=UTC)  # 00:00 at UTC+7
    tomorrow = practice.session(learner, "core-seed", new_limit=4, now=NOW + timedelta(hours=15))
    assert tomorrow.new_today == 0 and len([e for e in tomorrow.entries if e.is_new]) == 4


def test_max_level_and_limit_cap_the_new_words(setup: Setup) -> None:
    practice, learner, _ = setup
    a2 = practice.session(learner, "core-seed", max_level="A2", now=NOW)
    assert {e.card.level for e in a2.entries if e.card} == {"A2"} and len(a2.entries) == 3
    assert len(practice.session(learner, "core-seed", limit=2, now=NOW).entries) == 2


def test_a_card_for_a_word_no_longer_in_the_list_is_skipped(setup: Setup) -> None:
    practice, learner, db = setup
    with psycopg.connect(db) as conn:
        conn.execute(
            "insert into vocab_cards(learner_id,list_slug,word_key,fsrs_state,due_at) "
            "values (%s,'core-seed','ghost:noun','{}'::jsonb,%s)",
            (learner, NOW - timedelta(days=1)),
        )
    s = practice.session(learner, "core-seed", now=NOW)
    assert s.due == 1 and all(e.item.id.split("|")[1] != "ghost:noun" for e in s.entries)


def test_unknown_things_are_404_and_bad_input_is_422(setup: Setup) -> None:
    practice, learner, _ = setup
    ghost = "00000000-0000-0000-0000-000000000000"
    good = item_id("core-seed", "decision:noun", "gapfill", 0)
    no_word = item_id("core-seed", "nothing:noun", "gapfill", 0)
    no_item = item_id("core-seed", "decision:noun", "gapfill", 9)
    cases: list[tuple[Callable[[], object], int]] = [
        (lambda: practice.session(ghost, "core-seed"), 404),
        (lambda: practice.session(learner, "nope"), 404),
        (lambda: practice.session(learner, "../etc"), 404),
        (lambda: practice.answer(ghost, good, "decision"), 404),
        (lambda: practice.answer(learner, no_word, "x"), 404),
        (lambda: practice.answer(learner, no_item, "x"), 404),
        (lambda: practice.answer(learner, "garbage", "x"), 422),
        (lambda: practice.answer(learner, good, "x" * 101), 422),
    ]
    for call, code in cases:
        with pytest.raises(HTTPException) as err:
            call()
        assert err.value.status_code == code


def test_routes_end_to_end_without_leaking_the_key(setup: Setup) -> None:
    practice, learner, _ = setup
    app = FastAPI()
    app.include_router(vocab_routes.create_router(practice))
    with TestClient(app) as client:
        r = client.get("/vocab/session", params={"learner_id": learner, "new_limit": 2})
        assert r.status_code == 200, r.text
        first = r.json()["entries"][0]
        assert first["is_new"] and first["card"]["lemma"] == WL.words[0].lemma
        assert "accepted" not in r.text and "word_key" not in r.text
        item = first["item"]
        assert item["kind"] == "meaning" and len(item["options"]) == 4
        wrong = next(o for o in item["options"] if o != first["card"]["lemma"])

        def post(iid: str, answer: str, **extra: object) -> httpx.Response:
            body = {"learner_id": learner, "item_id": iid, "answer": answer, **extra}
            response: httpx.Response = client.post("/vocab/answers", json=body)
            return response

        bad = post(item["id"], wrong)
        assert bad.status_code == 200 and bad.json()["correct"] is False
        assert bad.json()["accepted"] == first["card"]["lemma"]
        assert bad.json()["trace"]["kind"] == "review"
        assert post(item["id"], first["card"]["lemma"]).json()["correct"] is True
        assert post("x|y|z|0", "a").status_code == 422
        assert post(item["id"], "a", extra=1).status_code == 422
        too_high = client.get("/vocab/session", params={"learner_id": learner, "max_level": "Z9"})
        assert too_high.status_code == 422
        missing = client.get("/vocab/session", params={"learner_id": learner, "list": "no-such"})
        assert missing.status_code == 404


def test_the_routes_are_mounted_in_the_app(database_url: str) -> None:
    settings = Settings(
        database_url=database_url,
        allow_unauthenticated_local_dev=True,
        _env_file=None,
    )
    app = create_app(settings)
    assert {"/vocab/session", "/vocab/answers"} <= set(app.openapi()["paths"])


def test_pick_matches_what_a_session_asks(setup: Setup) -> None:
    practice, learner, _ = setup
    e = practice.session(learner, "core-seed", new_limit=1, now=NOW).entries[0]
    word = WL.words[0]
    kind, n = pick(word, 0)
    assert e.item.id == item_id("core-seed", word.key, kind, n)
