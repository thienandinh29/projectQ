"""Grammar analysis of an essay (specs/writing/step-2.2.md, points 1 and 3 to 6).

LanguageTool's matches (already filtered, `languagetool.kept_matches`) become a **minimal
correction** per sentence; ERRANT types the edits between each sentence and its correction; the
error map turns a type into a hidden node or into nothing. spaCy splits sentences and measures
clauses. Nothing here touches the database or the network.
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from app.writing.analysis import words
from app.writing.error_map import Edit, ErrorMap
from app.writing.languagetool import NEVER_MAPPED_CATEGORIES, Match

CLAUSE_DEPS = frozenset({"advcl", "ccomp", "relcl", "acl", "xcomp", "csubj"})
_TOKEN = re.compile(r"\w+|[^\w\s]")
MINIMAL_SLACK = 2  # tokens a correction may change beyond what its matches cover


class Annotator(Protocol):  # errant.Annotator, typed by what we use
    def parse(self, text: str, tokenise: bool = ...) -> Any: ...
    def annotate(self, orig: Any, cor: Any) -> list[Any]: ...


@dataclass(frozen=True)
class Issue:
    id: int
    sentence: str
    sentence_start: int  # where the sentence starts in the essay
    start: int  # character offsets in the essay
    end: int
    text: str
    suggestion: str | None
    category: str
    rule_id: str
    message_en: str
    errant_type: str | None
    node: str | None
    explain_vi: str | None
    evidence: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Complexity:
    sentences: int
    clauses_per_sentence: float
    complex_sentence_share: float


@dataclass(frozen=True)
class GrammarResult:
    issues: tuple[Issue, ...]
    sentences: tuple[str, ...]
    complexity: Complexity

    def counts(self) -> dict[str, int]:
        return dict(Counter(i.errant_type or "untyped" for i in self.issues))


def token_count(text: str) -> int:
    return len(_TOKEN.findall(text))


def edit_distance(a: Sequence[str], b: Sequence[str]) -> int:
    """Levenshtein distance between two token lists."""
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def apply_matches(
    text: str, start: int, end: int, matches: Sequence[Match]
) -> tuple[str, list[Match]]:
    """text[start:end] with each match's first suggestion applied, left to right, no overlaps."""
    out, cursor, applied = [], start, []
    for m in sorted(matches, key=lambda m: (m.offset, m.length)):
        if not m.replacements or m.offset < cursor or m.end > end:
            continue
        out += [text[cursor : m.offset], m.replacements[0]]
        cursor = m.end
        applied.append(m)
    out.append(text[cursor:end])
    return "".join(out), applied


def is_minimal(original: str, corrected: str, text: str, applied: Sequence[Match]) -> bool:
    """A correction may change only the tokens its matches cover, plus `MINIMAL_SLACK` in all."""
    allowed = sum(token_count(text[m.offset : m.end]) for m in applied)
    return (
        edit_distance(_TOKEN.findall(original), _TOKEN.findall(corrected))
        <= allowed + MINIMAL_SLACK
    )


def _char_span(doc: Any, e: Any) -> tuple[int, int]:
    """The original side of an ERRANT edit as characters in the sentence (insertion: a point)."""
    if e.o_start < e.o_end:
        first, last = doc[e.o_start], doc[e.o_end - 1]
        return first.idx, last.idx + len(last.text)
    pos = doc[e.o_start].idx if e.o_start < len(doc) else len(doc.text)
    return pos, pos


def _overlaps(m: Match, start: int, end: int) -> bool:
    if start == end:  # an insertion: at or inside the match
        return m.offset <= start <= m.end
    return start < m.end and end > m.offset


def complexity(sents: Sequence[Any]) -> Complexity:
    subs = [sum(1 for t in s if t.dep_ in CLAUSE_DEPS) for s in sents]
    n = len(subs)
    return Complexity(
        sentences=n,
        clauses_per_sentence=round(sum(1 + k for k in subs) / n, 2) if n else 0.0,
        complex_sentence_share=round(sum(1 for k in subs if k) / n, 2) if n else 0.0,
    )


def analyse_grammar(
    text: str, matches: Sequence[Match], nlp: Any, annotator: Annotator, error_map: ErrorMap
) -> GrammarResult:
    doc = nlp(text)
    sents = [s for s in doc.sents if words(s.text)]
    issues: list[Issue] = []
    for sent in sents:
        start, end = sent.start_char, sent.end_char
        inside = [m for m in matches if start <= m.offset < end]
        if not inside:
            continue
        original = text[start:end]
        corrected, applied = apply_matches(text, start, end, inside)
        typed: dict[Match, Edit] = {}
        if applied and is_minimal(original, corrected, text, applied):
            o = annotator.parse(original, tokenise=True)
            c = annotator.parse(corrected, tokenise=True)
            for e in annotator.annotate(o, c):
                s, t = _char_span(o, e)
                m = next((m for m in applied if _overlaps(m, start + s, start + t)), None)
                if m is not None and m not in typed:
                    typed[m] = Edit(
                        type=str(e.type),
                        original_lemmas=tuple(tok.lemma_ for tok in e.o_toks),
                        original_tags=tuple(tok.tag_ for tok in e.o_toks),
                        corrected_lemmas=tuple(tok.lemma_ for tok in e.c_toks),
                        corrected_tags=tuple(tok.tag_ for tok in e.c_toks),
                    )
        for m in inside:
            edit = typed.get(m)
            row = error_map.lookup(edit) if edit else None
            mappable = m.category not in NEVER_MAPPED_CATEGORIES
            issues.append(
                Issue(
                    id=len(issues),
                    sentence=original,
                    sentence_start=start,
                    start=m.offset,
                    end=m.end,
                    text=text[m.offset : m.end],
                    suggestion=m.replacements[0] if m.replacements else None,
                    category=m.category,
                    rule_id=m.rule_id,
                    message_en=m.message,
                    errant_type=edit.type if edit else None,
                    node=row.node if row and mappable else None,
                    explain_vi=row.explain_vi if row else None,
                )
            )
    return GrammarResult(tuple(issues), tuple(s.text for s in sents), complexity(sents))


def choose_evidence(issues: Sequence[Issue], limit: int) -> list[Issue]:
    """At most `limit` mapped errors, one per node: most errors first, then the earliest."""
    mapped = [i for i in issues if i.node]
    count = Counter(i.node for i in mapped)
    first: dict[str, Issue] = {}
    for i in sorted(mapped, key=lambda i: i.start):
        first.setdefault(i.node or "", i)
    return sorted(first.values(), key=lambda i: (-count[i.node], i.start))[:limit]
