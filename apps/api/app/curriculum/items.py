"""Authored grammar items for a course's hidden nodes (specs/level-test).

Loaded next to the course and checked against it: every item practises an existing hidden node, has
exactly one correct option, and names a misconception on every wrong option. `draft` items are
served to the owner only; `reviewed` items to everyone.
"""

import hashlib
import random
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, Self

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.curriculum.course import CourseSpec
from app.curriculum.figures import Ident

Misconception = str


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    text: str = Field(min_length=1, max_length=80)
    correct: bool = False
    misconception: Ident | None = None

    @model_validator(mode="after")
    def _wrong_options_say_why(self) -> Self:
        if self.correct and self.misconception:
            raise ValueError(f"the correct option {self.text!r} cannot have a misconception")
        if not self.correct and not self.misconception:
            raise ValueError(f"the wrong option {self.text!r} needs a misconception")
        return self


class GrammarItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Ident
    node: Ident  # the hidden node it practises
    status: Literal["draft", "reviewed"]
    prompt: str = Field(min_length=5)
    options: tuple[Option, ...] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if self.prompt.count("___") != 1:
            raise ValueError(f"{self.id}: the prompt needs exactly one ___")
        if sum(o.correct for o in self.options) != 1:
            raise ValueError(f"{self.id}: exactly one option must be correct")
        texts = [o.text.casefold() for o in self.options]
        if len(set(texts)) != len(texts):
            raise ValueError(f"{self.id}: options must differ")
        return self

    @property
    def key(self) -> str:
        return next(o.text for o in self.options if o.correct)

    def shuffled(self) -> list[Option]:
        """Options in a fixed order per item, so the key is not always first."""
        rng = random.Random(int.from_bytes(hashlib.sha256(self.id.encode()).digest()[:8], "big"))
        options = list(self.options)
        rng.shuffle(options)
        return options

    def misconception_for(self, answer: str) -> Misconception | None:
        chosen = next((o for o in self.options if o.text == answer), None)
        return chosen.misconception if chosen else None


class ItemBank(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    course: Ident
    items: tuple[GrammarItem, ...] = Field(min_length=1)

    def for_node(self, node: str, *, include_drafts: bool) -> list[GrammarItem]:
        return [
            i for i in self.items if i.node == node and (include_drafts or i.status == "reviewed")
        ]

    def get(self, item_id: str) -> GrammarItem | None:
        return next((i for i in self.items if i.id == item_id), None)


def check_bank(bank: ItemBank, course: CourseSpec) -> list[str]:
    """Problems with the bank against its course (empty when it is consistent)."""
    problems = []
    if bank.course != course.slug:
        problems.append(f"items are for {bank.course}, not {course.slug}")
    hidden = {c.slug for c in course.concepts if c.part_of}
    ids = [i.id for i in bank.items]
    if len(set(ids)) != len(ids):
        problems.append("duplicate item id")
    for item in bank.items:
        if item.node not in hidden:
            problems.append(f"{item.id}: {item.node} is not a hidden node of {course.slug}")
    return problems


def load_items(path: Path, course: CourseSpec) -> ItemBank:
    bank = ItemBank.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    problems = check_bank(bank, course)
    if problems:
        raise ValueError("; ".join(problems))
    return bank


def items_per_milestone(
    bank: ItemBank, course: CourseSpec, *, include_drafts: bool
) -> Mapping[str, int]:
    return {
        m.slug: sum(
            len(bank.for_node(h.slug, include_drafts=include_drafts))
            for h in course.hidden_nodes(m.slug)
        )
        for m in course.milestones()
    }


def round_robin(lists: Sequence[Sequence[str]], size: int) -> list[str]:
    """Up to `size` ids taken one from each list in turn: spreads a test over its hidden nodes."""
    out: list[str] = []
    depth = 0
    while len(out) < size and any(depth < len(xs) for xs in lists):
        out += [xs[depth] for xs in lists if depth < len(xs)][: size - len(out)]
        depth += 1
    return out
