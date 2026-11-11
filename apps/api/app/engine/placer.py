"""One interface over the two placement strategies, so services do not depend on either.

- `walk`  — `placement.py`: graph walk with certain inference and a verification re-check.
- `bayes` — `placement_bayes.py`: posterior over knowledge states, questions by information gain.

Services ask at most one question per concept (they serve one unseen verified item per concept),
so the Bayesian placer runs with `max_asks_per_concept=1`. Accuracy for both, measured in
simulation with that cap, is in docs/v2/placement-eval.md.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from app.engine import placement, placement_bayes
from app.engine.graph import Graph
from app.engine.placement import Answer
from app.engine.trace import DecisionTrace

Strategy = Literal["walk", "bayes"]


class Placer(Protocol):
    def next_question(
        self, graph: Graph, answers: Sequence[Answer], *, now: datetime | None = None
    ) -> tuple[str | None, DecisionTrace]: ...

    def gap(self, graph: Graph, answers: Sequence[Answer]) -> str | None: ...

    def seed_mastery(self, graph: Graph, answers: Sequence[Answer]) -> dict[str, float]: ...


@dataclass(frozen=True)
class WalkPlacer:
    def next_question(
        self, graph: Graph, answers: Sequence[Answer], *, now: datetime | None = None
    ) -> tuple[str | None, DecisionTrace]:
        return placement.next_question(graph, answers, now=now)

    def gap(self, graph: Graph, answers: Sequence[Answer]) -> str | None:
        return placement.gap(graph, answers)

    def seed_mastery(self, graph: Graph, answers: Sequence[Answer]) -> dict[str, float]:
        return placement.seed_mastery(graph, answers)


@dataclass(frozen=True)
class BayesPlacer:
    max_asks_per_concept: int | None = 1

    def next_question(
        self, graph: Graph, answers: Sequence[Answer], *, now: datetime | None = None
    ) -> tuple[str | None, DecisionTrace]:
        return placement_bayes.next_question(
            graph, answers, now=now, max_asks_per_concept=self.max_asks_per_concept
        )

    def gap(self, graph: Graph, answers: Sequence[Answer]) -> str | None:
        return placement_bayes.gap(graph, answers)

    def seed_mastery(self, graph: Graph, answers: Sequence[Answer]) -> dict[str, float]:
        return placement_bayes.seed_mastery(graph, answers)


def make_placer(strategy: Strategy) -> Placer:
    if strategy == "bayes":
        return BayesPlacer()
    if strategy == "walk":
        return WalkPlacer()
    raise ValueError(f"unknown placement strategy {strategy!r}")
