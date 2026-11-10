from datetime import UTC, datetime

import pytest

from app.guardrails.metrics import RUBRIC, HumanLabel, Prediction, evaluate


def label(case_id: str, has_error: bool, *, kind: str = "item") -> HumanLabel:
    return HumanLabel.model_validate(
        {
            "id": case_id,
            "kind": kind,
            "status": "confirmed",
            "reviewer": "test-fixture-only",
            "reviewed_at": datetime(2026, 1, 1, tzinfo=UTC),
            "has_error": has_error,
        }
    )


def test_confusion_matrix_metrics_and_escaped_questions() -> None:
    labels = [label("tp", True), label("fp", False), label("fn", True), label("tn", False)]
    predictions = [
        Prediction(id=k, blocked=blocked, run_id="unit-test", method="mock")
        for k, blocked in [("tp", True), ("fp", True), ("fn", False), ("tn", False)]
    ]
    result = evaluate(labels, predictions, allow_mock=True)
    assert result["counts"] == {
        "cases": 4,
        "confirmed": 4,
        "paired": 4,
        "pending_or_disputed": 0,
        "missing_predictions": 0,
        "unlabelled_predictions": 0,
        "hints_missing_rubric": 0,
        "tp": 1,
        "fp": 1,
        "fn": 1,
        "tn": 1,
    }
    for metric in (
        "content_error_rate",
        "error_precision",
        "error_recall",
        "false_alarm_rate",
        "faulty_item_escape_rate",
        "served_item_error_rate",
    ):
        assert result[metric] == {
            "value": 0.5,
            "numerator": 1 if metric != "content_error_rate" else 2,
            "denominator": 2 if metric != "content_error_rate" else 4,
        }


def test_no_human_labels_means_unknown_quality_not_success() -> None:
    result = evaluate([HumanLabel(id="pending", kind="hint")], [])
    assert result["counts"]["confirmed"] == 0
    assert result["error_precision"]["value"] is None
    assert result["tutor_rubric_pass_rate"]["value"] is None
    assert result["tutor_target"]["met"] is None


def test_missing_predictions_and_disputed_labels_are_explicit() -> None:
    disputed = HumanLabel(id="disputed", kind="item", status="disputed")
    result = evaluate([label("missing", True), disputed], [])
    assert result["counts"]["missing_predictions"] == 1
    assert result["counts"]["pending_or_disputed"] == 1
    assert result["error_recall"]["value"] is None


def test_unreviewed_and_mock_data_cannot_be_presented_as_human_quality() -> None:
    with pytest.raises(ValueError):
        HumanLabel(id="x", kind="item", status="confirmed", has_error=False)
    with pytest.raises(ValueError, match="mock"):
        evaluate([], [Prediction(id="x", blocked=True, run_id="fake", method="mock")])


def test_tutor_target_requires_20_complete_confirmed_rubrics() -> None:
    labels = []
    for i in range(20):
        item = label(str(i), i >= 18, kind="hint")
        item = item.model_copy(update={"tutor_rubric": {k: i < 18 for k in RUBRIC}})
        labels.append(item)
    result = evaluate(labels, [])
    assert result["tutor_rubric_pass_rate"] == {"value": 0.9, "numerator": 18, "denominator": 20}
    assert result["tutor_target"]["met"] is True  # Synthetic unit test, not product quality.
    assert evaluate(labels[:19], [])["tutor_target"]["met"] is None


def test_duplicate_case_id_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        evaluate([label("same", True), label("same", False)], [])
