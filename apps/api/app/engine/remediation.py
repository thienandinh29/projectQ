"""Remediation rules: what to do after a wrong answer, and where to go once it is fixed.

Pure, no DB or LLM. Built on `graph.root_cause`; the contract's `Remediation` body
(`{concept_slug, reason_vi}`) comes from `RemediationPlan.to_contract()`.

Rules, in order (the first that applies wins):
  1. **A prerequisite is probably not known** (`p_known < WEAK_THRESHOLD`): go back to the weakest
     one (ties: the deeper foundation). Failing that prerequisite in turn descends further, so a
     chain of wrong answers always walks down to the real gap and stops at a root.
  2. **Foundations hold, and the learner has now made the same mistake `REPEATED_MISCONCEPTION`
     times:** drilling more questions is not working, so send them back to the explanation of
     that misconception on this concept.
  3. **Otherwise:** practise the same concept again; no redirect.

`resume` answers the opposite question: once the learner has worked on a prerequisite, where next?
The next weak prerequisite of the original concept, or the original concept itself.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.engine.graph import UNSEEN_P_KNOWN, WEAK_THRESHOLD, Graph, root_cause
from app.engine.trace import DecisionTrace, Evidence, fmt_p
from app.schemas import Remediation

REPEATED_MISCONCEPTION = 2  # the same wrong belief, this many times on one concept

Action = Literal["review_prerequisite", "address_misconception", "practice_again"]


@dataclass(frozen=True)
class RemediationPlan:
    origin_slug: str  # the concept the learner just got wrong
    target_slug: str  # where to send them (the origin itself for the last two actions)
    action: Action
    reason_vi: str
    misconception: str | None  # slug of the wrong belief behind the answer, if the option had one

    def to_contract(self) -> Remediation | None:
        """The API body; None when there is nothing to redirect (practise the same concept)."""
        if self.action == "practice_again":
            return None
        return Remediation(concept_slug=self.target_slug, reason_vi=self.reason_vi)


def remediate(
    graph: Graph,
    mastery: Mapping[str, float],
    failed_slug: str,
    *,
    now: datetime,
    item_id: str | None = None,
    misconception: str | None = None,
    misconception_vi: str | None = None,
    earlier_misconceptions: Sequence[str] = (),
    threshold: float = WEAK_THRESHOLD,
) -> tuple[RemediationPlan, DecisionTrace]:
    """Plan the response to a wrong answer on `failed_slug`.

    `misconception` is the slug of the wrong option's misconception and `misconception_vi` its
    description (shown to the learner). `earlier_misconceptions` are the misconception slugs of this
    learner's *earlier* wrong answers on this concept; this answer is counted on top of them.
    """
    target, trace = root_cause(
        graph,
        mastery,
        failed_slug,
        now=now,
        item_id=item_id,
        misconception=misconception,
        threshold=threshold,
    )
    name = graph.name_vi(failed_slug)
    note = f". Lỗi gặp phải: {misconception_vi.rstrip('.')}" if misconception_vi else ""

    if target != failed_slug:
        action: Action = "review_prerequisite"
        rule = "remediation.review_prerequisite"
        reason = trace.rule_vi + note
    else:
        times = (earlier_misconceptions.count(misconception) + 1) if misconception else 0
        if times >= REPEATED_MISCONCEPTION:
            action = "address_misconception"
            rule = "remediation.repeated_misconception"
            what = f" ({misconception_vi.rstrip('.')})" if misconception_vi else ""
            reason = (
                f"Bạn đã gặp lỗi này {times} lần{what}. Kiến thức nền đã vững, nên hãy đọc lại "
                f"phần giải thích về «{name}» trước khi làm tiếp"
            )
        else:
            action = "practice_again"
            rule = "remediation.practice_again"
            reason = trace.rule_vi + note

    plan = RemediationPlan(failed_slug, target, action, reason, misconception)
    return plan, trace.model_copy(update={"rule": rule, "rule_vi": reason})


def resume(
    graph: Graph,
    mastery: Mapping[str, float],
    origin_slug: str,
    *,
    now: datetime,
    threshold: float = WEAK_THRESHOLD,
) -> tuple[str, DecisionTrace]:
    """Where to go after the learner worked on a prerequisite of `origin_slug`.

    The next weak prerequisite if one is left, else the origin concept itself. Call it only while
    the origin is not yet mastered; once it is, the path moves on instead.
    """
    target, trace = root_cause(graph, mastery, origin_slug, now=now, threshold=threshold)
    origin_name = graph.name_vi(origin_slug)
    if target == origin_slug:
        rule = "remediation.resume_origin"
        reason = f"Kiến thức nền đã vững → quay lại «{origin_name}»"
    else:
        p = mastery.get(target, UNSEEN_P_KNOWN)
        rule = "remediation.resume_next_prerequisite"
        reason = (
            f"Còn kiến thức nền «{graph.name_vi(target)}» chưa vững ({fmt_p(p)}) "
            f"→ củng cố tiếp trước khi quay lại «{origin_name}»"
        )
    # No answer was given, so none of the wrong-answer evidence applies.
    return target, trace.model_copy(
        update={"kind": "next_item", "rule": rule, "rule_vi": reason, "evidence": Evidence()}
    )
