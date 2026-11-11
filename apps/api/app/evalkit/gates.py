"""Evaluation gates: seeded evaluations that CI compares with a committed baseline.

An evaluation becomes a gate when it is deterministic (fixed seeds, no network, no model calls)
and fast enough for every push. The first gate is placement accuracy (`placement_sim`). A cell
fails when its score drops more than `TOLERANCE` below the baseline; improvements pass and are
reported, so the baseline is raised on purpose, in a reviewed commit, with `run --out`.

Usage, from apps/api:
    uv run python -m app.evalkit.gates run --out ../../evals/baselines/placement-gate.json
    uv run python -m app.evalkit.gates check ../../evals/baselines/placement-gate.json
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from app.evalkit.placement_sim import SHAPES, evaluate

TOLERANCE = 0.02  # results are deterministic; this only absorbs rounding


@dataclass(frozen=True)
class PlacementGate:
    name: str = "placement"
    shapes: tuple[str, ...] = ("chain-4", "diamond-5", "two-chains-6")
    learner_models: tuple[str, ...] = ("single_gap",)
    budgets: tuple[int, ...] = (6, 10)
    strategies: tuple[str, ...] = ("walk+verify", "bayes")
    runs: int = 1000
    seed: int = 20261111
    metric: str = "gap_exact"


GATE = PlacementGate()


def run_gate(gate: PlacementGate = GATE) -> dict[str, object]:
    rows = evaluate(
        runs=gate.runs,
        budgets=gate.budgets,
        seed=gate.seed,
        shapes={s: SHAPES[s] for s in gate.shapes},
        learner_models=gate.learner_models,
        strategies=gate.strategies,
    )
    return {"gate": asdict(gate), "cells": [_cell(r) for r in rows]}


def _cell(row: dict[str, object]) -> dict[str, object]:
    keys = ("shape", "learner", "budget", "strategy", "gap_exact", "mean_questions")
    return {k: row[k] for k in keys}


def _key(cell: dict[str, object]) -> tuple[object, ...]:
    return (cell["shape"], cell["learner"], cell["budget"], cell["strategy"])


def _cells(report: dict[str, object]) -> list[dict[str, object]]:
    cells = report.get("cells")
    if not isinstance(cells, list):
        raise ValueError("report has no cells")
    return cells


def _score(cell: dict[str, object], metric: str) -> float:
    value = cell[metric]
    if not isinstance(value, (int, float)):
        raise ValueError(f"{metric} is not a number")
    return float(value)


@dataclass(frozen=True)
class Finding:
    kind: str  # "regression" | "improvement" | "missing" | "new"
    cell: str
    baseline: float | None
    current: float | None


def compare(
    baseline: dict[str, object], current: dict[str, object], tolerance: float = TOLERANCE
) -> list[Finding]:
    metric = GATE.metric
    base = {_key(c): c for c in _cells(baseline)}
    now = {_key(c): c for c in _cells(current)}
    findings: list[Finding] = []
    for key in sorted(set(base) | set(now), key=str):
        name = "/".join(str(k) for k in key)
        b = _score(base[key], metric) if key in base else None
        c = _score(now[key], metric) if key in now else None
        if c is None:
            findings.append(Finding("missing", name, b, None))
        elif b is None:
            findings.append(Finding("new", name, None, c))
        elif c < b - tolerance:
            findings.append(Finding("regression", name, b, c))
        elif c > b + tolerance:
            findings.append(Finding("improvement", name, b, c))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the gate and write a baseline")
    run.add_argument("--out", type=Path, required=True)
    check = sub.add_parser("check", help="run the gate and compare with a baseline")
    check.add_argument("baseline", type=Path)
    args = parser.parse_args(argv)

    current = run_gate()
    if args.command == "run":
        args.out.write_text(json.dumps(current, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(_cells(current))} cells)")
        return 0
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    findings = compare(baseline, current)
    for f in findings:
        print(f"{f.kind:12} {f.cell}: baseline {f.baseline} -> current {f.current}")
    failed = [f for f in findings if f.kind in {"regression", "missing"}]
    print("gate FAILED" if failed else "gate passed", f"({len(findings)} findings)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
