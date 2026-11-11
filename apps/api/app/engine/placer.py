"""One interface over the two placement strategies, so services do not depend on either.

- `walk`  — `placement.py`: graph walk with certain inference and a verification re-check.
- `bayes` — `placement_bayes.py`: posterior over knowledge states, questions by information gain.

`available` is how many verified items the caller can serve per concept. The Bayesian placer may
ask a concept again (a new item each time), never more often than `available` allows; the walk
asks each concept at most once and ignores it. Accuracy for both, measured in simulation, is in
docs/v2/placement-eval.md.
"""

from collections.abc import Mapping, Sequence
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
        self,
        graph: Graph,
        answers: Sequence[Answer],
        *,
        now: datetime | None = None,
        available: Mapping[str, int] | None = None,
    ) -> tuple[str | None, DecisionTrace]: ...

    def gap(self, graph: Graph, answers: Sequence[Answer]) -> str | None: ...

    def seed_mastery(self, graph: Graph, answers: Sequence[Answer]) -> dict[str, float]: ...


@dataclass(frozen=True)
class WalkPlacer:
    def next_question(
        self,
        graph: Graph,
        answers: Sequence[Answer],
        *,
        now: datetime | None = None,
        available: Mapping[str, int] | None = None,
    ) -> tuple[str | None, DecisionTrace]:
        return placement.next_question(graph, answers, now=now)

    def gap(self, graph: Graph, answers: Sequence[Answer]) -> str | None:
        return placement.gap(graph, answers)

    def seed_mastery(self, graph: Graph, answers: Sequence[Answer]) -> dict[str, float]:
        return placement.seed_mastery(graph, answers)


@dataclass(frozen=True)
class BayesPlacer:
    # Up to 10 questions, stopping early at 90% posterior confidence: in simulation this asks
    # about 6-9 questions on 4-6 concept graphs (docs/v2/placement-eval.md).
    max_questions: int = 10
    confidence: float = placement_bayes.CONFIDENCE

    def next_question(
        self,
        graph: Graph,
        answers: Sequence[Answer],
        *,
        now: datetime | None = None,
        available: Mapping[str, int] | None = None,
    ) -> tuple[str | None, DecisionTrace]:
        return placement_bayes.next_question(
            graph,
            answers,
            now=now,
            max_questions=self.max_questions,
            confidence=self.confidence,
            max_asks_per_concept=available,
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
