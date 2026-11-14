"""Candidate sources for a course and the rules for marking one verified (specs/english-course).

A candidate is not fetched until its licence was read on its own page: `verified` needs the date
and the page.
"""

from datetime import date
from pathlib import Path
from typing import Literal, Self

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.curriculum.figures import Ident


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    slug: Ident
    name: str = Field(min_length=1)
    url: HttpUrl
    use: str = Field(min_length=1)
    believed_licence: str = Field(min_length=1)
    status: Literal["to_check", "verified", "rejected"]
    licence: str | None = None  # as read on the licence page, when verified
    checked_on: date | None = None
    licence_page: HttpUrl | None = None
    reason: str | None = None

    @property
    def non_commercial(self) -> bool:
        return self.licence is not None and "NC" in self.licence.upper().replace("-", " ").split()

    @model_validator(mode="after")
    def _status_rules(self) -> Self:
        if self.status == "verified":
            if not (self.licence and self.checked_on and self.licence_page):
                raise ValueError(
                    f"{self.slug}: verified needs licence, checked_on and licence_page"
                )
            words = self.licence.upper().replace("-", " ").split()
            if "ND" in words or "NODERIVATIVES" in words:
                raise ValueError(f"{self.slug}: NoDerivatives licences are never allowed")
        if self.status == "rejected" and not self.reason:
            raise ValueError(f"{self.slug}: rejected needs a reason")
        return self


class Excluded(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class Candidates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidates: tuple[Candidate, ...]
    excluded: tuple[Excluded, ...] = ()

    @model_validator(mode="after")
    def _unique(self) -> Self:
        slugs = [c.slug for c in self.candidates]
        if len(set(slugs)) != len(slugs):
            raise ValueError("duplicate candidate slug")
        return self

    def usable(self) -> tuple[Candidate, ...]:
        return tuple(c for c in self.candidates if c.status == "verified")


def load_candidates(path: Path) -> Candidates:
    return Candidates.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
