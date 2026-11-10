"""Next-step rules: each priority, the post-placement scenario, and properties on random graphs."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from app.engine.bkt import MASTERY_THRESHOLD
from app.engine.graph import WEAK_THRESHOLD, Graph
from app.engine.path import CONFIRM_BELOW, NextStep, next_step, target_difficulty
from app.engine.placement import Answer, seed_mastery
from app.engine.trace import DecisionTrace
from tests.engine.mocks import GRAPH as PYTHON

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
DONE = 0.97

CHAIN = Graph.from_edges("abcd", [("a", "b"), ("b", "c"), ("c", "d")])
DIAMOND = Graph.from_edges("abcde", [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")])
WIDE = Graph.from_edges("pqrstg", [(x, "g") for x in "pqrst"])
DEEP = Graph.from_edges([f"n{i}" for i in range(10)], [(f"n{i}", f"n{i + 1}") for i in range(9)])
SINGLE = Graph.from_edges(["only"], [])
# one shallow isolated concept z next to a chain a -> b
SPLIT = Graph.from_edges(["a", "b", "z"], [("a", "b")])


def step(graph: Graph, mastery: dict[str, float], **kw: object) -> tuple[NextStep, DecisionTrace]:
    return next_step(graph, mastery, now=NOW, **kw)  # type: ignore[arg-type]


# --- the rules ---------------------------------------------------------------------------------


def test_a_new_learner_starts_at_the_first_foundation() -> None:
    result, trace = step(CHAIN, {})
    assert (result.kind, result.concept_slug) == ("learn", "a")
    assert "nền tảng đầu tiên" in result.reason_vi and result.reason_vi == trace.rule_vi
    assert trace.kind == "next_item" and trace.rule == "next_item.learn"


def test_learning_follows_the_textbook_order_among_ready_concepts() -> None:
    # Both roots are ready and new; the shallower comes first, ties by name.
    result, _ = step(WIDE, {})
    assert (result.kind, result.concept_slug) == ("learn", "p")


def test_what_you_started_comes_before_something_new_even_if_shallower() -> None:
    mastery = {"a": 0.96, "b": 0.6, "z": 0.2}  # z is new and shallower; b is in progress
    result, trace = step(SPLIT, mastery)
    assert (result.kind, result.concept_slug) == ("continue", "b")
    assert "Tiếp tục" in result.reason_vi
    assert [
        a.concept_slug
        for a in trace.alternatives
        if "học dở" in a.why_not_vi or "Bài mới" in a.why_not_vi
    ] == ["z"]


def test_a_concept_with_a_weak_foundation_is_never_next_and_the_panel_says_why() -> None:
    mastery = {"a": 0.96, "b": 0.2}  # c builds on a weak b
    result, trace = step(CHAIN, mastery)
    assert result.concept_slug == "b"  # not c or d
    blocked = {
        a.concept_slug: a.why_not_vi for a in trace.alternatives if "Chưa học được" in a.why_not_vi
    }
    assert set(blocked) == {"c", "d"}
    assert "«b»" in blocked["c"] and "0,20" in blocked["c"]


def test_probably_known_concepts_are_confirmed_only_when_nothing_is_unknown() -> None:
    result, _ = step(CHAIN, dict.fromkeys("abcd", 0.85))
    assert (result.kind, result.concept_slug) == ("confirm", "a")
    assert "Xác nhận" in result.reason_vi
    # one unknown concept beats any number of probably-known ones
    mixed = {"a": 0.85, "b": 0.85, "c": 0.85, "d": 0.2}
    result, _ = step(CHAIN, mixed)
    assert (result.kind, result.concept_slug) == ("learn", "d")


def test_everything_mastered_means_done() -> None:
    result, trace = step(CHAIN, dict.fromkeys("abcd", DONE))
    assert (result.kind, result.concept_slug) == ("done", None)
    assert trace.rule == "next_item.done" and "toàn bộ" in result.reason_vi
    DecisionTrace.model_validate(trace.model_dump(mode="json"))


def test_the_boundaries_between_groups() -> None:
    # exactly at the thresholds: 0.5 is in progress, 0.8 is probably known, 0.95 is mastered
    assert step(SINGLE, {"only": WEAK_THRESHOLD})[0].kind == "continue"
    assert step(SINGLE, {"only": WEAK_THRESHOLD - 0.01})[0].kind == "learn"
    assert step(SINGLE, {"only": CONFIRM_BELOW})[0].kind == "confirm"
    assert step(SINGLE, {"only": CONFIRM_BELOW - 0.01})[0].kind == "continue"
    assert step(SINGLE, {"only": MASTERY_THRESHOLD})[0].kind == "done"


# --- after placement: go to the gap -----------------------------------------------------------


def _placed() -> dict[str, float]:
    """Python graph, a learner whose real gap is booleans (the same run as the demo mock)."""
    answers = [
        Answer("danh-sach", False),
        Answer("bieu-thuc-boolean", False),
        Answer("bieu-thuc", True),
        Answer("ham", True),
    ]
    return seed_mastery(PYTHON, answers)


def test_after_placement_the_learner_goes_to_the_gap_not_to_what_placement_found_known() -> None:
    mastery = _placed()
    assert mastery["bien"] == mastery["bieu-thuc"] == mastery["ham"] == 0.85  # placed as known
    result, trace = step(PYTHON, mastery)
    assert (result.kind, result.concept_slug) == ("learn", "bieu-thuc-boolean")
    # the concepts above the gap are blocked, and the panel says by what
    why = {a.concept_slug: a.why_not_vi for a in trace.alternatives}
    assert "Biểu thức boolean" in why["cau-lenh-dieu-kien"] and "0,15" in why["cau-lenh-dieu-kien"]


def test_the_path_then_walks_up_from_the_gap_in_order() -> None:
    mastery = _placed()
    order = []
    for _ in range(len(PYTHON)):
        result, _ = step(PYTHON, mastery)
        if result.concept_slug is None:
            break
        order.append((result.kind, result.concept_slug))
        mastery[result.concept_slug] = DONE
    assert order[:4] == [
        ("learn", "bieu-thuc-boolean"),
        ("learn", "cau-lenh-dieu-kien"),
        ("learn", "vong-lap"),
        ("learn", "danh-sach"),
    ]
    # only then the concepts placement found probably-known, to confirm them
    assert {s for _, s in order[4:]} == {"bien", "bieu-thuc", "ham"}
    assert all(kind == "confirm" for kind, _ in order[4:])


# --- reviews -----------------------------------------------------------------------------------


def test_an_overdue_review_comes_before_new_learning_earliest_first() -> None:
    due = {"b": NOW - timedelta(days=2), "a": NOW - timedelta(days=5)}
    result, trace = step(CHAIN, {"a": 0.97, "b": 0.97}, due_reviews=due)
    assert (result.kind, result.concept_slug) == ("review", "a")
    assert "5 ngày" in result.reason_vi and trace.rule == "next_item.review"


def test_a_review_that_fell_due_a_moment_ago_does_not_pre_empt_learning() -> None:
    # srs.new_card is due at once: the concept just mastered must not be asked straight back
    fresh = {"a": NOW - timedelta(minutes=5)}
    result, _ = step(CHAIN, {"a": 0.97}, due_reviews=fresh)
    assert (result.kind, result.concept_slug) == ("learn", "b")
    just_over = {"a": NOW - timedelta(hours=1, minutes=1)}
    assert step(CHAIN, {"a": 0.97}, due_reviews=just_over)[0].kind == "review"


def test_reviews_for_unknown_concepts_are_ignored() -> None:
    result, _ = step(CHAIN, {}, due_reviews={"nope": NOW - timedelta(days=9)})
    assert result.kind == "learn"


# --- resume (an open remediation) --------------------------------------------------------------


def test_an_open_remediation_comes_back_to_the_origin_when_foundations_hold() -> None:
    mastery = {"a": 0.96, "b": 0.7, "c": 0.8, "d": 0.2}
    result, trace = step(CHAIN, mastery, resume_origin="d")
    assert (result.kind, result.concept_slug) == ("resume", "d")
    assert trace.rule == "remediation.resume_origin" and trace.kind == "next_item"


def test_resume_continues_with_the_next_weak_prerequisite_and_beats_an_overdue_review() -> None:
    mastery = {"a": 0.96, "b": 0.7, "c": 0.4, "d": 0.2}
    due = {"a": NOW - timedelta(days=3)}
    result, _ = step(CHAIN, mastery, resume_origin="d", due_reviews=due)
    assert (result.kind, result.concept_slug) == ("resume", "c")


def test_a_mastered_origin_ends_the_remediation() -> None:
    result, _ = step(CHAIN, {"a": 0.96, "b": 0.96, "c": 0.97, "d": 0.97}, resume_origin="d")
    assert result.kind == "done"
    with pytest.raises(KeyError):
        step(CHAIN, {}, resume_origin="zzz")


# --- difficulty --------------------------------------------------------------------------------


def test_target_difficulty_rises_with_mastery_and_stays_in_range() -> None:
    values = [target_difficulty(p / 20) for p in range(21)]
    assert values == sorted(values) and values[0] >= 0.0 and values[-1] <= 1.0
    assert target_difficulty(0.2) == 0.32 and target_difficulty(0.9) == 0.74
    assert step(CHAIN, {})[0].target_difficulty == 0.32


# --- properties on many shapes -----------------------------------------------------------------


def _random_dag(rng: random.Random) -> Graph:
    n = rng.randint(1, 12)
    names = [f"c{i:02d}" for i in range(n)]
    edges = [(names[i], names[j]) for j in range(n) for i in range(j) if rng.random() < 0.3]
    return Graph.from_edges(names, edges)


def _cases() -> list[tuple[Graph, dict[str, float]]]:
    rng = random.Random(21)
    graphs = [
        CHAIN,
        DIAMOND,
        WIDE,
        DEEP,
        SINGLE,
        SPLIT,
        PYTHON,
        *(_random_dag(rng) for _ in range(40)),
    ]
    values = [0.05, 0.15, 0.3, 0.49, 0.5, 0.6, 0.79, 0.8, 0.85, 0.94, 0.97]
    return [(g, {s: rng.choice(values) for s in g.order}) for g in graphs for _ in range(4)]


@pytest.mark.parametrize(("graph", "mastery"), _cases())
def test_the_next_concept_is_always_learnable_and_something_is_always_next(
    graph: Graph, mastery: dict[str, float]
) -> None:
    result, trace = step(graph, mastery)
    unmastered = [s for s in graph.order if mastery[s] < MASTERY_THRESHOLD]
    if not unmastered:
        assert result.kind == "done" and result.concept_slug is None
        return
    assert result.concept_slug is not None and result.kind in {"learn", "continue", "confirm"}
    chosen = result.concept_slug
    assert mastery[chosen] < MASTERY_THRESHOLD
    assert all(mastery[a] >= WEAK_THRESHOLD for a in graph.parents[chosen])  # solid foundations
    assert 0.0 <= result.target_difficulty <= 1.0 and len(trace.alternatives) <= 5
    DecisionTrace.model_validate(trace.model_dump(mode="json"))


@pytest.mark.parametrize(("graph", "mastery"), _cases()[::3])
def test_following_the_path_masters_everything_in_at_most_n_steps(
    graph: Graph, mastery: dict[str, float]
) -> None:
    mastery = dict(mastery)
    chosen: list[str] = []
    for _ in range(len(graph) + 1):
        result, _ = step(graph, mastery)
        if result.concept_slug is None:
            break
        assert result.concept_slug not in chosen  # once mastered, never chosen again
        chosen.append(result.concept_slug)
        mastery[result.concept_slug] = DONE
    else:
        pytest.fail("the path did not finish")
    assert all(v >= MASTERY_THRESHOLD for v in mastery.values()) and len(chosen) <= len(graph)


def test_the_choice_is_deterministic_and_an_empty_graph_is_an_error() -> None:
    m = {"a": 0.3, "b": 0.6, "c": 0.9}
    assert step(DIAMOND, m) == step(DIAMOND, dict(reversed(m.items())))
    with pytest.raises(ValueError):
        step(Graph.from_edges([], []), {})
