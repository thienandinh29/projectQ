"""Bayesian placement: a posterior over knowledge states, questions chosen by information gain.

Why: the graph-walk in `placement.py` treats each answer as certain, so one lucky MCQ guess
(probability 0.25) settles a whole branch. Here an answer is evidence, not a verdict.

Model
  - A *knowledge state* is the set of concepts a learner knows. It must be closed under
    prerequisites (knowing X implies knowing what X needs), so states are the order ideals of the
    prerequisite DAG. The prior is uniform over states unless `prior` gives per-concept
    probabilities.
  - An MCQ answer on concept c is correct with probability `1 - slip` if c is in the state and
    `guess` otherwise (the BKT observation model, `bkt.DEFAULT_PARAMS`).
  - The posterior over states follows by Bayes' rule. A concept may be asked again: under noise a
    second answer on the same concept is real evidence.

Which question next: the concept whose answer has the highest expected information gain about the
state (mutual information between the answer and the state). Ties go to the deeper concept, then
slug order, so runs are repeatable.

It stops when the most probable state reaches `confidence`, or at `max_questions`.

Scale: states are enumerated. Past `MAX_STATES` the model falls back to the "single gap" family
(one concept and everything that builds on it is unknown, or nothing is), which has n + 1 states.

Same call shape as `placement.py` (`next_question`, `gap`, `seed_mastery`), pure and traced.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from app.engine.bkt import DEFAULT_PARAMS, BKTParams
from app.engine.graph import Graph
from app.engine.placement import MAX_ALTERNATIVES, Answer
from app.engine.trace import Alternative, DecisionTrace, Evidence, fmt_p, utc_now

MAX_QUESTIONS = 6
CONFIDENCE = 0.9  # stop early once one state is this probable
MAX_STATES = 20_000
# Placement is an estimate, not mastery: seeded values stay clear of the 0.95 mastery threshold
# (and of 0) so later practice, through BKT, is what confirms understanding.
SEED_FLOOR, SEED_CEILING = 0.05, 0.90

State = frozenset[str]  # the concepts the learner knows


@dataclass(frozen=True)
class Belief:
    states: tuple[State, ...]
    probs: tuple[float, ...]  # same order as `states`; sums to 1
    family: str  # "ideals" (every closed state) or "single_gap" (the fallback)

    def best(self) -> tuple[State, float]:
        i = max(range(len(self.probs)), key=lambda k: (self.probs[k], -k))
        return self.states[i], self.probs[i]

    def p_known(self, slug: str) -> float:
        return sum(p for s, p in zip(self.states, self.probs, strict=True) if slug in s)

    def entropy(self) -> float:
        return -sum(p * math.log2(p) for p in self.probs if p > 0)


Shape = tuple[tuple[str, tuple[str, ...]], ...]  # (concept, its prerequisites) in topological order


def _states(graph: Graph) -> tuple[tuple[State, ...], str]:
    return _enumerate(tuple((n, graph.parents[n]) for n in graph.order))


@lru_cache(maxsize=64)
def _enumerate(shape: Shape) -> tuple[tuple[State, ...], str]:
    """Every prerequisite-closed state, or the single-gap family when there are too many."""
    found: list[State] = []

    def extend(i: int, known: frozenset[str]) -> bool:
        if len(found) > MAX_STATES:
            return False
        if i == len(shape):
            found.append(known)
            return True
        n, parents = shape[i]
        if not extend(i + 1, known):
            return False
        if all(p in known for p in parents):
            return extend(i + 1, known | {n})
        return True

    if extend(0, frozenset()) and len(found) <= MAX_STATES:
        return tuple(found), "ideals"
    # Fallback: "everything known" plus, per concept, "this concept and all that needs it unknown".
    everything = frozenset(n for n, _ in shape)
    # needs[n]: n and every concept that (directly or not) requires it. Walking the topological
    # order backwards, each concept's dependants are complete before its prerequisites read them.
    needs: dict[str, set[str]] = {n: {n} for n, _ in shape}
    for n, parents in reversed(shape):
        for p in parents:
            needs[p] |= needs[n]
    single = [everything - needs[n] for n, _ in shape]
    return tuple(dict.fromkeys([everything, *single])), "single_gap"


def _p_correct(state: State, slug: str, params: BKTParams) -> float:
    return 1 - params.p_slip if slug in state else params.p_guess


def belief(
    graph: Graph,
    answers: Sequence[Answer],
    *,
    params: BKTParams | None = None,
    prior: Mapping[str, float] | None = None,
) -> Belief:
    """Posterior over knowledge states after `answers` (every answer counts, repeats included)."""
    params = params or DEFAULT_PARAMS["mcq"]
    states, family = _states(graph)
    for a in answers:
        if a.slug not in graph:
            raise KeyError(f"answer for unknown concept {a.slug!r}")
    logs: list[float] = []
    for state in states:
        log_p = 0.0
        if prior is not None:
            for n in graph.order:
                p = min(max(prior.get(n, 0.5), 1e-6), 1 - 1e-6)
                log_p += math.log(p if n in state else 1 - p)
        for a in answers:
            p = _p_correct(state, a.slug, params)
            log_p += math.log(p if a.correct else 1 - p)
        logs.append(log_p)
    top = max(logs)
    weights = [math.exp(v - top) for v in logs]
    total = sum(weights)
    return Belief(states, tuple(w / total for w in weights), family)


def _h2(p: float) -> float:
    return 0.0 if p <= 0 or p >= 1 else -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def information_gain(b: Belief, slug: str, params: BKTParams) -> float:
    """Expected reduction, in bits, of the uncertainty about the state from one answer on `slug`."""
    p_in = b.p_known(slug)
    p_yes = p_in * (1 - params.p_slip) + (1 - p_in) * params.p_guess
    noise = p_in * _h2(1 - params.p_slip) + (1 - p_in) * _h2(params.p_guess)
    return max(0.0, _h2(p_yes) - noise)


def _frontier(graph: Graph, state: State) -> list[str]:
    """Unknown concepts whose prerequisites are all known: where learning should start."""
    return [n for n in graph.order if n not in state and all(p in state for p in graph.parents[n])]


def gap(
    graph: Graph,
    answers: Sequence[Answer],
    *,
    params: BKTParams | None = None,
    prior: Mapping[str, float] | None = None,
) -> str | None:
    """The most foundational unknown concept in the most probable state, or None if all known."""
    state, _ = belief(graph, answers, params=params, prior=prior).best()
    frontier = _frontier(graph, state)
    if not frontier:
        return None
    return min(frontier, key=lambda n: (graph.depth[n], graph.order.index(n)))


def seed_mastery(
    graph: Graph,
    answers: Sequence[Answer],
    *,
    params: BKTParams | None = None,
    prior: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Starting `p_known` per concept: its posterior probability, kept inside the seed bounds."""
    b = belief(graph, answers, params=params, prior=prior)
    return {n: min(max(b.p_known(n), SEED_FLOOR), SEED_CEILING) for n in graph.order}


