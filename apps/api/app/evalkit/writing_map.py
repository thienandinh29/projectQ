"""Score the owner's mapping check (specs/writing/step-2.2.md; gate: mapping >= 90% on 100 errors).

    uv run python -m app.evalkit.writing_map ../../data/private/writing/errors.csv

Input: the sheet from `app.writing.export_errors` with `correct_node` filled by hand (empty: no node
fits). Output: JSON metrics only, safe to commit; never the sheet itself.
- accuracy: among errors the map sent to a node, the share whose node the owner confirmed;
- coverage: the share of typed errors the map sends anywhere (low until new hidden nodes exist);
- missed: unmapped errors the owner says do fit a node (rows the map could gain).
"""

import argparse
import csv
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from app.evalkit.stats import rate

GATE_ACCURACY = 0.90
GATE_MIN_ERRORS = 100


@dataclass(frozen=True)
class MapScore:
    typed: int
    mapped: int
    correct: int
    accuracy: float | None
    accuracy_interval: tuple[float, float] | None
    coverage: float | None
    missed: int
    per_type: dict[str, dict[str, int]]
    gate_met: bool
    note: str


def base_type(errant_type: str) -> str:
    head, _, rest = errant_type.partition(":")
    return rest if head in {"M", "R", "U"} and rest else errant_type


def score(rows: Sequence[dict[str, str]]) -> MapScore:
    mapped = [r for r in rows if r["node"].strip()]
    correct = [r for r in mapped if r["node"].strip() == r["correct_node"].strip()]
    missed = [r for r in rows if not r["node"].strip() and r["correct_node"].strip()]
    per_type: dict[str, dict[str, int]] = defaultdict(lambda: {"mapped": 0, "correct": 0})
    for r in mapped:
        t = per_type[base_type(r["errant_type"])]
        t["mapped"] += 1
        t["correct"] += r["node"].strip() == r["correct_node"].strip()
    acc = rate(len(correct), len(mapped))
    point = acc.point
    interval = (
        (round(acc.low, 4), round(acc.high, 4))
        if acc.low is not None and acc.high is not None
        else None
    )
    met = point is not None and len(mapped) >= GATE_MIN_ERRORS and point >= GATE_ACCURACY
    if len(mapped) < GATE_MIN_ERRORS:
        note = f"{len(mapped)} mapped errors checked; the gate needs {GATE_MIN_ERRORS}."
    else:
        note = "Gate met." if met else f"Accuracy below {GATE_ACCURACY:.0%}: fix the rows first."
    return MapScore(
        typed=len(rows),
        mapped=len(mapped),
        correct=len(correct),
        accuracy=round(point, 4) if point is not None else None,
        accuracy_interval=interval,
        coverage=round(len(mapped) / len(rows), 4) if rows else None,
        missed=len(missed),
        per_type=dict(sorted(per_type.items())),
        gate_met=met,
        note=note,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("sheet", type=Path)
    args = parser.parse_args(argv)
    with args.sheet.open(encoding="utf-8", newline="") as f:
        print(json.dumps(asdict(score(list(csv.DictReader(f)))), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
