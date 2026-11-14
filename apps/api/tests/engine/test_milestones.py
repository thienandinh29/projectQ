"""Milestones, hidden nodes, the level estimate and the item bank (specs/level-test)."""

from pathlib import Path

import pytest

from app.curriculum.course import load_course
from app.curriculum.items import ItemBank, check_bank, items_per_milestone, load_items, round_robin
from app.curriculum.levels import ielts_range_vi
from app.curriculum.roadmap import build_roadmap
from app.engine.milestones import (
    ASSUMED_KNOWN,
    NodeAnswer,
    known_milestones,
    level_from,
    level_test_next,
    milestone_outcome,
    milestone_status,
    next_to_learn,
    questions_in_test,
    seed_from_level_test,
    vocab_level,
)
from app.engine.placement import Answer

DATA = Path(__file__).resolve().parents[4] / "data" / "courses"
COURSE = load_course(DATA / "english-ielts.yaml")
RM = build_roadmap(COURSE)
BANK = load_items(DATA.parent / "items" / "english-ielts.yaml", COURSE)


def known(*milestones: str) -> dict[str, float]:
    return {n: ASSUMED_KNOWN for m in milestones for n in RM.hidden[m]}


# --- the roadmap and the items -----------------------------------------------------------------


def test_the_roadmap_has_milestones_with_levels_and_ordered_hidden_nodes() -> None:
    assert len(RM.milestones) == 10 and set(RM.level.values()) == {"A2", "B1", "B2", "C1"}
    assert RM.hidden["present-tenses"] == ("be-present", "present-simple", "present-continuous")
    assert ("conditionals-1-2", "conditional-3") in COURSE.milestone_edges()


def test_every_hidden_node_has_four_items_and_every_wrong_option_says_why() -> None:
    assert not check_bank(BANK, COURSE)
    for node in RM.hidden_nodes:
        assert len(BANK.for_node(node, include_drafts=True)) == 4, node
        assert BANK.for_node(node, include_drafts=False) == []  # all draft until reviewed
    for item in BANK.items:
        assert all(o.misconception for o in item.options if not o.correct)
        assert item.shuffled() == item.shuffled()  # the same order every time


def test_a_bank_for_unknown_nodes_or_with_duplicates_is_refused() -> None:
    raw = BANK.model_dump()
    raw["items"] = [*raw["items"], {**raw["items"][0], "node": "present-tenses"}]
    problems = check_bank(ItemBank.model_validate(raw), COURSE)
    assert any("duplicate" in p for p in problems)
    assert any("not a hidden node" in p for p in problems)  # a milestone is not a hidden node


def test_items_per_milestone_counts_only_what_may_be_served() -> None:
    assert items_per_milestone(BANK, COURSE, include_drafts=True)["passive"] == 4
    assert set(items_per_milestone(BANK, COURSE, include_drafts=False).values()) == {0}


def test_a_test_spreads_its_questions_over_the_hidden_nodes() -> None:
    assert round_robin([["a1", "a2"], ["b1"], ["c1", "c2"]], 4) == ["a1", "b1", "c1", "a2"]
    assert round_robin([["a1", "a2", "a3", "a4"]], 3) == ["a1", "a2", "a3"]
    assert [questions_in_test(n) for n in (1, 2, 3, 4, 7)] == [3, 3, 3, 4, 4]


# --- milestone tests -------------------------------------------------------------------------


def test_all_correct_passes_and_raises_the_parts_to_assumed_known() -> None:
    nodes = RM.hidden["present-tenses"]
    out = milestone_outcome(RM, "present-tenses", [NodeAnswer(n, True) for n in nodes], {})
    assert out.result == "pass" and out.opened == ()
    assert out.raised == dict.fromkeys(nodes, ASSUMED_KNOWN)
    assert out.trace is not None and out.trace.rule == "milestone.pass"


def test_one_wrong_out_of_four_passes_with_that_gap_open() -> None:
    nodes = RM.hidden["present-tenses"]
    answers = [NodeAnswer(nodes[0], True), NodeAnswer(nodes[1], True),
               NodeAnswer(nodes[2], False, misconception="simple-for-now"),
               NodeAnswer(nodes[0], True)]  # fmt: skip
    out = milestone_outcome(RM, "present-tenses", answers, {})
    assert out.result == "gap" and out.opened == (nodes[2],)
    assert nodes[2] not in out.raised and out.raised[nodes[0]] == ASSUMED_KNOWN
    assert out.trace is not None and "simple-for-now" in out.trace.rule_vi


def test_one_wrong_out_of_three_or_two_wrong_fails_and_opens_every_part() -> None:
    nodes = RM.hidden["passive"]  # one hidden node: a test of 3 on it
    three = [NodeAnswer(nodes[0], True), NodeAnswer(nodes[0], True), NodeAnswer(nodes[0], False)]
    out = milestone_outcome(RM, "passive", three, {})
    assert out.result == "fail" and out.opened == nodes and out.raised == {}
    nodes = RM.hidden["nouns-articles"]
    two = [NodeAnswer(n, i % 2 == 0) for i, n in enumerate([*nodes, nodes[0]])]
    assert milestone_outcome(RM, "nouns-articles", two, {}).result == "fail"


