"""Bayesian placement: posterior, question rule, stopping, traces and a seeded comparison."""

import math
import random
from datetime import UTC, datetime

import pytest

from app.engine import placement, placement_bayes
from app.engine.bkt import DEFAULT_PARAMS
from app.engine.graph import Graph
from app.engine.placement import Answer
from app.engine.placement_bayes import (
    MAX_QUESTIONS,
    SEED_CEILING,
    SEED_FLOOR,
    belief,
    gap,
    information_gain,
    next_question,
    seed_mastery,
)

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
MCQ = DEFAULT_PARAMS["mcq"]

CHAIN = Graph.from_edges("abcd", [("a", "b"), ("b", "c"), ("c", "d")])
WIDE = Graph.from_edges("pqrstg", [(x, "g") for x in "pqrst"])
DIAMOND = Graph.from_edges("abcde", [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")])
TWO_CHAINS = Graph.from_edges(
    ["a1", "a2", "a3", "b1", "b2", "b3"],
    [("a1", "a2"), ("a2", "a3"), ("b1", "b2"), ("b2", "b3")],
)
SHAPES = {"chain": CHAIN, "wide": WIDE, "diamond": DIAMOND, "two-chains": TWO_CHAINS}


# --- the state space ----------------------------------------------------------------------------


def test_states_are_exactly_the_prerequisite_closed_sets() -> None:
    states, family = placement_bayes._states(CHAIN)
    assert family == "ideals"
    assert set(states) == {frozenset("abcd"[:k]) for k in range(5)}  # a chain: 5 prefixes
    for shape in SHAPES.values():
        for state in placement_bayes._states(shape)[0]:
            assert all(p in state for n in state for p in shape.parents[n])


def test_large_graphs_fall_back_to_single_gap_states(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(placement_bayes, "MAX_STATES", 3)
    placement_bayes._enumerate.cache_clear()
    try:
        states, family = placement_bayes._states(DIAMOND)
        assert family == "single_gap"
        everything = frozenset("abcde")
        expected = {everything} | {everything - {n, *DIAMOND.descendants(n)} for n in "abcde"}
        assert set(states) == expected
    finally:
        placement_bayes._enumerate.cache_clear()


# --- the posterior ------------------------------------------------------------------------------


def test_posterior_is_a_distribution_and_follows_bayes_rule() -> None:
    b = belief(CHAIN, [Answer("c", True)])
    assert math.isclose(sum(b.probs), 1.0)
    # Uniform prior over 5 states; "c correct" has likelihood 0.9 if c is known, 0.25 otherwise.
    knows_c = 2 * 0.9  # states {a,b,c} and {a,b,c,d}
    not_c = 3 * 0.25
    assert math.isclose(b.p_known("c"), knows_c / (knows_c + not_c))
    assert b.p_known("a") >= b.p_known("b") >= b.p_known("c") >= b.p_known("d")


def test_a_repeated_answer_is_real_evidence() -> None:
    once = belief(CHAIN, [Answer("c", True)]).p_known("c")
    twice = belief(CHAIN, [Answer("c", True), Answer("c", True)]).p_known("c")
    assert twice > once


def test_one_lucky_guess_does_not_settle_a_branch() -> None:
    # The graph-walk marks a, b and c known after one correct answer on d; the posterior does not.
    assert placement.classify(CHAIN, [Answer("d", True)])["a"] == "known"
    b = belief(CHAIN, [Answer("d", True)])
    assert 0.5 < b.p_known("a") < 0.95


def test_prior_shifts_the_posterior() -> None:
    weak = belief(CHAIN, [], prior={n: 0.1 for n in "abcd"})
    strong = belief(CHAIN, [], prior={n: 0.9 for n in "abcd"})
    assert weak.p_known("a") < strong.p_known("a")


def test_unknown_concept_in_answers_is_rejected() -> None:
    with pytest.raises(KeyError):
        belief(CHAIN, [Answer("zz", True)])


# --- information gain and question choice --------------------------------------------------------


def test_information_gain_is_zero_when_the_concept_is_settled() -> None:
    settled = placement_bayes.Belief((frozenset("ab"),), (1.0,), "ideals")
    assert information_gain(settled, "a", MCQ) == 0.0


def test_information_gain_is_highest_where_the_state_is_split() -> None:
    b = belief(CHAIN, [])
    gains = {n: information_gain(b, n, MCQ) for n in "abcd"}
    # Uniform over 5 prefixes: b and c split the states 3/2 and 2/3; a and d split 4/1 and 1/4.
    assert gains["b"] > gains["a"] and gains["c"] > gains["d"]


def test_first_question_and_trace() -> None:
    slug, trace = next_question(CHAIN, [], now=NOW)
    assert slug in {"b", "c"}
    assert trace.kind == "placement_step"
    assert trace.rule == "placement.bayes.ask"
    assert trace.rule_vi and "bit" in trace.rule_vi
    assert trace.at == NOW
    assert len(trace.alternatives) == 3


def test_runs_are_repeatable() -> None:
    answers = [Answer("c", False), Answer("b", True)]
    assert next_question(DIAMOND, answers, now=NOW) == next_question(DIAMOND, answers, now=NOW)


# --- stopping -----------------------------------------------------------------------------------


def test_stops_when_confident_and_names_the_gap() -> None:
    answers = [Answer("c", False)] * 3 + [Answer("b", True)] * 3
    slug, trace = next_question(CHAIN, answers, now=NOW, confidence=0.9)
    assert slug is None
    assert trace.rule == "placement.done.confident"
    assert trace.concept_slug == "c"
    assert gap(CHAIN, answers) == "c"
    assert trace.posterior is not None and trace.posterior >= 0.9


def test_stops_at_the_budget_and_says_it_is_unsure() -> None:
    answers = [Answer("b", True), Answer("b", False)] * 3
    slug, trace = next_question(CHAIN, answers, now=NOW, max_questions=6)
    assert slug is None
    assert trace.rule == "placement.done.budget"
    assert "chưa chắc" in trace.rule_vi


def test_max_asks_per_concept_never_repeats_and_ends_when_exhausted() -> None:
    answers: list[Answer] = []
    while True:
        slug, trace = next_question(CHAIN, answers, now=NOW, max_asks_per_concept=1)
        if slug is None:
            break
        assert slug not in {a.slug for a in answers}
        answers.append(Answer(slug, slug in "ab"))  # truth: knows a and b, not c and d
    assert len(answers) <= 4
    assert trace.rule.startswith("placement.done.")


def test_all_known_learner() -> None:
    answers = [Answer(n, True) for n in "abcd" for _ in range(2)]
    assert gap(CHAIN, answers) is None
    _, trace = next_question(CHAIN, answers, now=NOW)
    assert "nắm mọi khái niệm" in trace.rule_vi


def test_empty_graph_is_rejected() -> None:
    with pytest.raises(ValueError):
        next_question(Graph.from_edges([], []), [], now=NOW)


def test_seed_mastery_stays_inside_the_bounds() -> None:
    seeds = seed_mastery(CHAIN, [Answer("d", True)] * 4)
    assert all(SEED_FLOOR <= p <= SEED_CEILING for p in seeds.values())
    assert seeds["a"] == SEED_CEILING  # very likely known, but placement is not mastery


# --- simulated learners -------------------------------------------------------------------------


def _run(graph: Graph, planted: str, rng: random.Random, *, noisy: bool, budget: int) -> str | None:
    unknown = {planted, *graph.descendants(planted)}
    answers: list[Answer] = []
    while (slug := next_question(graph, answers, now=NOW, max_questions=budget)[0]) is not None:
        assert len(answers) < budget
        if noisy:
            p = MCQ.p_guess if slug in unknown else 1 - MCQ.p_slip
            answers.append(Answer(slug, rng.random() < p))
        else:
            answers.append(Answer(slug, slug not in unknown))
    return gap(graph, answers)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_noiseless_learner_gap_is_always_located_within_budget(shape: str) -> None:
    graph = SHAPES[shape]
    for planted in graph.order:
        assert _run(graph, planted, random.Random(0), noisy=False, budget=MAX_QUESTIONS) == planted


@pytest.mark.parametrize("shape", ["chain", "diamond", "two-chains"])
def test_beats_the_graph_walk_under_noise_with_the_same_budget(shape: str) -> None:
    # Seeded and deterministic. The full comparison, with intervals, is docs/v2/placement-eval.md.
    graph = SHAPES[shape]
    runs = 150
    bayes_hits = walk_hits = 0
    for planted in graph.order:
        rng_b, rng_w = random.Random(f"b-{planted}"), random.Random(f"w-{planted}")
        unknown = {planted, *graph.descendants(planted)}
        for _ in range(runs):
            bayes_hits += _run(graph, planted, rng_b, noisy=True, budget=6) == planted
            answers: list[Answer] = []
            while (s := placement.next_question(graph, answers, now=NOW)[0]) is not None:
                p = MCQ.p_guess if s in unknown else 1 - MCQ.p_slip
                answers.append(Answer(s, rng_w.random() < p))
            walk_hits += placement.gap(graph, answers) == planted
    assert bayes_hits > walk_hits * 1.1
