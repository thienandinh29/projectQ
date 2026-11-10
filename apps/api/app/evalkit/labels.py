"""The labelled sample behind the guardrail numbers (method: specs/guardrails/).

One record per generated item or tutor hint (or a deliberately broken "planted" one), with what
humans decided about it. The format fails loudly: a record that cannot be scored (a disagreement
nobody resolved, a defect that does not apply to its kind) stops the load, because during the
labelling hour a silent mistake costs far more than an error message.

Defects, by whether the answerability gate is built to catch them ("in scope"):
  item  in scope: key_wrong, not_supported, ambiguous
        out of scope: misconception_mismatch, vietnamese_error, other
  hint  in scope: not_supported, wrong
        out of scope: leaks_answer, not_socratic, vietnamese_error, other
A record is `good` (no defects), `in_scope` bad, or `out_of_scope` bad (only defects the gate was
never meant to catch). Out-of-scope defects are reported, not charged to the gate.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal, Self

import yaml  # type: ignore[import-untyped]  # no stubs; avoids a new dev dependency
from pydantic import BaseModel, ConfigDict, Field, model_validator

Kind = Literal["item", "hint"]
Source = Literal["generated", "planted"]
Defect = Literal[
    "key_wrong",
    "not_supported",
    "ambiguous",
    "wrong",
    "leaks_answer",
    "not_socratic",
    "misconception_mismatch",
    "vietnamese_error",
    "other",
]
Klass = Literal["good", "in_scope", "out_of_scope"]

DEFECTS: dict[Kind, frozenset[str]] = {
    "item": frozenset(
        {
            "key_wrong",
            "not_supported",
            "ambiguous",
            "misconception_mismatch",
            "vietnamese_error",
            "other",
        }
    ),
    "hint": frozenset(
        {"not_supported", "wrong", "leaks_answer", "not_socratic", "vietnamese_error", "other"}
    ),
}
IN_SCOPE: dict[Kind, frozenset[str]] = {
    "item": frozenset({"key_wrong", "not_supported", "ambiguous"}),
    "hint": frozenset({"not_supported", "wrong"}),
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Label(_Strict):
    labeler: str = Field(min_length=1)
    defects: list[Defect] = []  # empty means the labeler found nothing wrong


class Record(_Strict):
    id: str = Field(min_length=1)
    kind: Kind
    source: Source
    topic: str = Field(min_length=1)
    payload: dict[str, Any] = {}  # snapshot of what was labelled; P4 decides its shape
    chunk_ids: list[str] = []  # the chunks the item or hint cites (what the verifier saw)
    # generated: independent labels, blind to the gate's verdict and to the generator model
    labels: list[Label] = []
    # generated: required only when labelers disagree on the class (good / in scope / out of scope)
    resolved_defects: list[Defect] | None = None
    # planted: the one defect put in on purpose; no human label is needed
    planted_defect: Defect | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        allowed = DEFECTS[self.kind]
        every = [d for lab in self.labels for d in lab.defects]
        every += self.resolved_defects or []
        every += [self.planted_defect] if self.planted_defect else []
        for d in every:
            if d not in allowed:
                raise ValueError(f"{self.id}: defect {d!r} does not apply to a {self.kind}")
        if self.source == "planted":
            if self.planted_defect is None:
                raise ValueError(f"{self.id}: a planted record needs planted_defect")
            if self.labels or self.resolved_defects is not None:
                raise ValueError(f"{self.id}: a planted record is labelled by construction")
        else:
            if self.planted_defect is not None:
                raise ValueError(f"{self.id}: only a planted record has planted_defect")
            if not self.labels:
                raise ValueError(f"{self.id}: a generated record needs at least one label")
            if len({lab.labeler for lab in self.labels}) != len(self.labels):
                raise ValueError(f"{self.id}: the same person labelled it twice")
            classes = {classify(self.kind, lab.defects) for lab in self.labels}
            if len(classes) > 1 and self.resolved_defects is None:
                raise ValueError(
                    f"{self.id}: labelers disagree ({sorted(classes)}); add resolved_defects"
                )
            if len(classes) == 1 and self.resolved_defects is not None:
                raise ValueError(f"{self.id}: labelers agree; resolved_defects is not needed")
        return self

    @property
    def final_defects(self) -> frozenset[str]:
        """What counts: the planted defect, the resolution, or the union of agreeing labels."""
        if self.planted_defect:
            return frozenset({self.planted_defect})
        if self.resolved_defects is not None:
            return frozenset(self.resolved_defects)
        return frozenset(d for lab in self.labels for d in lab.defects)

    @property
    def klass(self) -> Klass:
        return classify(self.kind, self.final_defects)


def classify(kind: Kind, defects: Sequence[str] | frozenset[str]) -> Klass:
    if not defects:
        return "good"
    return "in_scope" if any(d in IN_SCOPE[kind] for d in defects) else "out_of_scope"


class RecordSet(_Strict):
    records: list[Record] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [r.id for r in self.records]
        if len(set(ids)) != len(ids):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate record ids: {dup}")
        return self


def load_records(path: Path) -> list[Record]:
    """Read a labelled-sample YAML file (`records:` list); raises on any unscorable record."""
    return RecordSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))).records
