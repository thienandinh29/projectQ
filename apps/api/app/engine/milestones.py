"""Milestones and hidden nodes: test outcomes, what to learn next, the level estimate (specs/level-
test).

Mastery lives on hidden nodes only. A milestone has no probability of its own: it is known when
every hidden node under it is at `ASSUMED_KNOWN` or above, and mastered when every hidden node
passes the mastery gate. Pure functions over plain data (no course files, no database), each
decision with a `DecisionTrace`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.engine import bkt, placement_bayes
from app.engine.graph import UNSEEN_P_KNOWN, Graph
from app.engine.placement import Answer
from app.engine.trace import Alternative, DecisionTrace, Evidence, fmt_p, utc_now

ASSUMED_KNOWN = placement_bayes.SEED_CEILING  # 0.9: known, not mastered
LEVELS = ("A1", "A2", "B1", "B2", "C1")
LEVEL_TEST_MAX_QUESTIONS = 20
LEVEL_TEST_CONFIDENCE = placement_bayes.CONFIDENCE
MIN_TEST_SIZE, MAX_TEST_SIZE = 3, 4

Status = Literal["mastered", "known", "partial", "unknown"]
Result = Literal["pass", "gap", "fail"]


@dataclass(frozen=True)
class Roadmap:
    graph: Graph  # every concept: hidden nodes and milestones, with hidden node -> milestone edges
    milestones: Graph  # milestones only, with the edges between them
    hidden: Mapping[str, tuple[str, ...]]  # milestone -> its hidden nodes, in learning order
    level: Mapping[str, str]  # milestone -> CEFR level

    def milestone_of(self, node: str) -> str:
        return next(m for m, nodes in self.hidden.items() if node in nodes)

    @property
    def hidden_nodes(self) -> frozenset[str]:
        return frozenset(n for nodes in self.hidden.values() for n in nodes)


@dataclass(frozen=True)
class NodeAnswer:
    node: str
    correct: bool
    item_id: str | None = None
    misconception: str | None = None


@dataclass(frozen=True)
class Outcome:
    result: Result
    opened: tuple[str, ...]  # hidden nodes to check quickly and learn
    raised: Mapping[str, float] = field(default_factory=dict)  # hidden node -> new p_known
    trace: DecisionTrace | None = None


def _p(p_known: Mapping[str, float], node: str) -> float:
    return p_known.get(node, UNSEEN_P_KNOWN)


def milestone_status(
    roadmap: Roadmap, p_known: Mapping[str, float], unaided: Mapping[str, int]
) -> dict[str, Status]:
    out: dict[str, Status] = {}
    for m, nodes in roadmap.hidden.items():
        ps = [_p(p_known, n) for n in nodes]
        if all(bkt.is_confirmed_mastery(_p(p_known, n), unaided.get(n, 0)) for n in nodes):
            out[m] = "mastered"
        elif all(p >= ASSUMED_KNOWN for p in ps):
            out[m] = "known"
        elif any(p >= ASSUMED_KNOWN for p in ps):
            out[m] = "partial"  # some parts known: shown as "cần ôn" when it was known before
        else:
            out[m] = "unknown"
    return out


def questions_in_test(hidden_count: int) -> int:
    """Questions in a milestone test: 4 when there are 4 or more parts, else at least 3."""
    return max(MIN_TEST_SIZE, min(MAX_TEST_SIZE, hidden_count))


def milestone_outcome(
    roadmap: Roadmap,
    milestone: str,
    answers: Sequence[NodeAnswer],
    p_known: Mapping[str, float],
    *,
    now: datetime | None = None,
) -> Outcome:
    """Pass, pass with one gap, or fail, from a milestone test's answers (spec points 2-4)."""
    nodes = roadmap.hidden[milestone]
    if not answers:
        raise ValueError("a milestone test needs answers")
    if any(a.node not in nodes for a in answers):
        raise ValueError(f"an answer is not about a part of {milestone}")
    name = roadmap.graph.name_vi(milestone)
    wrong = [a for a in answers if not a.correct]
    right = len(answers) - len(wrong)
    score = f"{right}/{len(answers)}"
    if not wrong:
        result: Result = "pass"
        opened: tuple[str, ...] = ()
        why = f"Đúng {score} câu của cột mốc «{name}»: các phần bên trong được coi là đã biết"
    elif len(wrong) == 1 and len(answers) >= MAX_TEST_SIZE:
        result, opened = "gap", (wrong[0].node,)
        why = (
            f"Đúng {score} câu của cột mốc «{name}»: qua cột mốc, "
            f"nhưng cần ôn «{roadmap.graph.name_vi(wrong[0].node)}»"
        )
    else:
        result, opened = "fail", nodes
        why = f"Đúng {score} câu của cột mốc «{name}»: kiểm tra nhanh từng phần để tìm chỗ hổng"
    raised = (
        {n: ASSUMED_KNOWN for n in nodes if n not in opened and _p(p_known, n) < ASSUMED_KNOWN}
        if result != "fail"
        else {}
    )
    misconceptions = sorted({a.misconception for a in wrong if a.misconception})
    if misconceptions:
        why += f" (lỗi gặp: {', '.join(misconceptions)})"
    trace = DecisionTrace(
        kind="placement_step",
        concept_slug=milestone,
        at=now or utc_now(),
        evidence=Evidence(correct=not wrong),
        rule=f"milestone.{result}",
        rule_vi=why,
    )
    return Outcome(result, opened, raised, trace)


