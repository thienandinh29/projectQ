"""The owner's mapping check: export sheet and score (specs/writing/step-2.2.md)."""

from pathlib import Path

from app.evalkit.writing_map import score
from app.writing.export_errors import main, rows


def row(node: str, correct: str, errant_type: str = "R:VERB:SVA") -> dict[str, str]:
    return {"errant_type": errant_type, "node": node, "correct_node": correct}


def test_accuracy_counts_only_mapped_errors_and_coverage_counts_all_typed() -> None:
    sheet = (
        [row("present-simple", "present-simple")] * 92
        + [row("present-simple", "be-present")] * 8
        + [row("", "", "R:PREP")] * 50
        + [row("", "articles-basic", "R:OTHER")] * 2
    )
    s = score(sheet)
    assert (s.typed, s.mapped, s.correct, s.missed) == (152, 100, 92, 2)
    assert s.accuracy == 0.92 and s.coverage == round(100 / 152, 4)
    assert s.accuracy_interval and s.accuracy_interval[0] < 0.92 < s.accuracy_interval[1]
    assert s.per_type == {"VERB:SVA": {"mapped": 100, "correct": 92}}
    assert s.gate_met and s.note == "Gate met."


def test_the_gate_needs_100_errors_and_90_percent() -> None:
    few = score([row("present-simple", "present-simple")] * 40)
    assert few.accuracy == 1.0 and not few.gate_met and "needs 100" in few.note
    low = score([row("a", "a")] * 85 + [row("a", "b")] * 15)
    assert not low.gate_met and "below 90%" in low.note
    empty = score([])
    assert empty.accuracy is None and empty.coverage is None and not empty.gate_met


def test_the_sheet_has_typed_errors_only_and_stays_private(tmp_path: Path) -> None:
    result = {"grammar": {"issues": [
        {"id": 0, "sentence": "She go.", "text": "go", "suggestion": "goes",
         "errant_type": "R:VERB:SVA", "node": "present-simple"},
        {"id": 1, "sentence": "x", "text": "x", "suggestion": None, "errant_type": None,
         "node": None},
    ]}}  # fmt: skip
    sheet = rows([("e1", result), ("e2", {"grammar": None})])
    assert [(r["issue_id"], r["node"], r["correct_node"]) for r in sheet] == [
        ("0", "present-simple", "")
    ]
    assert main(["--learner", "x", "--out", str(tmp_path / "errors.csv")]) == 2
