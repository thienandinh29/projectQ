import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.evalkit.model_checks import EvaluationCase, evaluate, main

URI = "https://example.org/chapter"


def hint(text: str = "Hãy xem lại định nghĩa.", url: str = URI) -> str:
    return json.dumps({"hint_vi": text, "citations": [{"title": "Sách", "url": url}]})


def case(*attempts: str, **kwargs: object) -> EvaluationCase:
    return EvaluationCase.model_validate(
        {
            "case_id": "hint-1",
            "task": "hint",
            "attempts": list(attempts),
            "chunk_ids": ["chunk-1"],
            "source_uris": [URI],
            "correct_option": "Từ nước",
            **kwargs,
        }
    )


def statuses(value: EvaluationCase) -> dict[str, str]:
    return {c.gate: c.status for c in evaluate(value).checks}


def test_retry_records_first_failure_and_success() -> None:
    result = evaluate(case("not json", hint()))
    assert not result.first_try_valid
    assert result.used_attempt == 2
    assert result.checks[0].status == "pass"
    assert not result.eligible_for_selection


def test_valid_first_attempt_cannot_hide_failure_with_retry() -> None:
    result = evaluate(case(hint("Đáp án là TỪ NƯỚC."), hint()))
    assert result.used_attempt == 1
    assert statuses(case(hint("Đáp án là TỪ NƯỚC."), hint()))["G4"] == "fail"


def test_invalid_contracts_and_extra_keys() -> None:
    assert statuses(case("{}", '{"hint_vi": "x"}'))["G1"] == "fail"
    value = json.loads(hint())
    value["answer"] = 1
    assert statuses(case(json.dumps(value)))["G1"] == "fail"


def test_unknown_citation_fails() -> None:
    assert statuses(case(hint(url="https://invented.org")))["G3"] == "fail"


def test_language_checks_do_not_certify_english_as_vietnamese() -> None:
    assert statuses(case(hint("Consider the definition.")))["G2"] == "review"
    assert statuses(case(hint("你好")))["G2"] == "fail"
    assert statuses(case(hint(unicodedata.normalize("NFD", "Hãy thử lại."))))["G2"] == "fail"


def test_leak_boundaries_and_review_requirement() -> None:
    assert statuses(case(hint("Hãy xem số 12."), correct_option="2"))["G4"] == "review"
    assert statuses(case(hint("Kết quả là 2."), correct_option="2"))["G4"] == "fail"
    assert statuses(case(hint(), hint_level=4))["G4"] == "not_applicable"


def test_missing_hint_context_and_retry_limit() -> None:
    with pytest.raises(ValidationError):
        case(hint(), correct_option=None)
    with pytest.raises(ValidationError):
        case(hint(), hint(), hint())


def test_graph_sources_and_cycles() -> None:
    graph = {
        "concepts": [{"slug": "water", "name_vi": "Nước", "name_en": "Water", "sources": [URI]}],
        "edges": [],
    }
    value = case(json.dumps(graph), task="graph", correct_option=None)
    assert statuses(value)["G3"] == "pass"
    graph["edges"] = [{"from": "water", "to": "water"}]
    assert statuses(case(json.dumps(graph), task="graph"))["G1"] == "fail"


def test_item_chunk_membership_and_misconceptions() -> None:
    items: dict[str, Any] = {
        "concept": "water",
        "misconceptions": [{"slug": "wrong", "description_vi": "Nhầm"}],
        "items": [
            {
                "id": "q1",
                "prompt_vi": "Chọn đáp án?",
                "difficulty": 0.5,
                "source": URI,
                "chunk_ids": ["invented"],
                "options": [
                    {"label": "Nước", "correct": True},
                    {"label": "Đất", "correct": False, "misconception": "wrong"},
                ],
            }
        ],
    }
    assert statuses(case(json.dumps(items), task="items"))["G3"] == "fail"
    items["items"][0]["chunk_ids"] = ["chunk-1"]
    assert statuses(case(json.dumps(items), task="items"))["G3"] == "pass"
    items["misconceptions"] = []
    assert statuses(case(json.dumps(items), task="items"))["G1"] == "fail"


@pytest.mark.parametrize("leak,expected", [(False, 2), (True, 1)])
def test_cli_reports_pending_review_or_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    leak: bool,
    expected: int,
) -> None:
    value = case(hint("Từ nước" if leak else "Hãy thử lại."))
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([value.model_dump()]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["model_checks", str(path)])
    assert main() == expected
    assert json.loads(capsys.readouterr().out)[0]["eligible_for_selection"] is False


def test_cli_rejects_duplicate_cases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cases.json"
    value = case(hint()).model_dump()
    path.write_text(json.dumps([value, value]), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["model_checks", str(path)])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
