"""Score offline H8 receipts: python -m app.evalkit.model_metrics receipts.json.

No model calls or prices are inferred. Per-case latency/cost includes retries and
failed calls. An explicit case manifest prevents missing cases being dropped.
"""

import argparse
import json
import math
from dataclasses import asdict
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evalkit.model_checks import CaseReport, EvaluationCase, evaluate
from app.evalkit.stats import Rate, rate

Task = Literal["graph", "items", "hint", "verification"]
MIN_CASES: dict[str, int] = {"graph": 3, "items": 15, "hint": 12, "verification": 20}
LATENCY_SECONDS: dict[str, float] = {"graph": 25, "items": 15, "verification": 10}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Observation(StrictModel):
    case_id: str = Field(min_length=1)
    elapsed_s: float | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    completed: bool = Field(default=True, strict=True)
    expected_bad: bool | None = Field(default=None, strict=True)
    rejected: bool | None = Field(default=None, strict=True)


class Receipt(StrictModel):
    model_id: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    task: Task
    generator_family: str | None = Field(default=None, min_length=1)
    expected_case_ids: list[str] = Field(min_length=1)
    observations: list[Observation] = Field(default_factory=list)
    offline_cases: list[EvaluationCase] = Field(default_factory=list)
    # Explicit hint budget; the plan does not specify one.
    latency_budget_s: float | None = Field(default=None, gt=0)
    planned_cases_per_topic: int | None = Field(default=None, gt=0, strict=True)
    topic_cost_cap_usd: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        expected = set(self.expected_case_ids)
        if len(expected) != len(self.expected_case_ids) or any(not x.strip() for x in expected):
            raise ValueError("manifest case IDs must be nonblank and unique")
        for records in (self.observations, self.offline_cases):
            ids = [r.case_id for r in records]
            if len(set(ids)) != len(ids) or not set(ids) <= expected:
                raise ValueError("receipt case IDs must be unique members of the manifest")
        if any(c.task != self.task for c in self.offline_cases):
            raise ValueError("offline cases must have the receipt task")
        if (
            self.task != "hint"
            and self.latency_budget_s is not None
            and self.latency_budget_s != LATENCY_SECONDS[self.task]
        ):
            raise ValueError("non-hint latency budgets are fixed by the H8 plan")
        return self


class Metric(StrictModel):
    gate: str
    status: Literal["pass", "fail", "missing", "not_applicable"]
    value: float | None = None
    limit: float | None = None
    n: int = 0
    notes: list[str] = Field(default_factory=list)


class MetricReport(StrictModel):
    model_id: str
    task: Task
    missing_case_ids: list[str]
    missing_offline_case_ids: list[str]
    offline_reports: list[CaseReport]
    metrics: list[Metric]
    catch_rate: Rate | None = None
    false_alarm_rate: Rate | None = None
    eligible_for_selection: bool = False


