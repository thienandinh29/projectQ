"""Internal MCQ validation and learner-safe projection; shared API schemas belong to P1."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1)
    correct: bool
    misconception: str | None = None


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["mcq"] = "mcq"
    prompt_vi: str
    difficulty: float = Field(ge=0, le=1)
    source: str
    chunk_ids: list[str] = Field(min_length=1)
    status: Literal["verified", "needs_review"]
    options: list[Option] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_key(self) -> "Item":
        if sum(option.correct for option in self.options) != 1:
            raise ValueError("An MCQ must have exactly one correct option")
        if any(not option.correct and not option.misconception for option in self.options):
            raise ValueError("Every distractor requires a misconception")
        if len({option.label for option in self.options}) != len(self.options):
            raise ValueError("Option labels must be unique")
        return self


class Grade(BaseModel):
    correct: bool
    misconception: str | None


class LearnerOption(BaseModel):
    label: str


class LearnerItem(BaseModel):
    id: str
    kind: Literal["mcq"]
    prompt_vi: str
    options: list[LearnerOption]


def learner_item(item: Item) -> LearnerItem:
    if item.status != "verified":
        raise ValueError("Unverified items cannot be served")
    return LearnerItem(
        id=item.id,
        kind=item.kind,
        prompt_vi=item.prompt_vi,
        options=[LearnerOption(label=o.label) for o in item.options],
    )


def grade(item: Item, option_index: int) -> Grade:
    """Grade the zero-based option index finalized in P1's AttemptCreate contract."""
    if item.status != "verified":
        raise ValueError("Unverified items cannot be graded")
    if (
        not isinstance(option_index, int)
        or isinstance(option_index, bool)
        or not 0 <= option_index < len(item.options)
    ):
        raise ValueError("Invalid answer option")
    option = item.options[option_index]
    return Grade(
        correct=option.correct, misconception=None if option.correct else option.misconception
    )
