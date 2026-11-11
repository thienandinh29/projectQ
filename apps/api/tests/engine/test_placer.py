from datetime import UTC, datetime

import pytest

from app.engine import placement, placement_bayes
from app.engine.graph import Graph
from app.engine.placement import Answer
from app.engine.placer import BayesPlacer, WalkPlacer, make_placer

NOW = datetime(2026, 11, 11, tzinfo=UTC)
CHAIN = Graph.from_edges("abcd", [("a", "b"), ("b", "c"), ("c", "d")])
ANSWERS = [Answer("c", False), Answer("a", True)]


def test_make_placer() -> None:
    assert isinstance(make_placer("walk"), WalkPlacer)
    assert isinstance(make_placer("bayes"), BayesPlacer)
    with pytest.raises(ValueError):
        make_placer("other")  # type: ignore[arg-type]


def test_walk_placer_is_the_graph_walk() -> None:
    p = WalkPlacer()
    assert p.next_question(CHAIN, ANSWERS, now=NOW) == placement.next_question(
        CHAIN, ANSWERS, now=NOW
    )
    assert p.gap(CHAIN, ANSWERS) == placement.gap(CHAIN, ANSWERS)
    assert p.seed_mastery(CHAIN, ANSWERS) == placement.seed_mastery(CHAIN, ANSWERS)


def test_bayes_placer_respects_the_items_available_per_concept() -> None:
    p = BayesPlacer()
    available = {"a": 1, "b": 2, "c": 2, "d": 1}
    answers: list[Answer] = []
    while (slug := p.next_question(CHAIN, answers, now=NOW, available=available)[0]) is not None:
        answers.append(Answer(slug, slug in "ab"))
        assert sum(a.slug == slug for a in answers) <= available[slug]
    assert len(answers) <= p.max_questions
    assert p.gap(CHAIN, answers) == "c"
    assert set(p.seed_mastery(CHAIN, answers)) == set("abcd")


def test_bayes_placer_never_asks_a_concept_without_items() -> None:
    slug, _ = BayesPlacer().next_question(CHAIN, [], now=NOW, available={"a": 1})
    assert slug == "a"
    slug, trace = BayesPlacer().next_question(CHAIN, [], now=NOW, available={})
    assert slug is None and trace.rule == "placement.done.exhausted"


def test_bayes_placer_matches_the_engine_function() -> None:
    assert BayesPlacer().next_question(CHAIN, ANSWERS, now=NOW) == placement_bayes.next_question(
        CHAIN, ANSWERS, now=NOW, max_questions=10
    )
