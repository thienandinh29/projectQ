"""Retrieval evaluation: does the right textbook passage come back for a Vietnamese question?

An eval set (`data/eval/<topic>.yaml`, see `data/eval/README.md`) lists questions and, for each, the
passage(s) a human judged to answer it. `run` sends every question through a search function and
scores the ranked results; `Report` carries the numbers the H8 reranker decision needs.

Passages are identified by `source_uri` and/or a text snippet, never by chunk id: ids are random
and change on every re-index, URIs and text do not.

Scoring is pure. Only `run` and the CLI touch a retriever, and `run` accepts any search function,
so the same set scores plain retrieval, a reranker, or another embedding model.

    uv run python -m app.rag.evaluate ../../data/eval/<topic>.yaml --min-hit-rate 0.8
"""

import argparse
import asyncio
import json
import os
import sys
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import yaml  # type: ignore[import-untyped]  # no stubs; avoids a new dev dependency
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas import Citation

DEFAULT_KS = (1, 3, 5, 10)
GATE_K = 5  # the spec's success criterion is measured at k = 5

SearchFn = Callable[[str, str, int], Awaitable[list[Citation]]]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


class Relevant(_Strict):
    """One acceptable passage. Give `source_uri`, `contains`, or both (both must match)."""

    source_uri: str | None = None
    contains: str | None = Field(default=None, min_length=3)  # a snippet of the passage text

    @model_validator(mode="after")
    def _needs_a_criterion(self) -> Self:
        if self.source_uri is None and self.contains is None:
            raise ValueError("a relevant passage needs source_uri, contains, or both")
        return self

    def matches(self, hit: Citation) -> bool:
        if self.source_uri is not None and hit.source_uri != self.source_uri:
            return False
        return self.contains is None or _norm(self.contains) in _norm(hit.content)


class EvalQuestion(_Strict):
    id: str = Field(min_length=1)
    question_vi: str = Field(min_length=1)
    relevant: list[Relevant] = Field(min_length=1)  # every passage that answers it
    note: str | None = None


class EvalSet(_Strict):
    subject: str  # the subject slug the retriever searches
    questions: list[EvalQuestion] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        ids = [q.id for q in self.questions]
        if len(set(ids)) != len(ids):
            raise ValueError("question ids must be unique")
        return self


def load_eval_set(path: Path) -> EvalSet:
    return EvalSet.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class QuestionResult:
    id: str
    question_vi: str
    ranks: tuple[int | None, ...]  # per relevant passage: 1-based rank of its first match, or None
    top: tuple[
        tuple[str, float], ...
    ]  # (source_uri, score) of the best hits, for diagnosing misses

    @property
    def first_rank(self) -> int | None:
        found = [r for r in self.ranks if r is not None]
        return min(found) if found else None

    def hit(self, k: int) -> bool:
        return self.first_rank is not None and self.first_rank <= k

    def recall(self, k: int) -> float:
        return sum(r is not None and r <= k for r in self.ranks) / len(self.ranks)


def score_question(question: EvalQuestion, hits: Sequence[Citation]) -> QuestionResult:
    ranks: list[int | None] = []
    for relevant in question.relevant:
        rank = next((i for i, h in enumerate(hits, start=1) if relevant.matches(h)), None)
        ranks.append(rank)
    top = tuple((h.source_uri, round(h.score, 4)) for h in hits[:3])
    return QuestionResult(question.id, question.question_vi, tuple(ranks), top)


