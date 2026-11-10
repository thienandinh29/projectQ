"""The learner's next step: what to do when nothing has just gone wrong (`GET /next-item`).

Pure, no DB or LLM. Spec: `specs/next-item/`. Remediation (`remediation.py`) answers "what now,
after a wrong answer"; this answers everything else, in a fixed priority order (first that applies
wins):

  0 resume    a remediation is open and its origin is not mastered
  1 review    a review card is overdue by more than `REVIEW_GRACE`
  2 continue  a *ready* concept is in progress (WEAK <= p < CONFIRM_BELOW): finish what you started
  3 learn     a ready concept is not yet known (p < WEAK): the shallowest, in textbook order
  4 confirm   a ready concept is probably known (CONFIRM_BELOW <= p < MASTERY)
  5 done      everything is mastered

*Ready* = not mastered and every direct prerequisite at least WEAK. The shallowest unmastered
concept always has mastered prerequisites, so while anything is unmastered some concept is ready.

Why `confirm` comes last: placement marks the concepts it found known at 0.85. If those came before
the gap, the learner would be asked again about what placement just showed they know.
"""

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.engine.bkt import MASTERY_THRESHOLD
from app.engine.graph import UNSEEN_P_KNOWN, WEAK_THRESHOLD, Graph
from app.engine.remediation import resume
from app.engine.trace import Alternative, DecisionTrace, Evidence, fmt_p

CONFIRM_BELOW = 0.8  # just under the 0.85 placement gives a concept it found known
# `srs.new_card` is due at once; do not ask straight back about a concept just mastered.
REVIEW_GRACE = timedelta(hours=1)
MAX_ALTERNATIVES = 3
MAX_BLOCKED = 2

StepKind = Literal["resume", "review", "continue", "learn", "confirm", "done"]


@dataclass(frozen=True)
class NextStep:
    concept_slug: str | None  # None when everything is mastered
    kind: StepKind
    target_difficulty: float  # for P3 to pick an item of about this difficulty (0-1)
    reason_vi: str


def target_difficulty(p_known: float) -> float:
    """Harder items nearer mastery: 0.32 for a new concept, 0.74 close to mastered."""
    return round(min(1.0, max(0.0, 0.2 + 0.6 * p_known)), 2)


