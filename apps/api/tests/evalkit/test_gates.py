from pathlib import Path

from app.evalkit.gates import GATE, PlacementGate, compare, run_gate


def report(**scores: float) -> dict[str, object]:
    return {
        "cells": [
            {"shape": s, "learner": "single_gap", "budget": 6, "strategy": "bayes", "gap_exact": v}
            for s, v in scores.items()
        ]
    }


def test_unchanged_results_pass() -> None:
    assert compare(report(a=0.8, b=0.7), report(a=0.8, b=0.7)) == []


def test_a_drop_beyond_tolerance_is_a_regression() -> None:
    findings = compare(report(a=0.80), report(a=0.70))
    assert [(f.kind, f.baseline, f.current) for f in findings] == [("regression", 0.8, 0.7)]


def test_small_changes_within_tolerance_pass_and_gains_are_reported() -> None:
    assert compare(report(a=0.80), report(a=0.79)) == []
    assert [f.kind for f in compare(report(a=0.80), report(a=0.90))] == ["improvement"]


def test_missing_and_new_cells_are_reported() -> None:
    kinds = {f.cell.split("/")[0]: f.kind for f in compare(report(a=0.8), report(b=0.8))}
    assert kinds == {"a": "missing", "b": "new"}


def test_the_gate_is_deterministic_and_matches_the_committed_baseline_shape() -> None:
    small = PlacementGate(shapes=("chain-4",), budgets=(6,), runs=30)
    assert run_gate(small) == run_gate(small)
    baseline = Path(__file__).resolve().parents[4] / "evals" / "baselines" / "placement-gate.json"
    assert baseline.exists()
    assert len(GATE.shapes) * len(GATE.budgets) * len(GATE.strategies) == 12