@dataclass(frozen=True)
class Report:
    subject: str
    ks: tuple[int, ...]
    results: tuple[QuestionResult, ...]

    @property
    def n(self) -> int:
        return len(self.results)

    def hit_rate(self, k: int) -> float:
        """Share of questions with at least one relevant passage in the top k."""
        return sum(r.hit(k) for r in self.results) / self.n

    def recall(self, k: int) -> float:
        """Average share of each question's relevant passages found in the top k."""
        return sum(r.recall(k) for r in self.results) / self.n

    def mrr(self) -> float:
        """Mean reciprocal rank of the first relevant passage (0 when it is not retrieved)."""
        return sum(1 / r.first_rank for r in self.results if r.first_rank) / self.n

    def misses(self, k: int) -> list[QuestionResult]:
        return [r for r in self.results if not r.hit(k)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "n": self.n,
            "mrr": self.mrr(),
            "at_k": {
                str(k): {"hit_rate": self.hit_rate(k), "recall": self.recall(k)} for k in self.ks
            },
            "misses_at_gate": [r.id for r in self.misses(GATE_K)],
        }


async def run(eval_set: EvalSet, search: SearchFn, ks: Sequence[int] = DEFAULT_KS) -> Report:
    """Score `search` on every question; one search per question at the largest k."""
    ks = tuple(sorted(set(ks)))
    if not ks or ks[0] < 1:
        raise ValueError("ks must be positive integers")
    results = []
    for q in eval_set.questions:
        hits = await search(q.question_vi, eval_set.subject, ks[-1])
        results.append(score_question(q, hits))
    return Report(eval_set.subject, ks, tuple(results))


def format_report(report: Report) -> str:
    lines = [f"Retrieval on «{report.subject}»: {report.n} questions", ""]
    lines.append(f"{'k':>4} {'hit rate':>9} {'recall':>8}")
    for k in report.ks:
        lines.append(f"{k:>4} {report.hit_rate(k):>9.1%} {report.recall(k):>8.1%}")
    lines.append(f"MRR {report.mrr():.3f}")
    if report.n < 20:
        lines.append(
            f"(only {report.n} questions: one question moves hit rate by {1 / report.n:.1%})"
        )
    gate = report.ks[-1] if GATE_K not in report.ks else GATE_K
    missed = report.misses(gate)
    if missed:
        lines += ["", f"Not found in the top {gate}:"]
        for r in missed:
            seen = ", ".join(f"{uri} ({score})" for uri, score in r.top) or "nothing returned"
            where = "" if r.first_rank is None else f" [found at rank {r.first_rank}]"
            lines.append(f"  {r.id}{where}: {r.question_vi}\n      top: {seen}")
    return "\n".join(lines)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate retrieval on a labelled question set.")
    p.add_argument("eval_file", type=Path)
    p.add_argument("--ks", default=",".join(map(str, DEFAULT_KS)), help="comma-separated k values")
    p.add_argument("--min-hit-rate", type=float, help=f"exit 1 if hit rate at k={GATE_K} is lower")
    p.add_argument("--json", type=Path, dest="json_out", help="also write the numbers here")
    p.add_argument("--embedder", choices=["tei", "local"], default="tei")
    p.add_argument("--tei-url", default=os.environ.get("TEI_URL"))
    p.add_argument("--api-key", default=os.environ.get("TEI_API_KEY"))
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    ks = tuple(int(x) for x in args.ks.split(","))
    eval_set = load_eval_set(args.eval_file)

    # Imported here so scoring (and its tests) never needs a database or the model.
    from app.config import get_settings
    from app.db import create_pool
    from app.rag.embed import AsyncEmbedder, TeiEmbedder, ThreadedEmbedder, make_embedder
    from app.rag.retrieve import Retriever

    built = make_embedder(args.embedder, tei_url=args.tei_url, api_key=args.api_key)
    embedder: AsyncEmbedder = built if isinstance(built, TeiEmbedder) else ThreadedEmbedder(built)
    pool = create_pool(get_settings().database_url)
    try:
        report = asyncio.run(run(eval_set, Retriever(pool, embedder).search, ks))
    finally:
        pool.close()

    print(format_report(report))
    if args.json_out:
        args.json_out.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    gate = args.min_hit_rate
    if gate is not None and GATE_K in ks and report.hit_rate(GATE_K) < gate:
        print(f"\nFAIL: hit rate at k={GATE_K} is below {gate:.0%}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
