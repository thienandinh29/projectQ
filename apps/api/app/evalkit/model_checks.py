"""Offline H8 checks. No provider calls, model ranking, or semantic certification.

Run: python -m app.evalkit.model_checks cases.json
Input is a JSON list of EvaluationCase objects; output is a JSON list of reports.
Exit 1 means a detected failure, 2 means all automatic checks passed but review is due.
"""

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas import HintResponse, ItemSet, KnowledgeGraph


class EvaluationCase(BaseModel):
    """One model/case pair; attempts contain original output then at most one retry.

    source_uris are exact authorized input URIs (signed URLs included when relevant).
    They are separate from chunk IDs: graph/hint contracts cite URIs, items cite IDs.
    """

    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1)
    task: Literal["graph", "items", "hint"]
    attempts: list[str] = Field(min_length=1, max_length=2)
    chunk_ids: list[str] = Field(min_length=1)
    source_uris: list[str] = Field(min_length=1)
    hint_level: int = Field(default=1, ge=1, le=4)
    correct_option: str | None = None

    @model_validator(mode="after")
    def hint_context(self) -> "EvaluationCase":
        if self.task == "hint" and not (self.correct_option or "").strip():
            raise ValueError("hint cases require the correct option text")
        return self


class Check(BaseModel):
    gate: str
    status: Literal["pass", "fail", "review", "not_applicable"]
    notes: list[str] = Field(default_factory=list)


class CaseReport(BaseModel):
    case_id: str
    first_try_valid: bool
    used_attempt: int
    checks: list[Check]
    eligible_for_selection: bool = False


def _fold(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def evaluate(case: EvaluationCase) -> CaseReport:
    """Use the first contract-valid attempt; only a parse failure allows a retry."""
    schema: type[KnowledgeGraph] | type[ItemSet] | type[HintResponse]
    if case.task == "graph":
        schema = KnowledgeGraph
    elif case.task == "items":
        schema = ItemSet
    else:
        schema = HintResponse
    parsed: KnowledgeGraph | ItemSet | HintResponse | None = None
    errors: list[str] = []
    used = 1
    for used, raw in enumerate(case.attempts, start=1):
        try:
            parsed = schema.model_validate_json(raw)
            break
        except ValueError:
            errors.append(f"attempt {used}: invalid JSON or contract")
    checks = [Check(gate="G1", status="pass" if parsed else "fail", notes=errors)]
    if parsed is None:
        checks.extend(Check(gate=g, status="not_applicable") for g in ("G2", "G3", "G4"))
        return CaseReport(
            case_id=case.case_id, first_try_valid=False, used_attempt=used, checks=checks
        )

    strings: list[str] = []
    unknown: list[str] = []
    if isinstance(parsed, KnowledgeGraph):
        for concept in parsed.concepts:
            strings.extend([concept.name_vi, concept.description_vi])
            unknown.extend(uri for uri in concept.sources if uri not in case.source_uris)
    elif isinstance(parsed, ItemSet):
        strings.extend(m.description_vi for m in parsed.misconceptions)
        for item in parsed.items:
            strings.extend([item.prompt_vi, *(o.label for o in item.options)])
            unknown.extend(cid for cid in item.chunk_ids if cid not in case.chunk_ids)
            if item.source not in case.source_uris:
                unknown.append(item.source)
    else:
        strings.append(parsed.hint_vi)
        unknown.extend(c.url for c in parsed.citations if c.url not in case.source_uris)

    language_errors: list[str] = []
    for index, value in enumerate(strings):
        if not unicodedata.is_normalized("NFC", value):
            language_errors.append(f"string {index}: not NFC")
        if any(c.isalpha() and "LATIN" not in unicodedata.name(c, "") for c in value):
            language_errors.append(
                f"string {index}: non-Latin letter; inspect code/formula context"
            )
    checks.append(
        Check(
            gate="G2",
            status="fail" if language_errors else "review",
            notes=language_errors
            or ["NFC/script checks passed; Vietnamese language/quality needs a rater."],
        )
    )
    checks.append(
        Check(
            gate="G3",
            status="fail" if unknown else "pass",
            notes=[f"unknown input reference: {ref}" for ref in sorted(set(unknown))]
            or ["Input membership only; semantic support and graph chunk attribution need review."],
        )
    )
    if isinstance(parsed, HintResponse) and case.hint_level <= 3:
        answer = _fold(case.correct_option or "")
        # Token boundaries avoid matching '2' in '12'; punctuation/code is literal.
        leaked = bool(re.search(r"(?<!\w)" + re.escape(answer) + r"(?!\w)", _fold(parsed.hint_vi)))
        checks.append(
            Check(
                gate="G4",
                status="fail" if leaked else "review",
                notes=[
                    "Correct option text appears in hint."
                    if leaked
                    else "No literal leak found; paraphrases and option-letter leaks need review."
                ],
            )
        )
    else:
        checks.append(Check(gate="G4", status="not_applicable"))
    return CaseReport(
        case_id=case.case_id,
        first_try_valid=not errors,
        used_attempt=used,
        checks=checks,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path)
    args = parser.parse_args()
    try:
        rows = json.loads(args.cases.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or not rows:
            raise ValueError("cases must be a nonempty JSON list")
        cases = [EvaluationCase.model_validate(row) for row in rows]
        if len({c.case_id for c in cases}) != len(cases):
            raise ValueError("case_id must be unique within a file")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Invalid evaluation input: {exc}\n")
    reports = [evaluate(case) for case in cases]
    print(json.dumps([r.model_dump() for r in reports], ensure_ascii=False, indent=2))
    return 1 if any(c.status == "fail" for r in reports for c in r.checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
