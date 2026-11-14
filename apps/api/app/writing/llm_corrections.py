"""Corrections the tools missed, proposed by the model and checked by code (step 2.4, point 2).

Only sentences LanguageTool found nothing in are sent. A correction that changes more than
`MAX_TOKEN_EDITS` tokens rewrote the sentence instead of correcting it and is discarded; the rest
are typed by ERRANT and mapped like 2.2's errors, but they are shown as "gợi ý từ AI" and never
move mastery until the owner has checked them.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.writing.error_map import Edit, ErrorMap
from app.writing.grammar import Annotator, Issue, _char_span, edit_distance

MAX_TOKEN_EDITS = 3
MAX_SENTENCES = 60
_TOKEN = re.compile(r"\w+|[^\w\s]")


class Fix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0)
    corrected: str | None = Field(default=None, max_length=1200)  # null: the sentence is fine


class CorrectionsOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fixes: list[Fix] = Field(max_length=MAX_SENTENCES)


SYSTEM = (
    "You correct grammar and word errors in sentences written by an English learner. For each "
    "numbered sentence, return the corrected sentence, changing as few words as possible, or null "
    "if it is already correct. Fix errors only: do not improve style, do not rephrase, do not "
    "change meaning, do not fix punctuation-only issues. Return JSON only."
)


def prompt(sentences: Sequence[str]) -> str:
    numbered = [{"index": i, "sentence": s} for i, s in enumerate(sentences)]
    return "Sentences:\n" + json.dumps(numbered, ensure_ascii=False)


@dataclass(frozen=True)
class Sentence:
    start: int  # character offset in the essay
    text: str


def unflagged(sents: Sequence[Sentence], flagged: Sequence[Issue]) -> list[Sentence]:
    """The sentences without a LanguageTool issue, at most MAX_SENTENCES."""
    hit = {i.sentence_start for i in flagged}
    return [s for s in sents if s.start not in hit][:MAX_SENTENCES]


def corrections(
    sents: Sequence[Sentence],
    out: CorrectionsOut,
    annotator: Annotator,
    error_map: ErrorMap,
    first_id: int,
) -> tuple[list[Issue], int]:
    """Issues from the model's minimal corrections, and how many corrections were discarded."""
    issues: list[Issue] = []
    discarded = 0
    seen: set[int] = set()
    for fix in out.fixes:
        if fix.index >= len(sents) or fix.index in seen or fix.corrected is None:
            continue
        seen.add(fix.index)
        s = sents[fix.index]
        corrected = fix.corrected.strip()
        if corrected == s.text:
            continue
        if edit_distance(_TOKEN.findall(s.text), _TOKEN.findall(corrected)) > MAX_TOKEN_EDITS:
            discarded += 1
            continue
        o = annotator.parse(s.text, tokenise=True)
        c = annotator.parse(corrected, tokenise=True)
        for e in annotator.annotate(o, c):
            a, b = _char_span(o, e)
            edit = Edit(
                type=str(e.type),
                original_lemmas=tuple(t.lemma_ for t in e.o_toks),
                original_tags=tuple(t.tag_ for t in e.o_toks),
                corrected_lemmas=tuple(t.lemma_ for t in e.c_toks),
                corrected_tags=tuple(t.tag_ for t in e.c_toks),
            )
            row = error_map.lookup(edit)
            issues.append(
                Issue(
                    id=first_id + len(issues),
                    sentence=s.text,
                    sentence_start=s.start,
                    start=s.start + a,
                    end=s.start + b,
                    text=s.text[a:b],
                    suggestion=str(e.c_str) or None,
                    category="AI",
                    rule_id="LLM_CORRECTION",
                    message_en="",
                    errant_type=edit.type,
                    node=row.node if row else None,
                    explain_vi=row.explain_vi if row else None,
                    evidence=False,
                    source="llm",
                )
            )
    return issues, discarded


def as_json(issues: Sequence[Issue]) -> list[dict[str, Any]]:
    return [i.to_json() for i in issues]
