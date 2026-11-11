"""Simulated evaluation of placement strategies (seeded, no DB, no LLM).

A simulated learner has a hidden knowledge state and answers each question with the BKT observation
model (correct with probability 1 - slip when the concept is known, `guess` otherwise). A strategy
asks up to `budget` questions and names the gap. Reported per strategy, shape, learner model and
budget: how often the located gap is exactly right, how often the whole state is right, and the mean
number of questions, each rate with an exact (Clopper-Pearson) interval.

Learner models
  - `single_gap`: one planted concept and everything that builds on it is unknown (the criterion in
    specs/engine/spec.md). Every concept is planted equally often.
  - `any_state`: a state drawn uniformly from all prerequisite-closed states (several gaps, or
    none).

Usage, from apps/api:
    uv run python -m app.evalkit.placement_sim --runs 2000 --out ../../docs/v2/placement-eval.json
"""

import argparse
import json
import random
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.engine import placement, placement_bayes
from app.engine.bkt import DEFAULT_PARAMS, BKTParams
from app.engine.graph import Graph
from app.engine.placement import Answer
from app.evalkit.stats import rate

NOW = datetime(2026, 11, 11, tzinfo=UTC)
State = frozenset[str]

SHAPES: dict[str, Graph] = {
    "chain-4": Graph.from_edges("abcd", [("a", "b"), ("b", "c"), ("c", "d")]),
    "wide-6": Graph.from_edges("pqrstg", [(x, "g") for x in "pqrst"]),
    "diamond-5": Graph.from_edges(
        "abcde", [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")]
    ),
    "two-chains-6": Graph.from_edges(
        ["a1", "a2", "a3", "b1", "b2", "b3"],
        [("a1", "a2"), ("a2", "a3"), ("b1", "b2"), ("b2", "b3")],
    ),
    "tree-10": Graph.from_edges(
        [f"n{i}" for i in range(10)],
        [
            ("n0", "n1"),
            ("n0", "n2"),
            ("n1", "n3"),
            ("n1", "n4"),
            ("n2", "n5"),
            ("n2", "n6"),
            ("n3", "n7"),
            ("n5", "n8"),
            ("n6", "n9"),
        ],
    ),
}

# A strategy: (graph, answers so far, budget) -> next concept or None; and a final gap estimate.
Ask = Callable[[Graph, Sequence[Answer], int], str | None]
Locate = Callable[[Graph, Sequence[Answer]], str | None]


@dataclass(frozen=True)
class Strategy:
    name: str
    ask: Ask
    locate: Locate
    state: Callable[[Graph, Sequence[Answer]], State] | None = None


def _walk(verify: bool) -> Strategy:
    def ask(graph: Graph, answers: Sequence[Answer], budget: int) -> str | None:
        return placement.next_question(
            graph, answers, now=NOW, max_questions=budget, verify=verify
        )[0]

    def state(graph: Graph, answers: Sequence[Answer]) -> State:
        status = placement.classify(graph, answers)
        return frozenset(n for n, s in status.items() if s == "known")

    return Strategy("walk+verify" if verify else "walk", ask, placement.gap, state)


def _bayes(confidence: float, name: str, max_asks: int | None = None) -> Strategy:
    def ask(graph: Graph, answers: Sequence[Answer], budget: int) -> str | None:
        return placement_bayes.next_question(
            graph,
            answers,
            now=NOW,
            max_questions=budget,
            confidence=confidence,
            max_asks_per_concept=max_asks,
        )[0]

    def state(graph: Graph, answers: Sequence[Answer]) -> State:
        return placement_bayes.belief(graph, answers).best()[0]

    return Strategy(name, ask, placement_bayes.gap, state)


STRATEGIES = (
    _walk(False),
    _walk(True),
    _bayes(0.9, "bayes"),  # stops early at 90% posterior
    _bayes(1.01, "bayes-full"),  # always spends the whole budget
    _bayes(0.9, "bayes-once", max_asks=1),  # at most one question per concept
)


def true_gap(graph: Graph, known: State) -> str | None:
    frontier = [
        n for n in graph.order if n not in known and all(p in known for p in graph.parents[n])
    ]
    if not frontier:
        return None
    return min(frontier, key=lambda n: (graph.depth[n], graph.order.index(n)))


def learners(graph: Graph, model: str, runs: int, rng: random.Random) -> list[State]:
    everything = frozenset(graph.order)
    if model == "single_gap":
        planted = [graph.order[i % len(graph.order)] for i in range(runs)]
        return [everything - {n, *graph.descendants(n)} for n in planted]
    if model == "any_state":
        states = placement_bayes._states(graph)[0]
        return [rng.choice(states) for _ in range(runs)]
    raise ValueError(f"unknown learner model {model!r}")


def simulate(
    graph: Graph,
    strategy: Strategy,
    known: State,
    budget: int,
    rng: random.Random,
    params: BKTParams,
) -> tuple[str | None, State | None, int]:
    answers: list[Answer] = []
    while (slug := strategy.ask(graph, answers, budget)) is not None:
        p = 1 - params.p_slip if slug in known else params.p_guess
        answers.append(Answer(slug, rng.random() < p))
        if len(answers) > budget:  # a strategy must never exceed its budget
            raise AssertionError(f"{strategy.name} asked more than {budget} questions")
    estimate = strategy.state(graph, answers) if strategy.state else None
    return strategy.locate(graph, answers), estimate, len(answers)


def evaluate(
    *,
    runs: int,
    budgets: Sequence[int],
    seed: int = 20261111,
    params: BKTParams | None = None,
    shapes: dict[str, Graph] | None = None,
) -> list[dict[str, object]]:
    params = params or DEFAULT_PARAMS["mcq"]
    rows: list[dict[str, object]] = []
    for shape, graph in (shapes or SHAPES).items():
        for model in ("single_gap", "any_state"):
            for budget in budgets:
                for strategy in STRATEGIES:
                    rng = random.Random(f"{seed}-{shape}-{model}-{budget}")  # same learners
                    truths = learners(graph, model, runs, rng)
                    gap_hits = state_hits = asked = 0
                    for known in truths:
                        located, estimate, n = simulate(graph, strategy, known, budget, rng, params)
                        gap_hits += located == true_gap(graph, known)
                        state_hits += estimate == known
                        asked += n
                    g, s = rate(gap_hits, runs), rate(state_hits, runs)
                    rows.append(
                        {
                            "shape": shape,
                            "concepts": len(graph),
                            "learner": model,
                            "budget": budget,
                            "strategy": strategy.name,
                            "runs": runs,
                            "gap_exact": round(gap_hits / runs, 4),
                            "gap_exact_ci95": [round(g.low or 0.0, 4), round(g.high or 0.0, 4)],
                            "state_exact": round(state_hits / runs, 4),
                            "state_exact_ci95": [round(s.low or 0.0, 4), round(s.high or 0.0, 4)],
                            "mean_questions": round(asked / runs, 2),
                        }
                    )
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--runs", type=int, default=2000)
    parser.add_argument("--budgets", type=int, nargs="+", default=[6, 10, 15, 20, 30])
    parser.add_argument("--seed", type=int, default=20261111)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    mcq = DEFAULT_PARAMS["mcq"]
    report = {
        "seed": args.seed,
        "runs_per_cell": args.runs,
        "slip": mcq.p_slip,
        "guess": mcq.p_guess,
        "rows": evaluate(runs=args.runs, budgets=args.budgets, seed=args.seed),
    }
    text = json.dumps(report, ensure_ascii=False, indent=1) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
