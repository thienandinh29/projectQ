import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.evalkit.model_metrics import MIN_CASES, Receipt, main, score, score_topic_cost


def receipt(task: str = "verification", **changes: Any) -> Receipt:
    count = MIN_CASES[task]
    data = {
        "model_id": f"synthetic-{task}",
        "model_family": "family-b",
        "task": task,
        "generator_family": "family-a" if task == "verification" else None,
        "expected_case_ids": [f"c{i}" for i in range(count)],
        "observations": [
            {
                "case_id": f"c{i}",
                "elapsed_s": 1.0,
                "cost_usd": 0.01,
                "expected_bad": i < 10,
                "rejected": i < 10,
            }
            for i in range(count)
        ],
        "planned_cases_per_topic": 1,
        "topic_cost_cap_usd": 0.025,
        **changes,
    }
    return Receipt.model_validate(data)


def gates(value: Receipt) -> dict[str, Any]:
    return {m.gate: m for m in score(value).metrics}


def test_verifier_threshold_boundaries_and_intervals() -> None:
    value = receipt()
    value.observations[0].rejected = False
    value.observations[10].rejected = True
    value.observations[11].rejected = True
    report = score(value)
    assert gates(value)["G5"].status == "pass"
    assert report.catch_rate is not None and report.catch_rate.k == 9
    assert report.catch_rate.n == 10
    assert report.catch_rate.low is not None and report.catch_rate.low < 0.9
    value.observations[12].rejected = True
    assert gates(value)["G5"].status == "fail"
    value.observations[12].rejected = False
    value.observations[1].rejected = False
    assert gates(value)["G5"].status == "fail"


def test_missing_rows_and_verdicts_cannot_pass() -> None:
    value = receipt()
    value.observations.pop()
    report = score(value)
    assert report.missing_case_ids == ["c19"]
    assert all(gates(value)[g].status == "missing" for g in ("G5", "G6", "G7"))
    value = receipt()
    value.observations[0].rejected = None
    assert gates(value)["G5"].status == "missing"


def test_same_family_and_unknown_family() -> None:
    assert gates(receipt(generator_family=" FAMILY-B "))["family"].status == "fail"
    assert gates(receipt(generator_family=None))["family"].status == "missing"


def test_nearest_rank_p95_includes_all_cases_and_task_budget() -> None:
    value = receipt()
    value.observations[-1].elapsed_s = 100
    assert gates(value)["G6"].value == 1.0  # rank 19 of 20
    value.observations[-2].elapsed_s = 11
    assert gates(value)["G6"].status == "fail"
    value.observations[-2].elapsed_s = 10
    assert gates(value)["G6"].status == "pass"
    value.observations[0].elapsed_s = None
    assert gates(value)["G6"].status == "missing"


def test_failure_is_not_dropped_from_latency_or_cost() -> None:
    value = receipt()
    value.observations[0].completed = False
    value.observations[0].cost_usd = Decimal("1.0")
    assert gates(value)["G6"].status == "fail"
    assert gates(value)["G7"].status == "fail"
    assert gates(value)["G5"].status == "missing"


def test_cost_volume_and_missing_cap_or_measurement() -> None:
    value = receipt(planned_cases_per_topic=3)
    assert gates(value)["G7"].value == pytest.approx(0.03)
    assert gates(value)["G7"].status == "fail"
    assert gates(receipt(topic_cost_cap_usd=None))["G7"].status == "missing"
    value.observations[0].cost_usd = None
    assert gates(value)["G7"].status == "missing"


def test_hint_needs_explicit_latency_budget() -> None:
    assert gates(receipt("hint"))["G6"].status == "missing"
    assert gates(receipt("hint", latency_budget_s=2))["G6"].status == "pass"
    with pytest.raises(ValidationError):
        receipt(latency_budget_s=99)


@pytest.mark.parametrize(
    "field,value",
    [
        ("elapsed_s", -1),
        ("elapsed_s", float("nan")),
        ("cost_usd", float("inf")),
        ("rejected", "false"),
    ],
)
def test_invalid_measurements_rejected(field: str, value: Any) -> None:
    data = receipt().model_dump()
    data["observations"][0][field] = value
    with pytest.raises(ValidationError):
        Receipt.model_validate(data)


def test_manifest_rejects_duplicates_unknown_ids_and_wrong_task() -> None:
    data = receipt().model_dump()
    data["observations"][1]["case_id"] = "c0"
    with pytest.raises(ValidationError):
        Receipt.model_validate(data)
    data["observations"][1]["case_id"] = "not-in-manifest"
    with pytest.raises(ValidationError):
        Receipt.model_validate(data)
    with pytest.raises(ValidationError):
        receipt(expected_case_ids=["c0", "c0"])


def test_small_manifest_does_not_waive_required_sample_count() -> None:
    value = receipt(
        expected_case_ids=["c0"],
        observations=[
            {
                "case_id": "c0",
                "elapsed_s": 1,
                "cost_usd": 0,
                "expected_bad": True,
                "rejected": True,
            }
        ],
    )
    assert gates(value)["G5"].status == "missing"
    assert gates(value)["G6"].status == "missing"


def test_topic_sum_can_fail_when_each_task_fits_and_alternatives_are_not_added() -> None:
    stack = [receipt(task) for task in ("graph", "items", "verification")]
    assert all(gates(r)["G7"].status == "pass" for r in stack)
    assert score_topic_cost(stack).status == "fail"
    assert score_topic_cost(stack).value == pytest.approx(0.03)
    assert score_topic_cost([*stack, receipt("items")]).status == "missing"
    assert score_topic_cost(stack[:2]).status == "missing"
    stack = [receipt(task, topic_cost_cap_usd=0.05) for task in ("graph", "items", "verification")]
    assert score_topic_cost(stack).status == "pass"


def test_cli_keeps_selection_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "receipts.json"
    path.write_text(json.dumps([receipt().model_dump(mode="json")]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["model_metrics", str(path)])
    assert main() == 2
    output = json.loads(capsys.readouterr().out)
    assert not output["models"][0]["eligible_for_selection"]
    assert output["models"][0]["catch_rate"]["n"] == 10


def test_cli_failures_and_invalid_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "receipts.json"
    path.write_text(
        json.dumps([receipt(generator_family="family-b").model_dump(mode="json")]), encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["model_metrics", str(path)])
    assert main() == 1
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1


def test_exact_cost_cap_passes_without_float_rounding() -> None:
    value = receipt("graph", planned_cases_per_topic=3, topic_cost_cap_usd="0.30")
    for row in value.observations:
        row.cost_usd = Decimal("0.10")
    assert gates(value)["G7"].status == "pass"
    value.topic_cost_cap_usd = Decimal("0.299999999999999999")
    assert gates(value)["G7"].status == "fail"
    stack = [
        receipt(task, topic_cost_cap_usd="0.03") for task in ("graph", "items", "verification")
    ]
    assert score_topic_cost(stack).status == "pass"
    for part in stack:
        part.topic_cost_cap_usd = Decimal("0.029999999999999999")
    assert score_topic_cost(stack).status == "fail"


def test_extra_unlabelled_verifier_case_never_passes() -> None:
    data = receipt().model_dump(mode="json")
    data["expected_case_ids"].append("extra")
    data["observations"].append(
        {"case_id": "extra", "elapsed_s": 1, "cost_usd": "0", "rejected": False}
    )
    assert gates(Receipt.model_validate(data))["G5"].status == "missing"


def test_missing_ground_truth_never_passes() -> None:
    value = receipt()
    value.observations[0].expected_bad = None
    assert gates(value)["G5"].status == "missing"
