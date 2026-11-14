"""What plain code can measure in an essay (specs/writing/step-2.1.md). Pure functions, no model.

Counting rules: a word is a run of letters, digits, apostrophes or hyphens that contains a letter
or a digit (so "don't", "well-known" and "2025" are one word each); sentences end at ., ! or ?
followed by space or the end; paragraphs are separated by one or more blank lines.
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

TASK_MIN_WORDS = {1: 150, 2: 250}
_WORD = re.compile("[A-Za-z0-9][A-Za-z0-9'\u2019-]*")
_SENTENCE_END = re.compile('(?<=[.!?])["\u201d\u2019)]*\\s+')
_PARAGRAPH = re.compile(r"\n\s*\n")


def words(text: str) -> list[str]:
    return _WORD.findall(text)


def sentences(text: str) -> list[str]:
    flat = " ".join(text.split())
    return [s for s in _SENTENCE_END.split(flat) if words(s)]


def paragraphs(text: str) -> list[str]:
    return [p for p in _PARAGRAPH.split(text.strip()) if words(p)]


def load_linking_words(path: Path) -> dict[str, tuple[str, ...]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {group: tuple(str(w).lower() for w in items) for group, items in raw.items()}


def linking_found(text: str, linking: Mapping[str, Sequence[str]]) -> dict[str, dict[str, int]]:
    """Linking words used, by function, with counts; whole words or phrases, ignoring case."""
    lowered = " ".join(text.lower().replace("\u2019", "'").split())
    found: dict[str, dict[str, int]] = {}
    for group, items in linking.items():
        for item in items:
            n = len(re.findall(rf"(?<![a-z']){re.escape(item)}(?![a-z'])", lowered))
            if n:
                found.setdefault(group, {})[item] = n
    return found


@dataclass(frozen=True)
class Analysis:
    words: int
    sentences: int
    paragraphs: int
    min_words: int
    long_enough: bool
    avg_sentence_words: float
    longest_sentence_words: int
    linking: dict[str, dict[str, int]] = field(default_factory=dict)
    linking_groups_used: int = 0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def analyse(text: str, task: int, linking: Mapping[str, Sequence[str]]) -> Analysis:
    text = unicodedata.normalize("NFC", text)
    lengths = [len(words(s)) for s in sentences(text)]
    n_words = len(words(text))
    found = linking_found(text, linking)
    return Analysis(
        words=n_words,
        sentences=len(lengths),
        paragraphs=len(paragraphs(text)),
        min_words=TASK_MIN_WORDS[task],
        long_enough=n_words >= TASK_MIN_WORDS[task],
        avg_sentence_words=round(sum(lengths) / len(lengths), 1) if lengths else 0.0,
        longest_sentence_words=max(lengths, default=0),
        linking=found,
        linking_groups_used=len(found),
    )
