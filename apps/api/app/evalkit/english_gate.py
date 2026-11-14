"""Gate: level-test accuracy on the English roadmap, simulated (specs/level-test, point 13).

Learners are simulated on the milestone graph of `data/courses/english-ielts.yaml` with the BKT
observation model, as `placement_sim` does for the toy shapes. Reported per learner model and
question budget, each with an exact interval:
- `gap_exact`: the gap the test names is the true one (target: >= 0.9 within 20 questions);
- `level_exact`: the CEFR level shown to the learner is the true one.
CI compares a fresh run with the committed baseline: a drop of more than `TOLERANCE` fails; an
improvement passes and is raised on purpose with `run --out`.

Usage, from apps/api:
    uv run python -m app.evalkit.english_gate run --out ../../evals/baselines/english-placement.json
    uv run python -m app.evalkit.english_gate check ../../evals/baselines/english-placement.json
"""

import argparse
import json
import random
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import REPO_ROOT
from app.curriculum.course import load_course
from app.curriculum.roadmap import build_roadmap
from app.engine import placement_bayes
from app.engine.bkt import DEFAULT_PARAMS
from app.engine.milestones import LEVEL_TEST_CONFIDENCE, Roadmap, level_from
from app.engine.placement import Answer
from app.evalkit.placement_sim import learners, true_gap
from app.evalkit.stats import rate

COURSE = REPO_ROOT / "data" / "courses" / "english-ielts.yaml"
BUDGETS = (6, 10, 15, 20)
MODELS = ("single_gap", "any_state")
RUNS = 1000
SEED = 20261114
TOLERANCE = 0.02


def _place(roadmap: Roadmap, known: frozenset[str], budget: int, rng: random.Random) -> tuple:  # type: ignore[type-arg]
    params = DEFAULT_PARAMS["mcq"]
    graph = roadmap.milestones
    answers: list[Answer] = []
    while len(answers) < budget:
        slug, _ = placement_bayes.next_question(
            graph, answers, max_questions=budget, confidence=LEVEL_TEST_CONFIDENCE
        )
        if slug is None:
            break
        p = 1 - params.p_slip if slug in known else params.p_guess
        answers.append(Answer(slug, rng.random() < p))
    estimate = placement_bayes.belief(graph, answers).best()[0]
    return placement_bayes.gap(graph, answers), estimate, len(answers)


def run(course_path: Path = COURSE, runs: int = RUNS) -> dict[str, object]:
    roadmap = build_roadmap(load_course(course_path))
    graph = roadmap.milestones
    states, family = placement_bayes._states(graph)
    cells = []
    for model in MODELS:
        for budget in BUDGETS:
            rng = random.Random(f"{SEED}-{model}-{budget}")
            truths = learners(graph, model, runs, rng)
            gap_hits = level_hits = asked = 0
            for known in truths:
                located, estimate, n = _place(roadmap, known, budget, rng)
                gap_hits += located == true_gap(graph, known)
                level_hits += level_from(roadmap, estimate) == level_from(roadmap, known)
                asked += n
            g, lv = rate(gap_hits, runs), rate(level_hits, runs)
            cells.append(
                {
                    "learner": model,
                    "budget": budget,
                    "gap_exact": round(gap_hits / runs, 4),
                    "gap_exact_ci95": [round(g.low or 0.0, 4), round(g.high or 0.0, 4)],
                    "level_exact": round(level_hits / runs, 4),
                    "level_exact_ci95": [round(lv.low or 0.0, 4), round(lv.high or 0.0, 4)],
                    "mean_questions": round(asked / runs, 2),
                }
            )
    return {
        "gate": {"name": "english-placement", "course": course_path.name, "runs": runs,
                 "seed": SEED, "milestones": len(graph), "states": len(states),
                 "state_family": family, "target": "gap_exact >= 0.9 within 20 questions"},
        "cells": cells,
    }  # fmt: skip


def check(baseline: dict[str, object], fresh: dict[str, object]) -> list[str]:
    def by_key(result: dict[str, object]) -> dict[tuple[object, object], dict[str, object]]:
        cells = result["cells"]
        assert isinstance(cells, list)
        return {(c["learner"], c["budget"]): c for c in cells}

    old, new = by_key(baseline), by_key(fresh)
    problems = [f"missing cell {k}" for k in old if k not in new]
    for key, cell in old.items():
        if key not in new:
            continue
        for metric in ("gap_exact", "level_exact"):
            before, after = cell[metric], new[key][metric]
            assert isinstance(before, float) and isinstance(after, float)
            if after < before - TOLERANCE:
                problems.append(f"{key} {metric}: {after} < baseline {before}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run")
    run_p.add_argument("--out", type=Path)
    check_p = sub.add_parser("check")
    check_p.add_argument("baseline", type=Path)
    args = parser.parse_args(argv)
    fresh = run()
    if args.command == "run":
        text = json.dumps(fresh, indent=1) + "\n"
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        print(text)
        return 0
    problems = check(json.loads(args.baseline.read_text(encoding="utf-8")), fresh)
    for c in fresh["cells"]:  # type: ignore[attr-defined]
        print(c)
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    print("english placement gate: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