def next_to_learn(
    roadmap: Roadmap,
    opened: Sequence[str],
    p_known: Mapping[str, float],
    *,
    now: datetime | None = None,
) -> tuple[str | None, DecisionTrace | None]:
    """The most foundational weak hidden node: the opened ones or their hidden prerequisites.

    A prerequisite counts only with evidence (a value in `p_known`): untested is not weak, and
    the roadmap's order already asks for earlier milestones first.
    """
    hidden = roadmap.hidden_nodes
    candidates = set(opened) | {
        a for o in opened for a in roadmap.graph.ancestors(o) if a in hidden and a in p_known
    }
    weak = [c for c in candidates if _p(p_known, c) < ASSUMED_KNOWN]
    if not weak:
        return None, None
    order = roadmap.graph.order

    def key(n: str) -> tuple[int, float, int]:
        return roadmap.graph.depth[n], _p(p_known, n), order.index(n)

    chosen = min(weak, key=key)
    others = sorted((n for n in weak if n != chosen), key=key)
    trace = DecisionTrace(
        kind="root_cause",
        concept_slug=chosen,
        at=now or utc_now(),
        prior=_p(p_known, chosen),
        rule="milestone.learn_foundation_first",
        rule_vi=(
            f"Học «{roadmap.graph.name_vi(chosen)}» trước: phần nền tảng nhất còn yếu "
            f"(p_known {fmt_p(_p(p_known, chosen))})"
        ),
        alternatives=[
            Alternative(
                concept_slug=n,
                p_known=_p(p_known, n),
                why_not_vi=f"«{roadmap.graph.name_vi(n)}» dựa trên phần nền tảng hơn",
            )
            for n in others[:3]
        ],
    )
    return chosen, trace


# --- the level test ---------------------------------------------------------------------------


def level_test_next(
    roadmap: Roadmap,
    answers: Sequence[Answer],
    *,
    asks_per_milestone: Mapping[str, int],
    now: datetime | None = None,
) -> tuple[str | None, DecisionTrace]:
    """The milestone to ask about next (Bayesian placement on the milestone graph), or None."""
    return placement_bayes.next_question(
        roadmap.milestones,
        answers,
        now=now,
        max_questions=LEVEL_TEST_MAX_QUESTIONS,
        confidence=LEVEL_TEST_CONFIDENCE,
        max_asks_per_concept=asks_per_milestone,
    )


def known_milestones(roadmap: Roadmap, answers: Sequence[Answer]) -> frozenset[str]:
    """The most probable set of known milestones after the level test."""
    return placement_bayes.belief(roadmap.milestones, answers).best()[0]


def level_from(roadmap: Roadmap, known: frozenset[str] | set[str]) -> str:
    """Highest CEFR level whose milestones, and those of every lower level, are all known."""
    level = "A1"  # below the roadmap's lowest milestones
    for tier in LEVELS:
        at_or_below = [
            m for m, lv in roadmap.level.items() if LEVELS.index(lv) <= LEVELS.index(tier)
        ]
        if not at_or_below:
            continue
        if not all(m in known for m in at_or_below):
            break
        level = tier
    return level


def vocab_level(results: Mapping[str, tuple[int, int]], *, pass_mark: int = 2) -> str:
    """Highest tier from A2 up with at least `pass_mark` correct, stopping at the first miss."""
    level = "A1"
    for tier in LEVELS[1:]:
        right, _asked = results.get(tier, (0, 0))
        if right < pass_mark:
            break
        level = tier
    return level


def seed_from_level_test(roadmap: Roadmap, known: frozenset[str] | set[str]) -> dict[str, float]:
    """Hidden nodes of known milestones start as assumed known; the rest keep the prior."""
    return {n: ASSUMED_KNOWN for m in known for n in roadmap.hidden.get(m, ())}


def up_to(roadmap: Roadmap, level: str) -> Roadmap:
    """The roadmap limited to milestones at or below `level` (a learner's target, e.g. B2)."""
    cut = LEVELS.index(level)
    keep = {m for m, lv in roadmap.level.items() if LEVELS.index(lv) <= cut}
    if not keep:
        raise ValueError(f"no milestones at or below {level}")
    edges = [(p, c) for c in keep for p in roadmap.milestones.parents[c] if p in keep]
    names = {m: roadmap.milestones.name_vi(m) for m in keep}
    return Roadmap(
        graph=roadmap.graph,
        milestones=Graph.from_edges(sorted(keep), edges, names),
        hidden={m: nodes for m, nodes in roadmap.hidden.items() if m in keep},
        level={m: lv for m, lv in roadmap.level.items() if m in keep},
    )
