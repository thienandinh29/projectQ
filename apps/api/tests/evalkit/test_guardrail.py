"""Scoring, on a hand-built sample whose every rate was worked out on paper first."""

import json
from typing import Any

import pytest

from app.evalkit.guardrail import MIN_PLANTED, Verdict, score
from app.evalkit.labels import Record


def gen(
    rid: str, *defect_sets: list[str], kind: str = "item", resolved: list[str] | None = None
) -> Record:
    data: dict[str, Any] = {
        "id": rid,
        "kind": kind,
        "source": "generated",
        "topic": "python",
        "labels": [{"labeler": f"p{i}", "defects": d} for i, d in enumerate(defect_sets)],
    }
    if resolved is not None:
        data["resolved_defects"] = resolved
    return Record.model_validate(data)


def planted(rid: str, defect: str, kind: str = "item") -> Record:
    return Record.model_validate(
        {"id": rid, "kind": kind, "source": "planted", "topic": "python", "planted_defect": defect}
    )


# Generated items:
#   g1 good, served      g2 good, served      g3 good, rejected        (false alarm)
#   g4 key_wrong, rejected (caught)           g5 not_supported, served (leaked)
#   g6 vietnamese_error, served (out of scope)  g7 vietnamese_error, rejected
# Planted: p1, p2 rejected; p3 served (missed).
# Double labels on g1, g2, g4, g5, g6: g5's two labelers disagree (resolved), the rest agree.
RECORDS = [
    gen("g1", [], []),
    gen("g2", [], []),
    gen("g3", []),
    gen("g4", ["key_wrong"], ["key_wrong"]),
    gen("g5", ["not_supported"], [], resolved=["not_supported"]),
    gen("g6", ["vietnamese_error"], ["vietnamese_error"]),
    gen("g7", ["vietnamese_error"]),
    planted("p1", "key_wrong"),
    planted("p2", "not_supported"),
    planted("p3", "ambiguous"),
]
SERVED = {"g1", "g2", "g5", "g6", "p3"}
VERDICTS: dict[str, Verdict] = {r.id: ("served" if r.id in SERVED else "rejected") for r in RECORDS}


def test_every_rate_matches_the_worked_example() -> None:
    items = score(RECORDS, VERDICTS).items
    assert items is not None
    assert (items.generated, items.planted) == (7, 3)
    assert (items.served, items.rejected) == (4, 3)
    assert (items.raw_bad.k, items.raw_bad.n) == (4, 7)  # g4, g5, g6, g7
    assert (items.served_error.k, items.served_error.n) == (2, 4)  # g5, g6 among g1 g2 g5 g6
    assert (items.served_in_scope_error.k, items.served_in_scope_error.n) == (1, 4)  # g5
    assert (items.false_alarm.k, items.false_alarm.n) == (1, 3)  # g3 of g1 g2 g3
    assert (items.catch_generated.k, items.catch_generated.n) == (1, 2)  # g4 of g4 g5
    assert (items.catch_planted.k, items.catch_planted.n) == (2, 3)
    assert items.out_of_scope_served == 1 and items.leaks_served == 0


def test_out_of_scope_defects_are_not_charged_to_the_gate() -> None:
    items = score(RECORDS, VERDICTS).items
    assert items is not None
    # g7 (out of scope, rejected) is in neither the catch nor the false-alarm denominator
    assert items.catch_generated.n == 2 and items.false_alarm.n == 3


def test_labeler_agreement_is_measured_on_the_double_labelled_records() -> None:
    items = score(RECORDS, VERDICTS).items
    assert items is not None
    # worked out by hand: agreement 4 of 5, chance 0.36 -> kappa 0.6875
    assert items.kappa_n == 5 and items.kappa == pytest.approx(0.6875)
    assert not any("labelers agree" in n for n in items.notes)


def test_notes_say_what_the_sample_cannot_show() -> None:
    items = score(RECORDS, VERDICTS).items
    assert items is not None
    text = " | ".join(items.notes)
    assert (
        "only 3 planted items: even with every one caught, a 90% catch rate cannot be shown" in text
    )
    assert f"(needs {MIN_PLANTED})" in text
    assert "only 2 naturally bad items" in text
    assert "cannot rule out more than 5%" in text
    assert "not built to catch" in text  # the served Vietnamese error is listed, not charged


def test_weak_labeler_agreement_is_called_out() -> None:
    records = [gen(f"g{i}", ["key_wrong"], [], resolved=["key_wrong"]) for i in range(6)]
    report = score(records, dict.fromkeys((r.id for r in records), "served"))
    assert report.items is not None and report.items.kappa is not None
    assert report.items.kappa < 0.6 and any(
        "labelers agree only weakly" in n for n in report.items.notes
    )


def test_a_clean_large_sample_has_no_caveats_about_its_size() -> None:
    records = [gen(f"g{i}", [], []) for i in range(80)]
    records += [planted(f"p{i}", "key_wrong") for i in range(40)]
    verdicts: dict[str, Verdict] = {
        r.id: ("rejected" if r.id.startswith("p") else "served") for r in records
    }
    items = score(records, verdicts).items
    assert items is not None
    assert items.served_error.high is not None and items.served_error.high < 0.05
    assert items.catch_planted.low is not None and items.catch_planted.low >= 0.90
    # no complaint about too few planted items, and none about the 5% bound
    assert not [n for n in items.notes if "cannot be shown" in n or "cannot rule out" in n]


def test_hints_report_leaks_even_though_the_gate_is_not_built_for_them() -> None:
    hints = [
        gen("h1", [], [], kind="hint"),
        gen("h2", ["leaks_answer"], ["leaks_answer"], kind="hint"),
        gen("h3", ["wrong"], ["wrong"], kind="hint"),
    ]
    verdicts: dict[str, Verdict] = {"h1": "served", "h2": "served", "h3": "rejected"}
    report = score(hints, verdicts)
    assert report.items is None and report.hints is not None
    assert report.hints.leaks_served == 1
    assert report.hints.catch_generated.n == 1 and report.hints.catch_generated.k == 1  # h3
    assert any("leak the answer" in n for n in report.hints.notes)


def test_items_and_hints_are_scored_separately() -> None:
    mixed = [*RECORDS, gen("h1", [], [], kind="hint")]
    report = score(mixed, {**VERDICTS, "h1": "served"})
    assert report.items is not None and report.hints is not None
    assert report.items.generated == 7 and report.hints.generated == 1


def test_verdicts_must_match_the_records() -> None:
    with pytest.raises(ValueError, match="missing"):
        score(RECORDS, {k: v for k, v in VERDICTS.items() if k != "g1"})
    with pytest.raises(ValueError, match="unknown"):
        score(RECORDS, {**VERDICTS, "zzz": "served"})


def test_report_serialises_for_the_dashboard_and_prints() -> None:
    report = score(RECORDS, VERDICTS)
    data = json.loads(json.dumps(report.to_dict()))
    assert data["items"]["served_error"] == {
        "k": 2,
        "n": 4,
        "point": 0.5,
        "low": pytest.approx(0.0676, abs=0.001),
        "high": pytest.approx(0.9324, abs=0.001),
    }
    assert data["hints"] is None
    text = report.format()
    assert "served error rate (any defect)    2/4 = 50%" in text and "Read with care" in text
