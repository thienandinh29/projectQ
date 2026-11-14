"""The error map: ERRANT error type -> hidden node (specs/writing/step-2.2.md, point 5)."""

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.curriculum.course import CourseSpec
from app.engine.bkt import DEFAULT_PARAMS, BKTParams


class When(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    corrected_lemma: tuple[str, ...] = ()
    original_lemma: tuple[str, ...] = ()
    corrected_tag: tuple[str, ...] = ()
    original_tag: tuple[str, ...] = ()


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    type: str = Field(pattern=r"^[A-Z]+(:[A-Z]+)?$")
    when: When = When()
    node: str | None
    explain_vi: str = Field(min_length=5)


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    slip: float = Field(ge=0, le=1)
    guess: float = Field(ge=0, le=1)


class Edit(BaseModel):
    """What a row is matched against: an ERRANT edit's type and the tokens on each side."""

    model_config = ConfigDict(frozen=True)
    type: str  # with or without the operation prefix (M:, R:, U:)
    original_lemmas: tuple[str, ...] = ()
    original_tags: tuple[str, ...] = ()
    corrected_lemmas: tuple[str, ...] = ()
    corrected_tags: tuple[str, ...] = ()

    @property
    def base_type(self) -> str:
        head, _, rest = self.type.partition(":")
        return rest if head in {"M", "R", "U"} and rest else self.type


def _any(wanted: Sequence[str], have: Sequence[str]) -> bool:
    return not wanted or any(w in have for w in wanted)


class ErrorMap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    course: str
    status: Literal["draft", "reviewed"]
    observation: Observation
    max_evidence_per_essay: int = Field(ge=0, le=5)
    rows: tuple[Row, ...]

    @model_validator(mode="after")
    def _identifiable(self) -> "ErrorMap":
        self.params()  # refuses slip + guess >= 1
        return self

    def params(self) -> BKTParams:
        """The writing observation model: an error is evidence, never practice (no transit)."""
        return BKTParams(
            p_init=DEFAULT_PARAMS["mcq"].p_init,
            p_transit=0.0,
            p_slip=self.observation.slip,
            p_guess=self.observation.guess,
        )

    def lookup(self, edit: Edit) -> Row | None:
        for row in self.rows:
            w = row.when
            if row.type == edit.base_type and all(
                (
                    _any(w.corrected_lemma, edit.corrected_lemmas),
                    _any(w.original_lemma, edit.original_lemmas),
                    _any(w.corrected_tag, edit.corrected_tags),
                    _any(w.original_tag, edit.original_tags),
                )
            ):
                return row
        return None

    def problems(self, course: CourseSpec) -> list[str]:
        """Rows whose node is not a hidden node of the course (a milestone or an unknown slug)."""
        hidden = {c.slug for c in course.concepts if c.part_of}
        out = []
        if course.slug != self.course:
            out.append(f"error map is for {self.course!r}, not {course.slug!r}")
        out += [
            f"{r.type}: {r.node!r} is not a hidden node of {course.slug}"
            for r in self.rows
            if r.node is not None and r.node not in hidden
        ]
        return out


def load_error_map(path: Path) -> ErrorMap:
    return ErrorMap.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
