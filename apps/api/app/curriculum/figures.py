"""Figures as structured data: what to draw, never a picture an LLM drew.

Each figure is a small, strictly validated spec. A renderer (the web app) draws it; `facts.py`
computes the ground truth from the same data, so the picture and the answer key cannot disagree.
"""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

FigureKind = Literal["chart", "map", "process", "diagram", "function_plot"]

Label = Annotated[str, Field(min_length=1, max_length=80)]
Ident = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$", max_length=40)]


class _Figure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: Label
    alt_vi: str = Field(min_length=10, max_length=600)  # what a screen reader says


# --- chart --------------------------------------------------------------------------------------


class Series(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: Label
    values: tuple[float, ...] = Field(min_length=1)


class ChartFigure(_Figure):
    kind: Literal["chart"] = "chart"
    chart_type: Literal["line", "bar", "pie", "table"]
    categories: tuple[Label, ...] = Field(min_length=1, max_length=40)  # x axis or slices
    series: tuple[Series, ...] = Field(min_length=1, max_length=8)
    unit: str = Field(default="", max_length=20)  # e.g. "%", "triệu người"
    x_label: str = Field(default="", max_length=60)
    y_label: str = Field(default="", max_length=60)

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if len(set(self.categories)) != len(self.categories):
            raise ValueError("categories must be unique")
        if len({s.name for s in self.series}) != len(self.series):
            raise ValueError("series names must be unique")
        for s in self.series:
            if len(s.values) != len(self.categories):
                raise ValueError(
                    f"series {s.name!r} has {len(s.values)} values for "
                    f"{len(self.categories)} categories"
                )
        if self.chart_type == "pie":
            if len(self.series) != 1:
                raise ValueError("a pie chart has exactly one series")
            if any(v < 0 for v in self.series[0].values):
                raise ValueError("pie values cannot be negative")
        return self


# --- map ----------------------------------------------------------------------------------------


class MapFeature(BaseModel):
    """A rectangle on a grid; (x, y) is the top-left cell."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Ident  # the same id before and after means the same feature
    label: Label
    type: Literal["building", "road", "park", "water", "farmland", "car_park", "other"]
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1)
    h: int = Field(ge=1)


class MapFigure(_Figure):
    kind: Literal["map"] = "map"
    width: int = Field(ge=4, le=40)
    height: int = Field(ge=4, le=40)
    before_label: Label = "Trước"
    after_label: Label = "Sau"
    before: tuple[MapFeature, ...] = Field(min_length=1, max_length=30)
    after: tuple[MapFeature, ...] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def _inside_and_unique(self) -> Self:
        for scene, features in (("before", self.before), ("after", self.after)):
            ids = [f.id for f in features]
            if len(set(ids)) != len(ids):
                raise ValueError(f"duplicate feature id in {scene}")
            for f in features:
                if f.x + f.w > self.width or f.y + f.h > self.height:
                    raise ValueError(f"feature {f.id!r} in {scene} lies outside the grid")
        return self


# --- process and diagram ------------------------------------------------------------------------


class ProcessFigure(_Figure):
    kind: Literal["process"] = "process"
    steps: tuple[Label, ...] = Field(min_length=2, max_length=20)
    cyclic: bool = False  # the last step leads back to the first (e.g. the water cycle)


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Ident
    label: Label


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: Ident
    target: Ident
    label: str = Field(default="", max_length=40)


class DiagramFigure(_Figure):
    kind: Literal["diagram"] = "diagram"
    nodes: tuple[Node, ...] = Field(min_length=1, max_length=40)
    edges: tuple[Edge, ...] = Field(default=(), max_length=80)
    directed: bool = True

    @model_validator(mode="after")
    def _edges_reference_nodes(self) -> Self:
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate node id")
        known = set(ids)
        for e in self.edges:
            if e.source not in known or e.target not in known:
                raise ValueError(f"edge {e.source}->{e.target} references a missing node")
        return self


# --- function plot ------------------------------------------------------------------------------

# A deliberately small expression language: x, numbers, + - * / ^, parentheses and a few named
# functions. It is never passed to eval(); sampling it needs a symbolic-maths parser (next spec).
_ALLOWED_NAMES = {"x", "sin", "cos", "tan", "exp", "log", "sqrt", "abs", "pi", "e"}
_TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d+)?)|([a-z]+)|([-+*/^(),]))")


class FunctionPlotFigure(_Figure):
    kind: Literal["function_plot"] = "function_plot"
    expressions: tuple[Annotated[str, Field(min_length=1, max_length=120)], ...] = Field(
        min_length=1, max_length=4
    )
    x_min: float
    x_max: float
    y_min: float | None = None
    y_max: float | None = None

    @model_validator(mode="after")
    def _safe(self) -> Self:
        if not self.x_min < self.x_max:
            raise ValueError("x_min must be below x_max")
        if self.y_min is not None and self.y_max is not None and not self.y_min < self.y_max:
            raise ValueError("y_min must be below y_max")
        for expr in self.expressions:
            check_expression(expr)
        return self


def check_expression(expr: str) -> None:
    """Refuse anything outside the small expression language (no attributes, no other names)."""
    pos, depth = 0, 0
    while pos < len(expr):
        if expr[pos:].strip() == "":
            break
        m = _TOKEN.match(expr, pos)
        if m is None:
            raise ValueError(f"unsupported character in expression {expr!r} at {pos}")
        name, symbol = m.group(2), m.group(3)
        if name is not None and name not in _ALLOWED_NAMES:
            raise ValueError(f"unknown name {name!r} in expression {expr!r}")
        if symbol == "(":
            depth += 1
        elif symbol == ")":
            depth -= 1
            if depth < 0:
                raise ValueError(f"unbalanced parentheses in {expr!r}")
        pos = m.end()
    if depth != 0:
        raise ValueError(f"unbalanced parentheses in {expr!r}")


Figure = Annotated[
    ChartFigure | MapFigure | ProcessFigure | DiagramFigure | FunctionPlotFigure,
    Field(discriminator="kind"),
]
