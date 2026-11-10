"""Bayesian Knowledge Tracing (Corbett & Anderson, 1994).

Each learner x concept has p_known = P(the learner has mastered the concept).
After every graded attempt we:
  1. condition on the observation (Bayes' rule with slip/guess noise), then
  2. apply the learning transition (chance the attempt itself taught the skill).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.engine.trace import DecisionTrace, Evidence, fmt_p

ItemKind = Literal["mcq", "code"]

MASTERY_THRESHOLD = 0.95


@dataclass(frozen=True)
class BKTParams:
    p_init: float  # P(known) before any evidence
    p_transit: float  # P(unknown -> known) per practice opportunity
    p_slip: float  # P(wrong | known)
    p_guess: float  # P(right | unknown)

    def __post_init__(self) -> None:
        for name in ("p_init", "p_transit", "p_slip", "p_guess"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")
        # With slip + guess >= 1 a correct answer would be evidence of NOT knowing
        # (the "model degeneracy" problem); refuse such parameters outright.
        if self.p_slip + self.p_guess >= 1.0:
            raise ValueError("p_slip + p_guess must be < 1 for the model to be identifiable")


# Starting values from the BKT literature, before we have data to fit them.
# MCQ guess ~ 1/4 for four options; code items are hard to pass by luck.
DEFAULT_PARAMS: dict[ItemKind, BKTParams] = {
    "mcq": BKTParams(p_init=0.2, p_transit=0.1, p_slip=0.1, p_guess=0.25),
    "code": BKTParams(p_init=0.2, p_transit=0.15, p_slip=0.1, p_guess=0.05),
}


def _check_probability(p_known: float) -> None:
    if not 0.0 <= p_known <= 1.0:
        raise ValueError(f"p_known must be in [0, 1], got {p_known}")


def predict_correct(p_known: float, params: BKTParams) -> float:
    """P(next attempt is correct)."""
    _check_probability(p_known)
    return p_known * (1 - params.p_slip) + (1 - p_known) * params.p_guess


def posterior(p_known: float, correct: bool, params: BKTParams) -> float:
    """P(known | observation), before the learning transition."""
    _check_probability(p_known)
    if correct:
        known = p_known * (1 - params.p_slip)
        unknown = (1 - p_known) * params.p_guess
    else:
        known = p_known * params.p_slip
        unknown = (1 - p_known) * (1 - params.p_guess)
    total = known + unknown
    # total == 0 only for impossible evidence (e.g. p_known=1, slip=0, wrong answer); keep belief.
    return p_known if total == 0 else known / total


def update(p_known: float, correct: bool, params: BKTParams) -> float:
    """New p_known after one graded attempt: evidence, then learning."""
    p = posterior(p_known, correct, params)
    return p + (1 - p) * params.p_transit


def is_mastered(p_known: float, threshold: float = MASTERY_THRESHOLD) -> bool:
    _check_probability(p_known)
    return p_known >= threshold


def update_traced(
    p_known: float,
    correct: bool,
    params: BKTParams,
    *,
    concept_slug: str,
    now: datetime,
    item_id: str | None = None,
    misconception: str | None = None,
) -> tuple[float, DecisionTrace]:
    """`update` plus the trace the "Vì sao?" panel shows. Same number as `update`, always."""
    new_p = update(p_known, correct, params)
    if correct:
        rule = "bkt.correct"
        why = f"Trả lời đúng → khả năng đã nắm vững tăng từ {fmt_p(p_known)} lên {fmt_p(new_p)}"
    else:
        rule = "bkt.wrong"
        why = f"Trả lời sai → khả năng đã nắm vững giảm từ {fmt_p(p_known)} xuống {fmt_p(new_p)}"
        if new_p > p_known:
            # Possible when p_known is tiny: the learning transition outweighs weak evidence.
            why = (
                "Trả lời sai, nhưng mỗi lần luyện tập vẫn giúp học thêm:"
                f" {fmt_p(p_known)} → {fmt_p(new_p)}"
            )
    if is_mastered(new_p) and not is_mastered(p_known):
        rule += ".mastered"
        why += " — đã đạt mức nắm vững"
    why += f" (xác suất trượt {fmt_p(params.p_slip)}, đoán đúng {fmt_p(params.p_guess)})"
    trace = DecisionTrace(
        kind="bkt_update",
        concept_slug=concept_slug,
        at=now,
        prior=p_known,
        evidence=Evidence(
            item_id=item_id,
            correct=correct,
            misconception=None if correct else misconception,
            slip=params.p_slip,
            guess=params.p_guess,
        ),
        posterior=new_p,
        rule=rule,
        rule_vi=why,
    )
    return new_p, trace
