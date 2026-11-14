"""LanguageTool client and the match filter (specs/writing/step-2.2.md, point 2).

LanguageTool runs as our own container, so the essay never leaves our machines. The text is
checked twice, in British and American English; a spelling match is kept only when both flag the
same span, so either spelling passes.
"""

from dataclasses import dataclass
from typing import Any

import httpx

KEPT_CATEGORIES = frozenset({"GRAMMAR", "TYPOS", "CASING", "CONFUSED_WORDS", "PUNCTUATION"})
NEVER_MAPPED_CATEGORIES = frozenset({"PUNCTUATION"})


@dataclass(frozen=True)
class Match:
    offset: int
    length: int
    rule_id: str
    category: str
    message: str
    replacements: tuple[str, ...]

    @property
    def end(self) -> int:
        return self.offset + self.length

    @property
    def spelling(self) -> bool:
        return self.category == "TYPOS" and self.rule_id.startswith("MORFOLOGIK_RULE")


def parse_matches(body: dict[str, Any]) -> list[Match]:
    """Matches from a `/v2/check` response; anything malformed raises (the essay then fails)."""
    out = []
    for m in body["matches"]:
        out.append(
            Match(
                offset=int(m["offset"]),
                length=int(m["length"]),
                rule_id=str(m["rule"]["id"]),
                category=str(m["rule"]["category"]["id"]),
                message=str(m["message"]),
                replacements=tuple(str(r["value"]) for r in m.get("replacements", [])),
            )
        )
    return out


def kept_matches(gb: list[Match], us: list[Match]) -> list[Match]:
    """Kept categories; spelling only where both variants flag the same span. By position."""
    us_spelling = {(m.offset, m.length) for m in us if m.spelling}
    kept = [
        m
        for m in gb
        if m.category in KEPT_CATEGORIES and (not m.spelling or (m.offset, m.length) in us_spelling)
    ]
    return sorted(kept, key=lambda m: (m.offset, m.length))


class LanguageToolClient:
    def __init__(self, url: str, *, timeout: float = 30.0) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout

    def check(self, text: str, language: str) -> list[Match]:
        response = httpx.post(
            f"{self.url}/v2/check",
            data={"text": text, "language": language},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return parse_matches(response.json())

    def matches(self, text: str) -> list[Match]:
        return kept_matches(self.check(text, "en-GB"), self.check(text, "en-US"))
