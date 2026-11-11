"""Course specs: which modalities and figure kinds each learning objective uses.

A course is authored (or extracted from a curriculum, then reviewed) as YAML in `data/courses/`.
Generation and grading must stay inside it: `check_figure` refuses a figure kind that the
objective does not allow.
"""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.curriculum.figures import Figure, FigureKind, Ident

Modality = Literal["mcq", "numeric", "code", "short_answer", "essay", "figure_description"]
NEEDS_RUBRIC: frozenset[str] = frozenset({"short_answer", "essay", "figure_description"})


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Ident
    name_vi: str = Field(min_length=1)
    description: str = Field(min_length=1)  # what the judge looks for, in the assessed language
    weight: float = Field(default=1.0, gt=0)


class Rubric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Ident
    scale_max: int = Field(default=9, ge=1, le=100)  # e.g. IELTS bands 0-9
    criteria: tuple[Criterion, ...] = Field(min_length=1)


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    call: str = Field(min_length=1, max_length=500)  # e.g. "is_even(4)"; run only in the sandbox
    expected: str = Field(min_length=1)  # the repr of the expected value
    hidden: bool = False  # never shown to the learner; discourages hard-coding visible answers


class CodeTask(BaseModel):
    """What a code objective needs besides its tests (specs/code-sandbox)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    function: Annotated[str, Field(pattern=r"^[a-z_][a-z0-9_]*$", max_length=40)]
    prompt_vi: str = Field(min_length=1)
    starter: str = Field(min_length=1)  # shown in the editor, e.g. "def is_even(n):\n    ..."
    reference: str = Field(min_length=1)  # must pass every test (self-test)
    wrong: tuple[str, ...] = Field(min_length=1)  # each must fail at least one test (self-test)


class Objective(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Ident
    concept: Ident  # the knowledge-graph concept it belongs to
    text_vi: str = Field(min_length=1)
    modality: Modality
    figures: tuple[FigureKind, ...] = ()
    rubric: Ident | None = None
    tests: tuple[TestCase, ...] = ()
    code: CodeTask | None = None


class CourseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    slug: Ident
    title_vi: str = Field(min_length=1)
    title_en: str = Field(min_length=1)
    language: Literal["vi", "en"] = "vi"  # the language answers are written and judged in
    source: str = Field(min_length=1)  # a catalogue book slug, or "authored"
    modalities: tuple[Modality, ...] = Field(min_length=1)
    figures: tuple[FigureKind, ...] = ()
    rubrics: tuple[Rubric, ...] = ()
    objectives: tuple[Objective, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        rubrics = {r.id for r in self.rubrics}
        if len(rubrics) != len(self.rubrics):
            raise ValueError("duplicate rubric id")
        ids = [o.id for o in self.objectives]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate objective id")
        for o in self.objectives:
            if o.modality not in self.modalities:
                raise ValueError(f"objective {o.id}: modality {o.modality} is not declared")
            extra = set(o.figures) - set(self.figures)
            if extra:
                raise ValueError(f"objective {o.id}: figure kinds {sorted(extra)} not declared")
            if o.modality in NEEDS_RUBRIC:
                if o.rubric is None:
                    raise ValueError(f"objective {o.id}: {o.modality} needs a rubric")
                if o.rubric not in rubrics:
                    raise ValueError(f"objective {o.id}: unknown rubric {o.rubric!r}")
            if o.modality == "code":
                if not o.tests:
                    raise ValueError(f"objective {o.id}: code needs test cases")
                if not any(t.hidden for t in o.tests) or all(t.hidden for t in o.tests):
                    raise ValueError(f"objective {o.id}: code needs visible and hidden tests")
                if o.code is None:
                    raise ValueError(f"objective {o.id}: code needs a CodeTask")
                if not all(o.code.function + "(" in t.call for t in o.tests):
                    raise ValueError(f"objective {o.id}: every test must call {o.code.function}")
            elif o.code is not None:
                raise ValueError(f"objective {o.id}: only code objectives take a CodeTask")
            if o.modality == "figure_description" and not o.figures:
                raise ValueError(f"objective {o.id}: figure_description needs a figure kind")
        return self

    def objective(self, objective_id: str) -> Objective:
        for o in self.objectives:
            if o.id == objective_id:
                return o
        raise KeyError(f"{self.slug}: no objective {objective_id!r}")


def load_course(path: Path) -> CourseSpec:
    return CourseSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


class FigureNotAllowed(ValueError):
    """The objective does not allow this kind of figure."""


def check_figure(course: CourseSpec, objective_id: str, figure: Figure) -> None:
    allowed = course.objective(objective_id).figures
    if figure.kind not in allowed:
        raise FigureNotAllowed(
            f"{course.slug}/{objective_id}: figure kind {figure.kind!r} not allowed "
            f"(allowed: {', '.join(allowed) or 'none'})"
        )
