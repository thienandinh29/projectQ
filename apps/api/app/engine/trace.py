"""DecisionTrace: why the engine decided what it decided (contract in TEAM.md, "DecisionTrace").

Pure data. The engine returns a trace next to every decision; P2's services store it
(migration 0004), the API returns it, and the web app renders it in the "Vì sao?" panel.
Nothing here touches the DB.
"""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TraceKind = Literal["bkt_update", "placement_step", "root_cause", "next_item", "review"]

Probability = Field(ge=0.0, le=1.0)


class Evidence(BaseModel):
    """What the decision was based on; all optional, since not every kind has an item."""

    model_config = ConfigDict(frozen=True)

    item_id: str | None = None
    correct: bool | None = None
    misconception: str | None = None  # misconception slug of the chosen wrong option
    slip: float | None = Field(default=None, ge=0.0, le=1.0)
    guess: float | None = Field(default=None, ge=0.0, le=1.0)


class Alternative(BaseModel):
    """A candidate the rule considered and did not pick."""

    model_config = ConfigDict(frozen=True)

    concept_slug: str
    p_known: float = Probability
    why_not_vi: str


class DecisionTrace(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: TraceKind
    concept_slug: str
    at: datetime
    # P(L_{t-1}) and P(L_t). None only where p_known is not what the decision is about
    # (e.g. a `review` trace that only reschedules a card).
    prior: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: Evidence = Evidence()
    posterior: float | None = Field(default=None, ge=0.0, le=1.0)
    rule: str  # machine-readable rule id + branch, e.g. "root_cause.lowest_p_known"
    rule_vi: str  # the same explanation in Vietnamese, shown to the learner
    alternatives: list[Alternative] = []


def utc_now() -> datetime:
    """Default clock for traces; engine functions accept `now` so tests stay deterministic."""
    return datetime.now(UTC)


def fmt_p(p: float) -> str:
    """A probability as Vietnamese text: two decimals with a decimal comma (0.31 -> "0,31")."""
    return f"{p:.2f}".replace(".", ",")
