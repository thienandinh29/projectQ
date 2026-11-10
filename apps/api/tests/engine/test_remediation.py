"""Remediation rules on varied graph shapes, including what placement actually produces."""

import random
from datetime import UTC, datetime

import pytest

from app.engine.graph import UNSEEN_P_KNOWN, WEAK_THRESHOLD, Graph
from app.engine.placement import Answer, seed_mastery
from app.engine.remediation import (
    REPEATED_MISCONCEPTION,
    RemediationPlan,
    remediate,
    resume,
)
from app.engine.trace import DecisionTrace

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)

CHAIN = Graph.from_edges("abcd", [("a", "b"), ("b", "c"), ("c", "d")])
WIDE = Graph.from_edges("pqrstg", [(x, "g") for x in "pqrst"])
DIAMOND = Graph.from_edges("abcde", [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")])
DEEP = Graph.from_edges([f"n{i}" for i in range(10)], [(f"n{i}", f"n{i + 1}") for i in range(9)])
SINGLE = Graph.from_edges(["only"], [])
SHAPES = {"chain": CHAIN, "wide": WIDE, "diamond": DIAMOND, "deep": DEEP, "single": SINGLE}


# --- the threshold: weak means probably-not-known, not not-yet-mastered ------------------------


def test_a_solid_but_unmastered_prerequisite_is_never_sent_back_to() -> None:
    # b is at 0.85, exactly what placement gives a concept it found known.
    mastery = {"a": 0.96, "b": 0.85, "c": 0.2}
    plan, trace = remediate(CHAIN, mastery, "c", now=NOW)
    assert plan.target_slug == "c" and plan.action == "practice_again"
    why_b = next(a.why_not_vi for a in trace.alternatives if a.concept_slug == "b")
    assert "Tương đối vững" in why_b


def test_after_real_placement_remediation_goes_to_the_unknown_not_the_known() -> None:
    # Gap is c: placement marked a, b known (0.85) and c, d unknown (0.15).
    answers = [Answer("d", False), Answer("b", True), Answer("c", False)]
    mastery = seed_mastery(CHAIN, answers)
    assert mastery == {"a": 0.85, "b": 0.85, "c": 0.15, "d": 0.15}
    plan, _ = remediate(CHAIN, mastery, "d", now=NOW)
    assert plan.target_slug == "c" and plan.action == "review_prerequisite"
    # A wrong answer on a concept placed as known must not drag the learner to its known base.
    plan, _ = remediate(CHAIN, mastery, "b", now=NOW)
    assert plan.target_slug == "b" and plan.action == "practice_again"


def test_threshold_is_the_boundary() -> None:
    at = {"a": WEAK_THRESHOLD, "b": 0.9}
    assert remediate(CHAIN, at, "b", now=NOW)[0].target_slug == "b"  # 0.5 is not below 0.5
    below = {"a": WEAK_THRESHOLD - 0.01, "b": 0.9}
    assert remediate(CHAIN, below, "b", now=NOW)[0].target_slug == "a"


# --- rule 1: weakest prerequisite --------------------------------------------------------------


def test_goes_to_the_weakest_prerequisite_with_a_reason() -> None:
    mastery = {"a": 0.9, "b": 0.31, "c": 0.4, "d": 0.2}
    plan, trace = remediate(
        CHAIN, mastery, "d", now=NOW, item_id="d-1", misconception="m", misconception_vi="Nhầm X."
    )
    assert plan.action == "review_prerequisite"
    assert (plan.origin_slug, plan.target_slug) == ("d", "b")
    assert "«b»" in plan.reason_vi and "0,31" in plan.reason_vi
    assert plan.reason_vi.endswith("Lỗi gặp phải: Nhầm X")  # no doubled full stop
    assert trace.rule == "remediation.review_prerequisite"
    assert trace.concept_slug == "b" and trace.evidence.misconception == "m"
    assert trace.rule_vi == plan.reason_vi
    assert plan.to_contract() is not None


def test_repeated_misconception_does_not_override_a_weak_prerequisite() -> None:
    plan, _ = remediate(
        CHAIN,
        {"a": 0.2, "b": 0.9},
        "b",
        now=NOW,
        misconception="m",
        earlier_misconceptions=["m"] * 5,
    )
    assert plan.action == "review_prerequisite" and plan.target_slug == "a"


# --- rules 2 and 3: misconception ---------------------------------------------------------------

SOLID = {"a": 0.96, "b": 0.9, "c": 0.2}


def test_first_mistake_with_solid_foundations_is_practised_again() -> None:
    plan, trace = remediate(CHAIN, SOLID, "c", now=NOW, misconception="m")
    assert plan.action == "practice_again" and plan.target_slug == "c"
    assert plan.to_contract() is None  # nothing to redirect
    assert trace.rule == "remediation.practice_again"


def test_repeating_the_same_misconception_sends_the_learner_to_the_explanation() -> None:
    plan, trace = remediate(
        CHAIN,
        SOLID,
        "c",
        now=NOW,
        misconception="m",
        misconception_vi="Nghĩ rằng X.",
        earlier_misconceptions=["m"],
    )
    assert plan.action == "address_misconception" and plan.target_slug == "c"
    assert f"{REPEATED_MISCONCEPTION} lần" in plan.reason_vi and "Nghĩ rằng X" in plan.reason_vi
    assert trace.rule == "remediation.repeated_misconception"
    contract = plan.to_contract()
    assert contract is not None and contract.concept_slug == "c"


def test_only_the_same_misconception_counts_and_unlabelled_wrong_answers_do_not() -> None:
    other = remediate(
        CHAIN, SOLID, "c", now=NOW, misconception="m", earlier_misconceptions=["x", "y"]
    )[0]
    assert other.action == "practice_again"
    none = remediate(CHAIN, SOLID, "c", now=NOW, earlier_misconceptions=["m", "m"])[0]
    assert none.action == "practice_again"  # this answer carries no misconception


# --- resume ------------------------------------------------------------------------------------


def test_resume_continues_with_the_next_weak_prerequisite() -> None:
    # Boolean work is done (0.7); conditionals are still weak.
    mastery = {"a": 0.96, "b": 0.7, "c": 0.4, "d": 0.2}
    slug, trace = resume(CHAIN, mastery, "d", now=NOW)
    assert slug == "c"
    assert trace.kind == "next_item" and trace.rule == "remediation.resume_next_prerequisite"
    assert trace.evidence.correct is None  # no answer was given
    assert "0,40" in trace.rule_vi


def test_resume_returns_to_the_origin_when_the_foundations_hold() -> None:
    slug, trace = resume(CHAIN, {"a": 0.96, "b": 0.7, "c": 0.8, "d": 0.2}, "d", now=NOW)
    assert slug == "d" and trace.rule == "remediation.resume_origin"
    assert "quay lại «d»" in trace.rule_vi


# --- properties over many shapes ---------------------------------------------------------------


def _random_dag(rng: random.Random) -> Graph:
    n = rng.randint(2, 12)
    names = [f"c{i:02d}" for i in range(n)]
    edges = [(names[i], names[j]) for j in range(n) for i in range(j) if rng.random() < 0.3]
    return Graph.from_edges(names, edges)


def _cases() -> list[tuple[Graph, dict[str, float]]]:
    rng = random.Random(11)
    cases = []
    for graph in [*SHAPES.values(), *(_random_dag(rng) for _ in range(40))]:
        for _ in range(5):
            mastery = {
                s: rng.choice([0.05, 0.15, 0.3, 0.49, 0.5, 0.6, 0.85, 0.97]) for s in graph.order
            }
            cases.append((graph, mastery))
    return cases


@pytest.mark.parametrize(("graph", "mastery"), _cases())
def test_target_is_the_weakest_ancestor_or_the_failed_concept_itself(
    graph: Graph, mastery: dict[str, float]
) -> None:
    for failed in graph.order:
        plan, trace = remediate(graph, mastery, failed, now=NOW)
        ancestors = graph.ancestors(failed)
        weak = {s: mastery[s] for s in ancestors if mastery[s] < WEAK_THRESHOLD}
        if weak:
            assert plan.target_slug in weak and mastery[plan.target_slug] == min(weak.values())
            assert plan.action == "review_prerequisite"
        else:
            assert plan.target_slug == failed
        DecisionTrace.model_validate(trace.model_dump(mode="json"))
        assert trace.rule_vi and trace.rule.startswith("remediation.")


@pytest.mark.parametrize(("graph", "mastery"), _cases()[::5])
def test_repeated_failures_walk_down_to_a_root_and_stop(
    graph: Graph, mastery: dict[str, float]
) -> None:
    for start in graph.order:
        current, steps = start, 0
        while True:
            plan, _ = remediate(graph, mastery, current, now=NOW)
            if plan.target_slug == current:
                break
            assert graph.depth[plan.target_slug] < graph.depth[current]  # strictly down
            current, steps = plan.target_slug, steps + 1
            assert steps <= len(graph)
        # It stopped on a concept none of whose prerequisites are weak.
        assert all(mastery[a] >= WEAK_THRESHOLD for a in graph.ancestors(current))


def test_unseen_concepts_are_treated_as_weak() -> None:
    assert UNSEEN_P_KNOWN < WEAK_THRESHOLD
    plan, _ = remediate(CHAIN, {"c": 0.9}, "c", now=NOW)  # a and b have no mastery rows
    assert plan.target_slug == "a"


def test_plan_is_frozen_data() -> None:
    plan = RemediationPlan("c", "c", "practice_again", "x", None)
    with pytest.raises(AttributeError):
        plan.target_slug = "a"  # type: ignore[misc]