def score(receipt: Receipt) -> MetricReport:
    rows = receipt.observations
    missing = sorted(set(receipt.expected_case_ids) - {r.case_id for r in rows})
    complete = not missing and len(rows) >= MIN_CASES[receipt.task]
    metrics: list[Metric] = []
    catches: Rate | None = None
    alarms: Rate | None = None
    if receipt.task == "verification":
        bad = [r for r in rows if r.expected_bad is True]
        good = [r for r in rows if r.expected_bad is False]
        labelled = all(
            r.completed and r.expected_bad is not None and r.rejected is not None for r in rows
        )
        if receipt.generator_family is None:
            metrics.append(
                Metric(
                    gate="family",
                    status="missing",
                    notes=["Generator family is required for this verifier pair."],
                )
            )
        else:
            same = (
                receipt.model_family.strip().casefold()
                == receipt.generator_family.strip().casefold()
            )
            metrics.append(Metric(gate="family", status="fail" if same else "pass"))
        if complete and len(rows) == 20 and len(bad) == 10 and len(good) == 10 and labelled:
            catches = rate(sum(r.rejected is True for r in bad), len(bad))
            alarms = rate(sum(r.rejected is True for r in good), len(good))
            metrics.append(
                Metric(
                    gate="G5",
                    status="pass" if catches.k >= 9 and alarms.k <= 2 else "fail",
                    n=len(rows),
                    notes=["Requires >=9/10 planted catches and <=2/10 false alarms."],
                )
            )
        else:
            metrics.append(
                Metric(
                    gate="G5",
                    status="missing",
                    n=len(rows),
                    notes=["Need 10 planted and 10 untouched completed verdicts."],
                )
            )
    else:
        metrics.append(Metric(gate="G5", status="not_applicable"))

    budget = receipt.latency_budget_s or LATENCY_SECONDS.get(receipt.task)
    times = sorted(r.elapsed_s for r in rows if r.elapsed_s is not None)
    if not complete or len(times) != len(rows) or budget is None:
        metrics.append(
            Metric(
                gate="G6",
                status="missing",
                n=len(times),
                limit=budget,
                notes=["Need all planned cases, timing and an explicit task budget."],
            )
        )
    else:
        p95 = times[math.ceil(0.95 * len(times)) - 1]
        metrics.append(
            Metric(
                gate="G6",
                status="pass" if p95 <= budget and all(r.completed for r in rows) else "fail",
                value=p95,
                limit=budget,
                n=len(times),
                notes=[
                    "Nearest-rank p95 in seconds including retries; small samples are descriptive."
                ],
            )
        )
    costs = [r.cost_usd for r in rows if r.cost_usd is not None]
    if (
        not complete
        or len(costs) != len(rows)
        or receipt.planned_cases_per_topic is None
        or receipt.topic_cost_cap_usd is None
    ):
        metrics.append(
            Metric(
                gate="G7",
                status="missing",
                n=len(costs),
                notes=["Need all case costs, planned volume and a pre-run USD cap."],
            )
        )
    else:
        projected = _project_cost(receipt)
        assert projected is not None
        metrics.append(
            Metric(
                gate="G7",
                status="pass" if projected <= Fraction(receipt.topic_cost_cap_usd) else "fail",
                value=float(projected),
                limit=float(receipt.topic_cost_cap_usd),
                n=len(costs),
                notes=[
                    "Task contribution only: mean observed case cost x planned cases per topic. "
                    "All task contributions must fit the shared topic cap together."
                ],
            )
        )
    metrics.append(
        Metric(
            gate="selection",
            status="missing",
            notes=["Need human review, G1-G4 evidence, combined topic cost and P1's decision."],
        )
    )
    return MetricReport(
        model_id=receipt.model_id,
        task=receipt.task,
        missing_case_ids=missing,
        missing_offline_case_ids=(
            sorted(set(receipt.expected_case_ids) - {c.case_id for c in receipt.offline_cases})
            if receipt.task != "verification"
            else []
        ),
        offline_reports=[evaluate(c) for c in receipt.offline_cases],
        metrics=metrics,
        catch_rate=catches,
        false_alarm_rate=alarms,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.receipts.read_text(encoding="utf-8"), parse_float=Decimal)
        if not isinstance(payload, list) or not payload:
            raise ValueError("receipts must be a nonempty list")
        receipts = [Receipt.model_validate(row) for row in payload]
        keys = [(r.model_id, r.task, r.generator_family) for r in receipts]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate model/task/generator receipt")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Invalid receipt: {exc}\n")
    reports = [score(r) for r in receipts]
    # Explicitly serialize the dataclass rates, including their sample sizes and intervals.
    output = []
    for report in reports:
        row = report.model_dump()
        for name in ("catch_rate", "false_alarm_rate"):
            value = getattr(report, name)
            row[name] = asdict(value) if value is not None else None
        output.append(row)
    topic = score_topic_cost(receipts)
    print(
        json.dumps(
            {"models": output, "topic_cost": topic.model_dump()},
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )
    failed = any(m.status == "fail" for r in reports for m in r.metrics)
    failed |= any(c.status == "fail" for r in reports for o in r.offline_reports for c in o.checks)
    failed |= topic.status == "fail"
    return 1 if failed else 2


def _project_cost(receipt: Receipt) -> Fraction | None:
    """Exact USD projection; rounding for display never changes the budget decision."""
    rows = receipt.observations
    if (
        len(rows) != len(receipt.expected_case_ids)
        or len(rows) < MIN_CASES[receipt.task]
        or receipt.planned_cases_per_topic is None
        or any(r.cost_usd is None for r in rows)
    ):
        return None
    total = sum((Fraction(r.cost_usd) for r in rows if r.cost_usd is not None), Fraction(0))
    return total * receipt.planned_cases_per_topic / len(rows)


def score_topic_cost(receipts: list[Receipt]) -> Metric:
    """Sum one explicit model per task. Never add alternative candidates together."""
    tasks = [r.task for r in receipts]
    caps = {r.topic_cost_cap_usd for r in receipts}
    if (
        len(set(tasks)) != len(tasks)
        or not {"graph", "items", "verification"} <= set(tasks)
        or len(caps) != 1
        or None in caps
    ):
        return Metric(
            gate="G7-topic",
            status="missing",
            notes=[
                "Need one model per graph/items/verification task, optional hint, and one USD cap."
            ],
        )
    contributions = [_project_cost(r) for r in receipts]
    if any(value is None for value in contributions):
        return Metric(
            gate="G7-topic", status="missing", notes=["Task cost evidence is incomplete."]
        )
    total = sum((value for value in contributions if value is not None), Fraction(0))
    cap = receipts[0].topic_cost_cap_usd
    assert cap is not None
    return Metric(
        gate="G7-topic",
        status="pass" if total <= Fraction(cap) else "fail",
        value=float(total),
        limit=float(cap),
        n=len(contributions),
        notes=[
            "Projected sum for the declared task volumes, including retries/failures. "
            "Only tasks supplied are covered; this does not select models."
        ],
    )


if __name__ == "__main__":
    raise SystemExit(main())
