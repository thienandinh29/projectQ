"""graph.py on deliberately different shapes: chain, wide (flat), diamond."""

from datetime import UTC, datetime

import pytest

from app.engine.graph import UNSEEN_P_KNOWN, Graph, root_cause
from app.schemas import KnowledgeGraph

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)

# a -> b -> c -> d
CHAIN = Graph.from_edges("abcd", [("a", "b"), ("b", "c"), ("c", "d")])
# five independent concepts plus one goal needing all of them
WIDE = Graph.from_edges("pqrstg", [(x, "g") for x in "pqrst"])
#   a
#  / \
# b   c
#  \ /
#   d -> e
DIAMOND = Graph.from_edges("abcde", [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")])


def test_topological_order_and_depth() -> None:
    assert CHAIN.order == ("a", "b", "c", "d")
    assert dict(CHAIN.depth) == {"a": 0, "b": 1, "c": 2, "d": 3}
    assert DIAMOND.order == ("a", "b", "c", "d", "e")
    assert DIAMOND.depth["d"] == 2 and DIAMOND.depth["e"] == 3
    assert WIDE.depth["g"] == 1


def test_roots_leaves_ancestors_descendants() -> None:
    assert DIAMOND.roots() == ("a",)
    assert DIAMOND.leaves() == ("e",)
    assert DIAMOND.ancestors("e") == {"d": 1, "b": 2, "c": 2, "a": 3}
    assert DIAMOND.descendants("a") == {"b": 1, "c": 1, "d": 2, "e": 3}
    assert DIAMOND.ancestors("a") == {}
    assert set(WIDE.roots()) == set("pqrst")


def test_order_is_deterministic_regardless_of_input_order() -> None:
    edges = [("c", "d"), ("a", "c"), ("d", "e"), ("b", "d"), ("a", "b")]
    assert Graph.from_edges("edcba", edges).order == DIAMOND.order


@pytest.mark.parametrize(
    ("edges", "message"),
    [
        ([("a", "b"), ("b", "a")], "cycle"),
        ([("a", "a")], "self-loop"),
        ([("a", "z")], "unknown"),
    ],
)
def test_invalid_graphs_rejected(edges: list[tuple[str, str]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Graph.from_edges("ab", edges)


def test_unknown_concept_lookup_raises() -> None:
    with pytest.raises(KeyError):
        CHAIN.ancestors("zzz")
    with pytest.raises(KeyError):
        root_cause(CHAIN, {}, "zzz", now=NOW)


def test_from_contract_keeps_vietnamese_names() -> None:
    kg = KnowledgeGraph.model_validate(
        {
            "concepts": [
                {"slug": "bien", "name_vi": "Biến", "name_en": "Variables", "sources": ["u"]},
                {"slug": "vong-lap", "name_vi": "Vòng lặp", "name_en": "Loops", "sources": ["u"]},
            ],
            "edges": [{"from": "bien", "to": "vong-lap"}],
        }
    )
    graph = Graph.from_contract(kg)
    assert graph.order == ("bien", "vong-lap")
    assert graph.name_vi("vong-lap") == "Vòng lặp"
    assert graph.name_vi("not-named") == "not-named"


def test_root_cause_picks_the_weakest_prerequisite() -> None:
    mastery = {"a": 0.9, "b": 0.31, "c": 0.6, "d": 0.5}
    slug, trace = root_cause(CHAIN, mastery, "d", now=NOW, item_id="d-1", misconception="m")
    assert slug == "b"
    assert trace.kind == "root_cause"
    assert trace.rule == "root_cause.lowest_p_known"
    assert trace.prior == 0.31
    assert "0,31" in trace.rule_vi
    assert (trace.evidence.item_id, trace.evidence.correct, trace.evidence.misconception) == (
        "d-1",
        False,
        "m",
    )
    # every other candidate (the failed concept + its other prerequisites) is explained
    assert [a.concept_slug for a in trace.alternatives] == ["d", "c", "a"]
    assert all(a.why_not_vi for a in trace.alternatives)


def test_mastered_prerequisites_are_never_chosen() -> None:
    mastery = {"a": 0.96, "b": 0.97, "c": 0.99, "d": 0.1}
    slug, trace = root_cause(CHAIN, mastery, "d", now=NOW)
    assert slug == "d"
    assert trace.rule == "root_cause.no_weak_prerequisite"
    assert all("nắm vững" in a.why_not_vi for a in trace.alternatives)


def test_root_concept_remediates_itself() -> None:
    slug, trace = root_cause(CHAIN, {"a": 0.1}, "a", now=NOW)
    assert slug == "a"
    assert trace.alternatives == []


def test_tie_goes_to_the_deeper_foundation() -> None:
    # b and a equally weak: a is the deeper foundation (depth 0), so learn it first.
    slug, trace = root_cause(DIAMOND, {"a": 0.3, "b": 0.3, "c": 0.9, "d": 0.8}, "e", now=NOW)
    assert slug == "a"
    why_b = next(x.why_not_vi for x in trace.alternatives if x.concept_slug == "b")
    assert "sâu hơn" in why_b


def test_tie_at_same_depth_goes_by_slug_and_is_deterministic() -> None:
    mastery = {"a": 0.99, "b": 0.4, "c": 0.4, "d": 0.8}
    first = root_cause(DIAMOND, mastery, "e", now=NOW)
    again = root_cause(DIAMOND, dict(reversed(mastery.items())), "e", now=NOW)
    assert first == again
    assert first[0] == "b"


def test_float_noise_does_not_break_ties() -> None:
    slug, _ = root_cause(DIAMOND, {"a": 0.99, "b": 0.1 + 0.2, "c": 0.3, "d": 0.8}, "e", now=NOW)
    assert slug == "b"


def test_unseen_concepts_count_as_the_bkt_prior() -> None:
    # Only the goal has a mastery row; every prerequisite is unseen and equally weak.
    slug, trace = root_cause(WIDE, {"g": 0.5}, "g", now=NOW)
    assert slug == "p"  # all depth 0, all 1 hop: slug order
    assert trace.prior == UNSEEN_P_KNOWN
    assert len(trace.alternatives) == 5  # g + the four other prerequisites


def test_wide_graph_finds_the_one_gap() -> None:
    mastery = dict.fromkeys("pqrst", 0.9) | {"s": 0.2, "g": 0.3}
    assert root_cause(WIDE, mastery, "g", now=NOW)[0] == "s"