def next_question(
    graph: Graph,
    answers: Sequence[Answer],
    *,
    now: datetime | None = None,
    max_questions: int = MAX_QUESTIONS,
    confidence: float = CONFIDENCE,
    params: BKTParams | None = None,
    prior: Mapping[str, float] | None = None,
    max_asks_per_concept: int | Mapping[str, int] | None = None,
) -> tuple[str | None, DecisionTrace]:
    """The concept to ask about next, or None when placement is finished; always with a trace.

    `max_asks_per_concept`: cap on questions per concept: one number for every concept, or a
    mapping (a concept missing from it cannot be asked), or None for no cap. Services pass the
    number of verified items they hold per concept, so a repeat question is always a new item.
    Repeats are what make the posterior robust to a lucky guess: capping at one question per
    concept costs much of the gain (docs/v2/placement-eval.md).
    """
    if len(graph) == 0:
        raise ValueError("cannot place a learner on an empty graph")
    params = params or DEFAULT_PARAMS["mcq"]
    now = now or utc_now()
    b = belief(graph, answers, params=params, prior=prior)
    state, p_state = b.best()
    last = answers[-1] if answers else None
    evidence = Evidence(
        item_id=last.item_id if last else None, correct=last.correct if last else None
    )

    asked: dict[str, int] = {}
    for a in answers:
        asked[a.slug] = asked.get(a.slug, 0) + 1

    def cap(n: str) -> float:
        if max_asks_per_concept is None:
            return math.inf
        if isinstance(max_asks_per_concept, int):
            return max_asks_per_concept
        return max_asks_per_concept.get(n, 0)

    askable = [n for n in graph.order if asked.get(n, 0) < cap(n)]

    if p_state >= confidence or len(answers) >= max_questions or not askable:
        reason = "confident" if p_state >= confidence else "budget" if askable else "exhausted"
        frontier = _frontier(graph, state)
        found = (
            min(frontier, key=lambda n: (graph.depth[n], graph.order.index(n)))
            if frontier
            else None
        )
        slug = found or (last.slug if last else graph.order[-1])
        sure = f"độ tin cậy {fmt_p(p_state)}"
        if found:
            why = f"Lỗ hổng nhiều khả năng nhất ở «{graph.name_vi(found)}» ({sure})"
        else:
            why = f"Nhiều khả năng bạn đã nắm mọi khái niệm trong bản đồ ({sure})"
        if reason == "budget":
            why += f"; đã hỏi đủ {len(answers)} câu nên dừng, kết luận này còn chưa chắc"
        elif reason == "exhausted":
            why += "; đã hỏi hết các khái niệm có thể hỏi, kết luận này còn chưa chắc"
        others = sorted(
            (n for n in graph.order if n != found),
            key=lambda n: (abs(b.p_known(n) - 0.5), graph.order.index(n)),
        )
        return None, DecisionTrace(
            kind="placement_step",
            concept_slug=slug,
            at=now,
            prior=b.p_known(slug),
            posterior=p_state,
            evidence=evidence,
            rule=f"placement.done.{reason}",
            rule_vi=why,
            alternatives=[
                Alternative(
                    concept_slug=n,
                    p_known=b.p_known(n),
                    why_not_vi=f"Xác suất đã biết {fmt_p(b.p_known(n))}",
                )
                for n in others[:MAX_ALTERNATIVES]
            ],
        )

    gains = {n: information_gain(b, n, params) for n in askable}
    ranked = sorted(askable, key=lambda n: (-round(gains[n], 9), -graph.depth[n], n))
    chosen = ranked[0]
    p = b.p_known(chosen)
    why = (
        f"Hỏi «{graph.name_vi(chosen)}» vì câu trả lời ở đây làm rõ nhất bạn đang ở đâu "
        f"(xác suất đã biết hiện tại {fmt_p(p)}, lượng thông tin {fmt_p(gains[chosen])} bit)"
    )
    return chosen, DecisionTrace(
        kind="placement_step",
        concept_slug=chosen,
        at=now,
        prior=p,
        evidence=evidence,
        rule="placement.bayes.ask",
        rule_vi=why,
        alternatives=[
            Alternative(
                concept_slug=n,
                p_known=b.p_known(n),
                why_not_vi=f"Ít thông tin hơn ({fmt_p(gains[n])} bit)",
            )
            for n in ranked[1 : 1 + MAX_ALTERNATIVES]
        ],
    )
