"""Writing prompts, authored in `data/writing/prompts.yaml` (specs/writing/step-2.1.md)."""

from pathlib import Path
from typing import Literal, Self

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.curriculum.course import Level
from app.curriculum.figures import Ident

PromptType = Literal[
    "opinion", "discussion", "problem-solution", "advantages-disadvantages", "two-part", "chart"
]


class Prompt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Ident
    task: Literal[1, 2]
    type: PromptType
    level: Level
    status: Literal["draft", "reviewed"]
    prompt: str = Field(min_length=20, max_length=1000)


class PromptBank(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    prompts: tuple[Prompt, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [p.id for p in self.prompts]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate prompt id")
        return self

    def get(self, prompt_id: str) -> Prompt | None:
        return next((p for p in self.prompts if p.id == prompt_id), None)


def load_prompts(path: Path) -> PromptBank:
    return PromptBank.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
