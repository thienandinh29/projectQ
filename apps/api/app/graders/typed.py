"""Grading of typed answers (specs/vocabulary): exact after normalisation, never fuzzy.

A misspelled word is a wrong answer (IELTS marks spelling). Variants that are really correct, such
as colour/color or an inflected form, are listed by the author in `accepted`; they are never
guessed here.

`normalise` is deliberately the minimal baseline. Extending it is the owner's task
(specs/vocabulary/tasks.md): decide, and write a test for, each of curly vs straight apostrophes,
hyphen vs space vs joined compounds, trailing punctuation, a typed leading article, and stray
punctuation, while keeping "a misspelling is wrong".
"""

import unicodedata
from collections.abc import Iterable


def normalise(text: str) -> str:
    """Unicode NFC, case folded, outer space removed, inner whitespace collapsed to one space."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def grade_typed(answer: str, accepted: Iterable[str]) -> bool:
    """True when the normalised answer equals a normalised accepted answer. Empty is wrong."""
    given = normalise(answer)
    return bool(given) and any(given == normalise(a) for a in accepted)
