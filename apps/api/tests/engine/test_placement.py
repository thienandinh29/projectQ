"""Graph-walk placement: inference rules, question choice, stopping, and a simulated learner."""

import random
from datetime import UTC, datetime

import pytest

from app.engine.bkt import DEFAULT_PARAMS, MASTERY_THRESHOLD
from app.engine.graph import Graph
from app.engine.placement import (
    KNOWN_P,
    MAX_QUESTIONS,
    UNKNOWN_P,
    Answer,
    classify,
    gap,
    next_question,
    seed_mastery,
)

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)

CHAIN = Graph.from_edges("abcd", [("a", "b"), ("b", "c"), ("c", "d")])
WIDE = Graph.from_edges("pqrstg", [(x, "g") for x in "pqrst"])
DIAMOND = Graph.from_edges("abcde", [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")])
# Two independent chains: a1 -> a2 -> a3 and b1 -> b2 -> b3.
TWO_CHAINS = Graph.from_edges(
    ["a1", "a2", "a3", "b1", "b2", "b3"],
    [("a1", "a2"), ("a2", "a3"), ("b1", "b2"), ("b2", "b3")],
)
SHAPES = {"chain": CHAIN, "wide": WIDE, "diamond": DIAMOND, "two-chains": TWO_CHAINS}


def yes(slug: str) -> Answer:
    return Answer(slug, True)


def no(slug: str) -> Answer:
    return Answer(slug, False)


# --- inference ----------------------------------------------------------------------------------


def test_correct_makes_prerequisites_known() -> None:
    status = classify(DIAMOND, [yes("d")])
    assert status == {"a": "known", "b": "known", "c": "known", "d": "known", "e": "undecided"}


def test_wrong_makes_dependents_unknown() -> None:
    status = classify(DIAMOND, [no("b")])
    assert status == {
        "a": "undecided",
        "b": "unknown",
        "c": "undecided",
        "d": "unknown",
        "e": "unknown",
    }


def test_unknown_beats_known_between_inferences() -> None:
    # Correct on e makes c known; wrong on a makes c unknown. The wrong answer is stronger evidence.
    status = classify(DIAMOND, [yes("e"), no("a")])
    assert status["c"] == "unknown"
    assert status["a"] == "unknown"  # direct answer


def test_direct_answer_beats_inference() -> None:
    # Wrong on b makes d unknown, but the learner answered d correctly: trust the direct answer.
    status = classify(DIAMOND, [no("b"), yes("d")])
    assert status["d"] == "known"
    assert status["b"] == "unknown"


def test_later_answer_to_the_same_concept_wins() -> None:
    assert classify(CHAIN, [no("c"), yes("c")])["c"] == "known"


def test_unknown_concept_in_answers_rejected() -> None:
    with pytest.raises(KeyError):
        classify(CHAIN, [yes("zzz")])


def test_seed_mastery_stays_below_the_mastery_threshold() -> None:
    seeded = seed_mastery(CHAIN, [no("d"), yes("b")])
    assert seeded == {"a": KNOWN_P, "b": KNOWN_P, "c": 0.2, "d": UNKNOWN_P}
    assert KNOWN_P < MASTERY_THRESHOLD
    assert DEFAULT_PARAMS["mcq"].p_init == 0.2  # undecided keeps the BKT prior


# --- choosing the next question -----------------------------------------------------------------


def test_first_question_is_the_most_advanced_concept() -> None:
    slug, trace = next_question(DIAMOND, [], now=NOW)
    assert slug == "e"
    assert trace.kind == "placement_step"
    assert trace.rule == "placement.start_advanced"
    assert "«e»" in trace.rule_vi


def test_wrong_answer_chases_the_gap_among_its_prerequisites() -> None:
    slug, trace = next_question(CHAIN, [no("d")], now=NOW)
    assert slug == "b"  # binary search over a, b, c
    assert trace.rule == "placement.chase_gap"
    assert trace.evidence.correct is False
    assert {a.concept_slug for a in trace.alternatives} == {"a", "c"}
    assert all(a.why_not_vi for a in trace.alternatives)


def test_chase_only_asks_prerequisites_of_failed_concepts() -> None:
    # Wrong on a3 (chain a); the other chain b is unrelated and must not be asked yet.
    slug, trace = next_question(TWO_CHAINS, [no("a3")], now=NOW)
    assert slug == "a2" or slug == "a1"
    assert trace.rule == "placement.chase_gap"


def test_explore_when_no_gap_has_been_found_yet() -> None:
    # Correct on a3 settles chain a; chain b is still undecided and has no known failure.
    slug, trace = next_question(TWO_CHAINS, [yes("a3")], now=NOW)
    assert slug == "b2"  # b3 would settle 3 on a correct answer but only 1 on a wrong one
    assert trace.rule == "placement.explore"


def test_never_asks_the_same_concept_twice() -> None:
    answers = [no("d"), yes("b"), no("c")]
    for i in range(len(answers)):
        slug, _ = next_question(CHAIN, answers[:i], now=NOW)
        assert slug not in {a.slug for a in answers[:i]}


def test_choice_is_deterministic() -> None:
    first = next_question(DIAMOND, [no("e")], now=NOW)
    again = next_question(DIAMOND, [no("e")], now=NOW)
    assert first == again


# --- stopping -----------------------------------------------------------------------------------


def test_gap_located_when_unknown_concept_has_all_prerequisites_known() -> None:
    answers = [no("d"), yes("b"), no("c")]
    slug, trace = next_question(CHAIN, answers, now=NOW)
    assert slug is None
    assert trace.rule == "placement.done.gap_located"
    assert trace.concept_slug == "c"
    assert "«c»" in trace.rule_vi
    assert [a.concept_slug for a in trace.alternatives] == ["d"]
    assert gap(CHAIN, answers) == "c"


def test_all_known_when_the_top_answer_is_correct() -> None:
    slug, trace = next_question(CHAIN, [yes("d")], now=NOW, verify=False)
    assert slug is None
    assert trace.rule == "placement.done.all_known"
    assert gap(CHAIN, [yes("d")]) is None


def test_verification_is_on_by_default() -> None:
    # One correct answer on the hardest concept is not trusted on its own.
    slug, trace = next_question(CHAIN, [yes("d")], now=NOW)
    assert slug == "c"
    assert trace.rule == "placement.verify"
    # Once the neighbours confirm it (and the budget allows), placement finishes.
    done_slug, done = next_question(CHAIN, [yes("d"), yes("c"), yes("b"), yes("a")], now=NOW)
    assert done_slug is None
    assert done.rule == "placement.done.all_known"


def test_budget_stops_placement_with_a_best_estimate() -> None:
    graph = Graph.from_edges(
        [f"w{i}" for i in range(9)] + ["goal"], [(f"w{i}", "goal") for i in range(9)]
    )
    answers = [no("goal")] + [yes(f"w{i}") for i in range(MAX_QUESTIONS - 1)]
    slug, trace = next_question(graph, answers, now=NOW)
    assert slug is None
    assert trace.rule == "placement.done.budget"
    assert gap(graph, answers) == "goal"


def test_empty_graph_rejected() -> None:
    with pytest.raises(ValueError):
        next_question(Graph.from_edges([], []), [])


# --- simulated learner (spec success criterion) -------------------------------------------------


def _unknown_set(graph: Graph, planted: str) -> set[str]:
    return {planted, *graph.descendants(planted)}


def _run(graph: Graph, planted: str, rng: random.Random, *, noisy: bool) -> tuple[str | None, int]:
    """Place a learner whose real gap is `planted`; returns (located gap, questions asked)."""
    mcq = DEFAULT_PARAMS["mcq"]
    unknown = _unknown_set(graph, planted)
    answers: list[Answer] = []
    while True:
        slug, _ = next_question(graph, answers, now=NOW)
        if slug is None:
            return gap(graph, answers), len(answers)
        if noisy:
            p_correct = mcq.p_guess if slug in unknown else 1 - mcq.p_slip
            correct = rng.random() < p_correct
        else:
            correct = slug not in unknown
        answers.append(Answer(slug, correct))


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_noiseless_learner_gap_is_always_located_within_budget(shape: str) -> None:
    graph = SHAPES[shape]
    for planted in graph.order:
        located, asked = _run(graph, planted, random.Random(0), noisy=False)
        assert located == planted, (shape, planted)
        assert asked <= MAX_QUESTIONS, (shape, planted, asked)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_run_ends_within_budget_even_with_noise(shape: str) -> None:
    graph = SHAPES[shape]
    rng = random.Random(7)
    for planted in graph.order:
        for _ in range(50):
            _, asked = _run(graph, planted, rng, noisy=True)
            assert asked <= MAX_QUESTIONS


# --- verify mode: leftover budget re-checks the result ------------------------------------------


def test_verify_skips_neighbours_that_were_already_answered_directly() -> None:
    # The gap's only prerequisite (b) was answered directly, so there is nothing left to re-check.
    answers = [no("d"), yes("b"), no("c")]
    slug, trace = next_question(CHAIN, answers, now=NOW, verify=True)
    assert slug is None
    assert trace.rule == "placement.done.gap_located"


def test_verify_catches_a_lucky_guess_that_hid_the_real_gap() -> None:
    # Truth: the learner fails b (so c and d too). A lucky correct on d marked b known, and a
    # wrong on c then "located" the gap at c. Verifying b (inferred known) exposes the real gap.
    answers = [yes("d"), no("c")]
    assert gap(CHAIN, answers) == "c"
    slug, _ = next_question(CHAIN, answers, now=NOW, verify=True)
    assert slug == "b"
    assert gap(CHAIN, [*answers, no("b")]) == "b"


def test_verify_checks_an_inferred_concept_when_no_gap_was_found() -> None:
    slug, trace = next_question(CHAIN, [yes("d")], now=NOW, verify=True)
    assert slug == "c"
    assert trace.rule == "placement.verify"


def test_verify_finishes_when_nothing_is_left_to_check() -> None:
    answers = [no("d"), yes("b"), no("c"), yes("a")]
    slug, trace = next_question(CHAIN, answers, now=NOW, verify=True)
    assert slug is None
    assert trace.rule == "placement.done.gap_located"


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_verify_never_exceeds_the_budget_and_stays_exact_without_noise(shape: str) -> None:
    graph = SHAPES[shape]
    for planted in graph.order:
        unknown = _unknown_set(graph, planted)
        answers: list[Answer] = []
        while (slug := next_question(graph, answers, now=NOW, verify=True)[0]) is not None:
            answers.append(Answer(slug, slug not in unknown))
        assert len(answers) <= MAX_QUESTIONS
        assert gap(graph, answers) == planted


def _exact_rate(graph: Graph, *, verify: bool) -> float:
    rng = random.Random(3)
    mcq = DEFAULT_PARAMS["mcq"]
    hits = total = 0
    for planted in graph.order:
        unknown = _unknown_set(graph, planted)
        for _ in range(200):
            answers: list[Answer] = []
            while (s := next_question(graph, answers, now=NOW, verify=verify)[0]) is not None:
                p = mcq.p_guess if s in unknown else 1 - mcq.p_slip
                answers.append(Answer(s, rng.random() < p))
            hits += gap(graph, answers) == planted
            total += 1
    return hits / total


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_verify_improves_accuracy_under_noise(shape: str) -> None:
    # Measured 2026-11-07 (seeded): plain 45-55% exact, verify 58-64%. Neither reaches the 90%
    # target in specs/engine/spec.md; this test only guards that verify keeps helping.
    graph = SHAPES[shape]
    assert _exact_rate(graph, verify=True) > _exact_rate(graph, verify=False) + 0.05