def next_step(
    graph: Graph,
    mastery: Mapping[str, float],
    *,
    now: datetime,
    resume_origin: str | None = None,
    due_reviews: Mapping[str, datetime] | None = None,
    review_grace: timedelta = REVIEW_GRACE,
    available_concepts: Collection[str] | None = None,
) -> tuple[NextStep, DecisionTrace]:
    """Choose the learner's next concept. `due_reviews` maps a concept to when its card fell due."""
    if len(graph) == 0:
        raise ValueError("cannot plan a path on an empty graph")

    def p(slug: str) -> float:
        return mastery.get(slug, UNSEEN_P_KNOWN)

    def mastered(slug: str) -> bool:
        return p(slug) >= MASTERY_THRESHOLD

    def ready(slug: str) -> bool:
        return (
            available(slug)
            and not mastered(slug)
            and all(p(a) >= WEAK_THRESHOLD for a in graph.parents[slug])
        )

    def available(slug: str) -> bool:
        return available_concepts is None or slug in available_concepts

    # 0. an open remediation comes back to where the learner failed
    if resume_origin is not None:
        if resume_origin not in graph:
            raise KeyError(f"unknown concept {resume_origin!r}")
        if not mastered(resume_origin):
            target, trace = resume(graph, mastery, resume_origin, now=now)
            if available(target):
                step = NextStep(target, "resume", target_difficulty(p(target)), trace.rule_vi)
                return step, trace

    # 1. an overdue review (earliest first); a card due a moment ago is not overdue
    overdue = sorted(
        (due, slug)
        for slug, due in (due_reviews or {}).items()
        if slug in graph and available(slug) and due <= now - review_grace
    )
    if overdue:
        due, slug = overdue[0]
        days = (now - due).total_seconds() / 86400
        late = "hôm nay" if days < 1 else f"{round(days)} ngày trước"
        reason = f"Ôn lại «{graph.name_vi(slug)}»: đã đến hạn ôn ({late}) để không quên"
        return _step(graph, slug, "review", reason, p, [], now, "next_item.review", mastered)

    candidates = [s for s in graph.order if ready(s)]
    in_progress = [s for s in candidates if WEAK_THRESHOLD <= p(s) < CONFIRM_BELOW]
    fresh = [s for s in candidates if p(s) < WEAK_THRESHOLD]
    probable = [s for s in candidates if p(s) >= CONFIRM_BELOW]

    ranked: list[tuple[StepKind, str]] = (
        [("continue", s) for s in sorted(in_progress, key=lambda s: (-p(s), graph.depth[s], s))]
        + [("learn", s) for s in sorted(fresh, key=lambda s: (graph.depth[s], -p(s), s))]
        + [("confirm", s) for s in sorted(probable, key=lambda s: (graph.depth[s], -p(s), s))]
    )

    if not ranked:
        # Everything is mastered (a ready concept always exists while anything is not).
        slug = graph.order[-1]
        reason = "Bạn đã nắm vững toàn bộ lộ trình"
        trace = DecisionTrace(
            kind="next_item",
            concept_slug=slug,
            at=now,
            prior=p(slug),
            evidence=Evidence(),
            rule="next_item.done",
            rule_vi=reason,
        )
        return NextStep(None, "done", target_difficulty(1.0), reason), trace

    kind, slug = ranked[0]
    name = graph.name_vi(slug)
    if kind == "continue":
        reason = (
            f"Tiếp tục «{name}»: bạn đã bắt đầu nắm ({fmt_p(p(slug))}), "
            "hoàn thành trước khi sang phần mới"
        )
    elif kind == "learn":
        base = (
            "đây là khái niệm nền tảng đầu tiên chưa vững"
            if not graph.parents[slug]
            else "các kiến thức nền của nó đã đủ vững"
        )
        reason = f"Học «{name}»: {base} (hiện {fmt_p(p(slug))})"
    else:
        reason = (
            f"Xác nhận «{name}»: bạn có vẻ đã biết ({fmt_p(p(slug))}), "
            "thêm vài câu để chắc chắn đã nắm vững"
        )
    return _step(graph, slug, kind, reason, p, ranked[1:], now, f"next_item.{kind}", mastered)


def _step(
    graph: Graph,
    slug: str,
    kind: StepKind,
    reason: str,
    p: Callable[[str], float],
    others: list[tuple[StepKind, str]],
    now: datetime,
    rule: str,
    mastered: Callable[[str], bool],
) -> tuple[NextStep, DecisionTrace]:
    alternatives = [
        Alternative(concept_slug=s, p_known=p(s), why_not_vi=_why_later(graph, k, s, slug, p))
        for k, s in others[:MAX_ALTERNATIVES]
    ]
    blocked = [
        s
        for s in graph.order
        if not mastered(s) and any(p(a) < WEAK_THRESHOLD for a in graph.parents[s])
    ]
    for s in sorted(blocked, key=lambda s: (graph.depth[s], s))[:MAX_BLOCKED]:
        weakest = min(
            (a for a in graph.parents[s] if p(a) < WEAK_THRESHOLD), key=lambda a: (p(a), a)
        )
        alternatives.append(
            Alternative(
                concept_slug=s,
                p_known=p(s),
                why_not_vi=(
                    f"Chưa học được: kiến thức nền «{graph.name_vi(weakest)}» "
                    f"còn yếu ({fmt_p(p(weakest))})"
                ),
            )
        )
    trace = DecisionTrace(
        kind="next_item",
        concept_slug=slug,
        at=now,
        prior=p(slug),
        evidence=Evidence(),
        rule=rule,
        rule_vi=reason,
        alternatives=alternatives,
    )
    return NextStep(slug, kind, target_difficulty(p(slug)), reason), trace


def _why_later(
    graph: Graph, kind: StepKind, slug: str, chosen: str, p: Callable[[str], float]
) -> str:
    if kind == "continue":
        return f"Cũng đang học dở ({fmt_p(p(slug))}); hoàn thành «{graph.name_vi(chosen)}» trước"
    if kind == "learn":
        return f"Bài mới, để sau «{graph.name_vi(chosen)}» (nền tảng hơn hoặc đang học dở)"
    return f"Có vẻ đã biết ({fmt_p(p(slug))}); xác nhận sau khi học phần chưa vững"
