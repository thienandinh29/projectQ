"""LLM feedback on the four IELTS criteria, checked by code (specs/writing/step-2.4.md, point 1).

The model explains; it never decides. Every point must quote the essay: a quote that is not an
exact substring (after NFC and whitespace normalisation) is removed, and a point left without a
quote is removed. The model never sees our band; its own criterion bands only feed the
disagreement rule and are never shown.
"""

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.writing.scoring import round_half

CRITERIA = ("tr", "cc", "lr", "gra")
CRITERION_NAMES = {
    "tr": "Task Response",
    "cc": "Coherence and Cohesion",
    "lr": "Lexical Resource",
    "gra": "Grammatical Range and Accuracy",
}
MIN_QUOTE_WORDS = 3
DISAGREEMENT_BANDS = 1.0


class PointOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["strength", "issue"]
    point_vi: str = Field(min_length=10, max_length=600)
    quotes: list[str] = Field(min_length=1, max_length=3)


class CriterionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    band: float = Field(ge=0, le=9)  # the model's judgement: stored for the rule, never shown
    points: list[PointOut] = Field(min_length=1, max_length=3)


class FeedbackOut(BaseModel):
    """What the model must return (validated by the gateway)."""

    model_config = ConfigDict(extra="forbid")
    tr: CriterionOut
    cc: CriterionOut
    lr: CriterionOut
    gra: CriterionOut


SYSTEM = (
    "You are an experienced IELTS Writing teacher giving feedback to a Vietnamese learner on a "
    "Task 2 essay. Write every point in Vietnamese, simply and kindly, and be specific. For each "
    "of the four criteria (tr = Task Response, cc = Coherence and Cohesion, lr = Lexical "
    "Resource, gra = Grammatical Range and Accuracy) give 1 to 3 points; each point is a "
    "strength or an issue and must include 1 to 3 quotes copied EXACTLY from the essay, each at "
    "least 3 words long, character for character. Never invent text that is not in the essay. "
    "Also give your band for each criterion (0 to 9 in steps of 0.5). Do not mention any other "
    "score. Return JSON only."
)


def prompt(task_prompt: str, essay: str, measures: dict[str, Any]) -> str:
    """The user message: the task, the essay, and what the tools measured (never the band)."""
    return (
        f"Task 2 question:\n{task_prompt}\n\n"
        f"Measured by tools (for context; do not repeat the numbers):\n"
        f"{json.dumps(measures, ensure_ascii=False)}\n\n"
        f"Essay:\n{essay}"
    )


# Curly quotes typed on phones or by the model count as straight ones.
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_QUOTES)
    return " ".join(text.split())


@dataclass(frozen=True)
class Point:
    kind: str
    point_vi: str
    quotes: tuple[str, ...]


@dataclass(frozen=True)
class Feedback:
    criteria: dict[str, list[Point]]
    bands: dict[str, float]  # the model's own, for the disagreement rule only
    dropped: int  # points removed because no quote was found in the essay
    quotes_checked: int
    quotes_kept: int

    def to_json(self, model: str) -> dict[str, Any]:
        return {
            "criteria": {
                c: [{"kind": p.kind, "point_vi": p.point_vi, "quotes": list(p.quotes)} for p in ps]
                for c, ps in self.criteria.items()
            },
            "dropped": self.dropped,
            "quotes_checked": self.quotes_checked,
            "quotes_kept": self.quotes_kept,
            "model": model,
        }


def verify(essay: str, out: FeedbackOut) -> Feedback:
    """Keep only quotes that are in the essay; drop points left without one."""
    haystack = _norm(essay)
    criteria: dict[str, list[Point]] = {}
    dropped = checked = kept = 0
    for c in CRITERIA:
        points = []
        for p in getattr(out, c).points:
            good = []
            for q in p.quotes:
                checked += 1
                nq = _norm(q).strip(" .,;:")
                if len(re.findall(r"\w+", nq)) >= MIN_QUOTE_WORDS and nq in haystack:
                    good.append(nq)
                    kept += 1
            if good:
                points.append(Point(p.kind, p.point_vi.strip(), tuple(dict.fromkeys(good))))
            else:
                dropped += 1
        criteria[c] = points
    return Feedback(criteria, {c: float(getattr(out, c).band) for c in CRITERIA}, dropped,
                    checked, kept)  # fmt: skip


def overall_band(bands: Sequence[float]) -> float:
    """IELTS Writing overall: the mean of the four criteria to half bands (.25 and .75 go up)."""
    return round_half(sum(bands) / len(bands))


def disagreement(band_low: float, band_high: float, llm_overall: float) -> str | None:
    """A Vietnamese reason when the model's overall is more than a band from the scorer's range."""
    middle = (band_low + band_high) / 2
    if abs(llm_overall - middle) > DISAGREEMENT_BANDS:
        return (
            "Mô hình chấm và phần nhận xét bằng AI đánh giá bài này khác nhau hơn 1 band, "
            "nên chưa đưa ra khoảng band."
        )
    return None
