"""The grammar roadmap with the database (specs/level-test).

Level test, roadmap, milestone tests, quick checks and practice.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from app.api import grammar as grammar_routes
from app.config import Settings
from app.engine.milestones import ASSUMED_KNOWN
from app.main import create_app
from app.services.grammar import GrammarService, Step
from app.services.vocabulary import VocabPractice
from app.vocabulary.items import parse_item_id

ROOT = Path(__file__).resolve().parents[3] / "data"
Setup = tuple[GrammarService, str, str]


def make(pool: ConnectionPool, drafts: str) -> GrammarService:
    return GrammarService(
        lambda: pool, ROOT / "courses", ROOT / "items", ROOT / "vocabulary", drafts
    )


@pytest.fixture
def setup(database_url: str) -> Iterator[Setup]:
    pool = ConnectionPool(database_url, open=True)
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "insert into learners(display_name) values ('G') returning id"
        ).fetchone()
        assert row
    learner = str(row[0])
    yield make(pool, learner), learner, database_url  # this learner may see draft items
    pool.close()


def key(svc: GrammarService, item_id: str) -> str:
    if "|" in item_id:  # a vocabulary item in the level test
        from app.services.grammar import _vocab_item

        return _vocab_item(svc.wordlist(), item_id).accepted[0]
    item = svc.bundle("english-ielts").bank.get(item_id)
    assert item is not None
    return item.key


def wrong(svc: GrammarService, step: Step) -> str:
    assert step.question
    return next(o for o in step.question.options if o != key(svc, step.question.item_id))


def answer_all(svc: GrammarService, learner: str, step: Step, choose: Callable[[Step], str],
               answer: Callable[..., Step]) -> Step:  # fmt: skip
    while step.question is not None:
        assert step.run_id
        step = answer(learner, step.run_id, step.question.item_id, choose(step))
    return step


def test_without_permission_draft_items_are_never_served(setup: Setup, database_url: str) -> None:
    svc, learner, _ = setup
    pool = ConnectionPool(database_url, open=True)
    other = make(pool, "")
    calls: list[Callable[[], object]] = [
        lambda: other.start_level_test(learner, "english-ielts", None),
        lambda: other.start_run(learner, "english-ielts", "milestone", "passive"),
    ]
    for call in calls:
        with pytest.raises(HTTPException) as err:
            call()
        assert err.value.status_code == 409
    pool.close()
    step = svc.start_level_test(learner, "english-ielts", None)
    assert step.question and step.question.draft  # the owner sees drafts, labelled


def test_a_learner_who_knows_everything_is_placed_at_c1_and_seeded(setup: Setup) -> None:
    svc, learner, db = setup
    step = svc.start_level_test(learner, "english-ielts", None)
    done = answer_all(svc, learner, step, lambda s: key(svc, s.question.item_id),  # type: ignore[union-attr]
                      svc.answer_level_test)  # fmt: skip
    result = done.finished
    assert result is not None
    assert result["grammar_level"] == "C1" and result["vocab_level"] == "C1"
    assert "7.0–8.0" in result["ielts_vi"] and "ước lượng" in result["ielts_vi"]  # noqa: RUF001
    assert result["questions"] <= 20 + 12
    road = svc.roadmap(learner, "english-ielts")
    assert {m["status"] for m in road["milestones"]} == {"known"}
    assert all(h["p_known"] >= ASSUMED_KNOWN for m in road["milestones"] for h in m["hidden"])
    assert road["next_milestone"] is None and road["level_test"]["grammar_level"] == "C1"
    pool = ConnectionPool(db, open=True)
    vocab = VocabPractice(lambda: pool, ROOT / "vocabulary").session(learner, "core-seed")
    pool.close()
    assert vocab.entries  # max_level comes from the level test (C1: everything)


def test_a_beginner_is_placed_below_a2_with_nothing_seeded(setup: Setup) -> None:
    svc, learner, db = setup
    step = svc.start_level_test(learner, "english-ielts", "B2")
    done = answer_all(svc, learner, step, lambda s: wrong(svc, s), svc.answer_level_test)
    assert done.finished is not None
    assert done.finished["grammar_level"] == "A1" and done.finished["vocab_level"] == "A1"
    assert "dưới 4.0" in done.finished["ielts_vi"]
    road = svc.roadmap(learner, "english-ielts")
    assert {m["status"] for m in road["milestones"]} == {"unknown"}
    assert road["next_milestone"] is not None
    assert (
        road["milestones"][[m["slug"] for m in road["milestones"]].index(road["next_milestone"])][
            "needs"
        ]
        == []
    )
    pool = ConnectionPool(db, open=True)
    vocab = VocabPractice(lambda: pool, ROOT / "vocabulary").session(learner, "core-seed")
    pool.close()
    assert {e.card.level for e in vocab.entries if e.card} == {"A2"}  # one level above A1


def test_passing_a_milestone_test_marks_its_parts_known(setup: Setup) -> None:
    svc, learner, _ = setup
    step = svc.start_run(learner, "english-ielts", "milestone", "present-tenses")
    assert step.question and step.question.total == 3  # three hidden nodes: three questions
    done = answer_all(svc, learner, step, lambda s: key(svc, s.question.item_id),  # type: ignore[union-attr]
                      svc.answer_run)  # fmt: skip
    assert done.finished == {"result": "pass", "opened": []}
    assert any(t.rule == "milestone.pass" for t in done.traces)
    status = {m["slug"]: m["status"] for m in svc.roadmap(learner, "english-ielts")["milestones"]}
    assert status["present-tenses"] == "known"


def test_failing_a_milestone_opens_quick_checks_then_names_what_to_learn(setup: Setup) -> None:
    svc, learner, db = setup
    step = svc.start_run(learner, "english-ielts", "milestone", "conditional-3")
    step = answer_all(
        svc, learner, step, lambda s: wrong(svc, s), svc.answer_run
    )  # until the checks start
    # the last answer of the milestone test returns the outcome and the first quick check together
    assert step.kind in ("checks", "milestone")
    with psycopg.connect(db) as conn:
        runs = conn.execute(
            "select kind, outcome from grammar_runs where learner_id=%s order by started_at",
            (learner,),
        ).fetchall()
        logged = conn.execute(
            "select count(*) from grammar_answers "
            "where learner_id=%s and misconception is not null",
            (learner,),
        ).fetchone()
    assert runs[0][0] == "milestone" and runs[0][1]["result"] == "fail"
    assert logged and logged[0] >= 3  # every wrong answer logged its misconception


def test_checks_end_with_the_most_foundational_weak_part(setup: Setup) -> None:
    svc, learner, _ = setup
    step = svc.start_run(learner, "english-ielts", "milestone", "conditional-3")
    while step.kind == "milestone" and step.question is not None:
        assert step.run_id and step.question
        step = svc.answer_run(learner, step.run_id, step.question.item_id, wrong(svc, step))
    assert step.kind == "checks" and step.finished and step.finished["result"] == "fail"
    done = answer_all(svc, learner, step, lambda s: wrong(svc, s), svc.answer_run)
    assert done.finished is not None and done.finished["learn_next"] == "third-conditional"
    assert any(t.kind == "root_cause" for t in done.traces)
    # with evidence that past perfect is weak, the root cause moves to it
    weak = svc.start_run(learner, "english-ielts", "practice", "past-perfect")
    answer_all(svc, learner, weak, lambda s: wrong(svc, s), svc.answer_run)
    again = svc.start_run(learner, "english-ielts", "milestone", "conditional-3")
    while again.kind == "milestone" and again.question is not None:
        assert again.run_id and again.question
        again = svc.answer_run(learner, again.run_id, again.question.item_id, wrong(svc, again))
    final = answer_all(svc, learner, again, lambda s: wrong(svc, s), svc.answer_run)
    assert final.finished is not None and final.finished["learn_next"] == "past-perfect"
    road = svc.roadmap(learner, "english-ielts")
    assert road["learn_next"] is None  # nothing is "partial" yet: nothing was known before


def test_one_slip_in_four_passes_with_a_gap(setup: Setup) -> None:
    svc, learner, _ = setup
    step = svc.start_run(learner, "english-ielts", "milestone", "nouns-articles")
    assert step.question and step.question.total == 3  # 3 hidden nodes
    step = svc.start_run(learner, "english-ielts", "milestone", "past-and-future")
    assert step.question and step.question.total == 3  # 2 hidden nodes: still 3 questions


def test_practice_updates_mastery_and_reports_it(setup: Setup) -> None:
    svc, learner, _ = setup
    step = svc.start_run(learner, "english-ielts", "practice", "past-perfect")
    assert step.question and step.question.total == 3
    done = answer_all(svc, learner, step, lambda s: key(svc, s.question.item_id),  # type: ignore[union-attr]
                      svc.answer_run)  # fmt: skip
    assert done.finished and done.finished["node"] == "past-perfect"
    # three right answers from the prior give 0.948: not yet mastery (0.95 and 2 unaided wins)
    assert 0.9 < done.finished["p_known"] < 0.95 and done.finished["mastered"] is False
    assert [t.kind for t in done.traces] == ["bkt_update"]


def test_answers_out_of_turn_or_from_someone_else_are_refused(
    setup: Setup, database_url: str
) -> None:
    svc, learner, _ = setup
    step = svc.start_run(learner, "english-ielts", "practice", "past-perfect")
    assert step.run_id and step.question
    with pytest.raises(HTTPException) as err:
        svc.answer_run(learner, step.run_id, "be-present-1", "is")
    assert err.value.status_code == 409
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "insert into learners(display_name) values ('X') returning id"
        ).fetchone()
        assert row
    with pytest.raises(HTTPException) as err:
        svc.answer_run(str(row[0]), step.run_id, step.question.item_id, "x")
    assert err.value.status_code == 404
    cases: list[tuple[Callable[[], object], int]] = [
        (lambda: svc.start_run(learner, "english-ielts", "milestone", "nope"), 404),
        (
            lambda: svc.start_run(learner, "english-ielts", "practice", "passive"),
            404,
        ),  # a milestone
        (lambda: svc.start_run(learner, "nope", "milestone", "passive"), 404),
        (lambda: svc.answer_run(learner, "not-a-uuid", "x", "y"), 404),
    ]
    for call, code in cases:
        with pytest.raises(HTTPException) as err:
            call()
        assert err.value.status_code == code


def test_routes_end_to_end(setup: Setup) -> None:
    svc, learner, _ = setup
    app = FastAPI()
    app.include_router(grammar_routes.create_router(svc))
    with TestClient(app) as client:
        r = client.post("/level-tests", json={"learner_id": learner, "target": "B1"})
        assert r.status_code == 200, r.text
        q = r.json()["question"]
        assert q["draft"] is True and len(q["options"]) == 4
        assert '"correct":true' not in r.text and 'misconception":"' not in r.text
        body = {"learner_id": learner, "item_id": q["item_id"], "answer": q["options"][0]}
        r2 = client.post(f"/level-tests/{r.json()['run_id']}/answers", json=body)
        assert r2.status_code == 200 and r2.json()["traces"]
        road = client.get("/roadmap", params={"learner_id": learner})
        assert road.status_code == 200 and len(road.json()["milestones"]) == 10
        m = client.post("/milestones/passive/tests", json={"learner_id": learner})
        assert m.status_code == 200 and m.json()["kind"] == "milestone"
        p = client.post("/nodes/past-perfect/practice", json={"learner_id": learner})
        assert p.status_code == 200
        bad = client.post("/level-tests", json={"learner_id": learner, "target": "Z9"})
        assert bad.status_code == 422


def test_the_routes_are_mounted_in_the_app(database_url: str) -> None:
    app = create_app(
        Settings(database_url=database_url, allow_unauthenticated_local_dev=True, _env_file=None)
    )
    paths = set(app.openapi()["paths"])
    assert {
        "/level-tests",
        "/roadmap",
        "/milestones/{slug}/tests",
        "/grammar-runs/{run_id}/answers",
    } <= paths


def test_level_test_vocabulary_items_are_meaning_questions() -> None:
    from app.vocabulary.items import item_id

    assert parse_item_id(item_id("core-seed", "important:adjective", "meaning", 0))[2] == "meaning"


def test_every_run_answer_says_right_or_wrong_and_explains_the_mistake_in_vietnamese(
    setup: Setup,
) -> None:
    svc, learner, _ = setup
    step = svc.start_run(learner, "english-ielts", "practice", "past-simple")
    assert step.question and step.run_id
    item_id = step.question.item_id
    bad = svc.answer_run(learner, step.run_id, item_id, wrong(svc, step))
    assert bad.feedback is not None and bad.feedback["correct"] is False
    assert bad.feedback["key"] == key(svc, item_id)
    assert bad.feedback["misconception"] and bad.feedback["misconception_vi"]
    assert bad.question is not None and bad.run_id
    good = svc.answer_run(learner, bad.run_id, bad.question.item_id, key(svc, bad.question.item_id))
    assert good.feedback == {"correct": True, "key": key(svc, bad.question.item_id),
                             "misconception": None, "misconception_vi": None}  # fmt: skip


def test_every_misconception_an_item_names_has_a_vietnamese_explanation() -> None:
    from app.services.grammar import load_misconceptions

    glossary = load_misconceptions(ROOT / "items" / "misconceptions.vi.yaml")
    from app.curriculum.course import load_course
    from app.curriculum.items import load_items

    items = load_items(
        ROOT / "items" / "english-ielts.yaml", load_course(ROOT / "courses" / "english-ielts.yaml")
    )
    named = {o.misconception for i in items.items for o in i.options if o.misconception}
    assert named <= set(glossary), sorted(named - set(glossary))
    assert all(len(text) > 10 for text in glossary.values())
