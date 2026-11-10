import json
from fractions import Fraction

import pytest

from app.content.models import Graph
from tests.content.fakes import ROOT, topic


@pytest.mark.parametrize("slug", ["python-conditions", "fractions", "cell-basics"])
def test_golden_references_unique_answers_and_pending_reviews(slug: str) -> None:
    sources, chunks, graph, items = topic(slug)
    assert len(items) == 15
    assert len(chunks) == 5
    assert len({c.chunk_id for c in chunks}) == 5
    assert len({item.id for item in items}) == 15
    assert len({item.answer_id for item in items}) == 15
    assert all(i.status == "needs_review" and i.verification is None for i in items)
    assert all(i.human_review.status == "pending" and not i.human_review.reviewer for i in items)
    assert all(i.source in {s.url for s in sources} for i in items)
    assert all(c.representation == "agent_paraphrase_vi" for c in chunks)
    assert graph.team_payload()["edges"]


def test_fraction_computations_independently_match_keys() -> None:
    _, _, _, items = topic("fractions")
    expected = {
        1: Fraction(3, 8),
        3: Fraction(1, 6),
        7: Fraction(7, 7),
        8: Fraction(5, 5),
        9: Fraction(1),
        10: Fraction(2, 3),
        11: Fraction(9, 15),
        12: Fraction(1, 2),
        13: Fraction(5, 8),
        14: Fraction(1, 3),
    }
    for index, value in expected.items():
        item = items[index - 1]
        correct = next(o for o in item.options if o.correct)
        assert Fraction(correct.label) == value
    assert Fraction(2, 3) > Fraction(3, 6)
    # Equivalent-fraction choices must not conceal another mathematically correct answer.
    for index in (10, 12):
        item = items[index - 1]
        assert sum(Fraction(o.label) == expected[index] for o in item.options) == 1


def test_python_arithmetic_logic_and_branch_keys() -> None:
    _, _, _, items = topic()
    answers = [next(o.label for o in item.options if o.correct) for item in items]
    assert str(17 % 5) == answers[0]
    assert str(246 % 10) == answers[2]
    numbers = [4, 7]
    assert str(numbers[0] == numbers[1]) == answers[3]
    right, wrong = True, False
    assert str(right and wrong) == answers[6]
    assert str(wrong or right) == answers[7]
    assert str(not (3 < 2)) == answers[8]
    branches = []
    x = 5
    if x > 0:
        branches.append("P")
    elif x > 3:
        branches.append("Q")
    assert branches == ["P"]
    assert answers[12] == "Chỉ P"


def test_graph_rejects_cycle_and_unknown_endpoint() -> None:
    _, _, graph, _ = topic()
    data = graph.model_dump(mode="json", by_alias=True)
    data["edges"].append({**data["edges"][0], "from": "elif-order", "to": "remainder"})
    with pytest.raises(ValueError, match="cycle"):
        Graph.model_validate(data)
    data["edges"][-1]["from"] = "unknown"
    with pytest.raises(ValueError, match="unknown"):
        Graph.model_validate(data)


def test_evaluation_has_50_items_20_hints_and_no_confirmed_human_labels() -> None:
    directory = ROOT / "data/guardrails"

    def read(name: str) -> list[dict[str, object]]:
        return [
            json.loads(line) for line in (directory / name).read_text(encoding="utf-8").splitlines()
        ]

    assert len(read("items.jsonl")) == 50
    assert len(read("hints.jsonl")) == 20
    labels = read("human_labels.template.jsonl")
    assert len(labels) == 70
    assert all(label["status"] == "pending" and label["reviewer"] is None for label in labels)
