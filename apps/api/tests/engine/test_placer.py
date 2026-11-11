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


def test_bayes_placer_never_asks_a_concept_twice() -> None:
    p = BayesPlacer()
    assert p.next_question(CHAIN, ANSWERS, now=NOW) == placement_bayes.next_question(
        CHAIN, ANSWERS, now=NOW, max_asks_per_concept=1
    )
    answers: list[Answer] = []
    while (slug := p.next_question(CHAIN, answers, now=NOW)[0]) is not None:
        assert slug not in {a.slug for a in answers}
        answers.append(Answer(slug, slug == "a"))
    assert p.gap(CHAIN, answers) == "b"
    assert set(p.seed_mastery(CHAIN, answers)) == set("abcd")