def test_a_milestone_test_with_answers_from_elsewhere_is_refused() -> None:
    with pytest.raises(ValueError):
        milestone_outcome(RM, "passive", [NodeAnswer("past-perfect", True)], {})
    with pytest.raises(ValueError):
        milestone_outcome(RM, "passive", [], {})


def test_a_part_already_above_assumed_known_is_never_lowered_by_a_pass() -> None:
    nodes = RM.hidden["present-tenses"]
    out = milestone_outcome(
        RM, "present-tenses", [NodeAnswer(n, True) for n in nodes], {nodes[0]: 0.97}
    )
    assert nodes[0] not in out.raised


def test_status_comes_from_the_hidden_nodes_and_reopens_when_one_drops() -> None:
    p = known("present-tenses")
    unaided = dict.fromkeys(RM.hidden["present-tenses"], 2)
    assert milestone_status(RM, p, unaided)["present-tenses"] == "known"
    mastered = {**p, **dict.fromkeys(RM.hidden["present-tenses"], 0.97)}
    assert milestone_status(RM, mastered, unaided)["present-tenses"] == "mastered"
    dropped = {**p, "present-simple": 0.6}  # later evidence, e.g. writing errors
    assert milestone_status(RM, dropped, unaided)["present-tenses"] == "partial"
    assert milestone_status(RM, {}, {})["present-tenses"] == "unknown"


def test_the_most_foundational_weak_part_is_learned_first() -> None:
    p = {"first-conditional": 0.95, "second-conditional": 0.95, "past-continuous": 0.95}
    node, trace = next_to_learn(RM, ["third-conditional"], p)
    assert node == "past-perfect"  # third conditional needs past perfect, which is weak
    assert trace is not None and trace.kind == "root_cause" and trace.alternatives
    node, _ = next_to_learn(RM, ["third-conditional"], {**p, "past-perfect": 0.95})
    assert node == "third-conditional"
    done = {**p, "past-perfect": 0.95, "third-conditional": 0.95}
    assert next_to_learn(RM, ["third-conditional"], done) == (None, None)


# --- the level test --------------------------------------------------------------------------


def test_levels_need_every_milestone_at_and_below() -> None:
    a2 = {m for m, lv in RM.level.items() if lv == "A2"}
    b1 = {m for m, lv in RM.level.items() if lv == "B1"}
    assert level_from(RM, set()) == "A1"
    assert level_from(RM, a2) == "A2"
    assert level_from(RM, a2 | b1) == "B1"
    assert level_from(RM, b1) == "A1"  # B1 milestones without A2 ones do not make a B1
    assert level_from(RM, set(RM.level)) == "C1"


def test_the_vocabulary_level_stops_at_the_first_missed_tier() -> None:
    assert vocab_level({}) == "A1"
    assert vocab_level({"A2": (3, 3), "B1": (2, 3), "B2": (1, 3), "C1": (3, 3)}) == "B1"
    assert vocab_level({"A2": (3, 3), "B1": (3, 3), "B2": (2, 3), "C1": (2, 3)}) == "C1"


def test_the_level_test_asks_about_milestones_and_stops() -> None:
    caps = dict.fromkeys(RM.level, 4)
    first, trace = level_test_next(RM, [], asks_per_milestone=caps)
    assert first in RM.level and trace.kind == "placement_step"
    answers = [Answer(m, True) for m in RM.level for _ in range(2)]  # 20 answers: the budget
    assert level_test_next(RM, answers, asks_per_milestone=caps)[0] is None
    assert known_milestones(RM, answers) == frozenset(RM.level)
    assert level_test_next(RM, [], asks_per_milestone=dict.fromkeys(RM.level, 0))[0] is None


def test_known_milestones_seed_their_hidden_nodes_only() -> None:
    seeded = seed_from_level_test(RM, {"present-tenses"})
    assert seeded == dict.fromkeys(RM.hidden["present-tenses"], ASSUMED_KNOWN)


def test_the_ielts_range_is_always_labelled_an_estimate() -> None:
    assert ielts_range_vi("B2") == "IELTS khoảng 5.5–6.5 (ước lượng, không phải điểm IELTS)"  # noqa: RUF001
    assert "dưới 4.0" in ielts_range_vi("A2") and "ước lượng" in ielts_range_vi("A1")


def test_the_english_gate_baseline_is_committed_and_honest() -> None:
    import json

    baseline = json.loads(
        (DATA.parents[1] / "evals" / "baselines" / "english-placement.json").read_text()
    )
    assert baseline["gate"]["milestones"] == len(RM.milestones)
    cells = {(c["learner"], c["budget"]): c for c in baseline["cells"]}
    assert set(cells) == {(m, b) for m in ("single_gap", "any_state") for b in (6, 10, 15, 20)}
    assert cells[("any_state", 20)]["level_exact"] >= cells[("any_state", 6)]["level_exact"]
