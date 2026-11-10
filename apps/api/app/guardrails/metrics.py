"""Positive = faulty content that should be blocked. Human labels alone are ground truth."""

from collections.abc import Iterable
from datetime import datetime
from typing import Literal, TypedDict

from pydantic import model_validator

from app.content.models import Record

RUBRIC = (
    "correct",
    "supported",
    "citations_valid",
    "relevant_to_history",
    "clear_vietnamese",
    "no_answer_leak",
)


class HumanLabel(Record):
    id: str
    kind: Literal["item", "hint"]
    status: Literal["pending", "disputed", "confirmed"] = "pending"
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    has_error: bool | None = None
    tutor_rubric: dict[str, bool] | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def confirmed_label(self) -> "HumanLabel":
        if self.status == "confirmed":
            if not self.reviewer or not self.reviewed_at or self.has_error is None:
                raise ValueError("confirmed labels need reviewer, time and has_error")
            if self.reviewed_at.tzinfo is None:
                raise ValueError("review timestamp must be timezone-aware")
        if self.tutor_rubric is not None and set(self.tutor_rubric) != set(RUBRIC):
            raise ValueError("tutor rubric must contain exactly the six rubric criteria")
        return self


class Prediction(Record):
    id: str
    blocked: bool
    run_id: str
    method: Literal["real_model", "structural", "mock"]


class Rate(TypedDict):
    value: float | None
    numerator: int
    denominator: int


class Counts(TypedDict):
    cases: int
    confirmed: int
    paired: int
    pending_or_disputed: int
    missing_predictions: int
    unlabelled_predictions: int
    hints_missing_rubric: int
    tp: int
    fp: int
    fn: int
    tn: int


class TutorTarget(TypedDict):
    required: int
    sample_size: int
    met: bool | None


class MetricReport(TypedDict):
    positive_definition: str
    ground_truth: str
    counts: Counts
    content_error_rate: Rate
    item_error_rate: Rate
    error_precision: Rate
    error_recall: Rate
    false_alarm_rate: Rate
    faulty_item_escape_rate: Rate
    served_item_error_rate: Rate
    tutor_rubric_pass_rate: Rate
    tutor_target: TutorTarget
    prediction_methods: list[str]


def rate(numerator: int, denominator: int) -> Rate:
    return {
        "value": numerator / denominator if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
    }


def _unique[T: HumanLabel | Prediction](rows: Iterable[T]) -> dict[str, T]:
    result: dict[str, T] = {}
    for row in rows:
        if row.id in result:
            raise ValueError(f"duplicate evaluation ID: {row.id}")
        result[row.id] = row
    return result


def evaluate(
    labels: list[HumanLabel], predictions: list[Prediction], *, allow_mock: bool = False
) -> MetricReport:
    labelled = _unique(labels)
    predicted = _unique(predictions)
    if not allow_mock and any(p.method == "mock" for p in predictions):
        raise ValueError("mock predictions are for tests, not quality reports")
    confirmed = {k: v for k, v in labelled.items() if v.status == "confirmed"}
    pairs = [(label, predicted[k]) for k, label in confirmed.items() if k in predicted]
    tp = sum(label.has_error is True and pred.blocked for label, pred in pairs)
    fp = sum(label.has_error is False and pred.blocked for label, pred in pairs)
    fn = sum(label.has_error is True and not pred.blocked for label, pred in pairs)
    tn = sum(label.has_error is False and not pred.blocked for label, pred in pairs)
    items = [label for label in confirmed.values() if label.kind == "item"]
    hints = [
        label
        for label in confirmed.values()
        if label.kind == "hint" and label.tutor_rubric is not None
    ]
    faulty_items_passed = sum(
        label.kind == "item" and label.has_error is True and not pred.blocked
        for label, pred in pairs
    )
    served_items = sum(label.kind == "item" and not pred.blocked for label, pred in pairs)
    faulty_items = sum(label.kind == "item" and label.has_error is True for label, _ in pairs)
    tutor_passed = sum(
        label.has_error is False and all((label.tutor_rubric or {}).values()) for label in hints
    )
    return {
        "positive_definition": "faulty_content_to_block",
        "ground_truth": "confirmed_human_labels_only",
        "counts": {
            "cases": len(labels),
            "confirmed": len(confirmed),
            "paired": len(pairs),
            "pending_or_disputed": len(labels) - len(confirmed),
            "missing_predictions": len(confirmed) - len(pairs),
            "unlabelled_predictions": len(set(predicted) - set(confirmed)),
            "hints_missing_rubric": sum(
                label.kind == "hint" and label.tutor_rubric is None for label in confirmed.values()
            ),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
        },
        "content_error_rate": rate(
            sum(label.has_error is True for label in confirmed.values()), len(confirmed)
        ),
        "item_error_rate": rate(sum(label.has_error is True for label in items), len(items)),
        "error_precision": rate(tp, tp + fp),
        "error_recall": rate(tp, tp + fn),
        "false_alarm_rate": rate(fp, fp + tn),
        "faulty_item_escape_rate": rate(faulty_items_passed, faulty_items),
        "served_item_error_rate": rate(faulty_items_passed, served_items),
        "tutor_rubric_pass_rate": rate(tutor_passed, len(hints)),
        "tutor_target": {
            "required": 18,
            "sample_size": 20,
            "met": tutor_passed >= 18 if len(hints) == 20 else None,
        },
        "prediction_methods": sorted({p.method for p in predictions}),
    }
