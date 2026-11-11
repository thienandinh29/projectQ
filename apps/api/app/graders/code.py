"""Grading code exercises: compare what the sandbox reported with the expected values, here.

The runner (`runner/`) executes learner code and returns only the repr of each test call's value,
or the error it raised. This module never runs learner code and never sends expected values to the
sandbox: comparison happens on this side, so printing fake results inside the sandbox cannot pass
a test. Values are compared as Python literals when both sides are literals (so `5.0 == 5.00`,
`{'a': 1, 'b': 2} == {'b': 2, 'a': 1}`), and as text otherwise.
"""

import ast
from dataclasses import dataclass
from typing import Literal

from app.curriculum.course import Objective, TestCase

RunStatus = Literal["ok", "load_error", "timeout", "memory", "output_limit", "crashed"]


@dataclass(frozen=True)
class RunOutcome:
    """What the runner returned for one submission (runner/nodetrail_runner/sandbox.py)."""

    status: RunStatus
    results: tuple[dict[str, str], ...] = ()
    load_error: dict[str, str] | None = None
    output: str = ""
    duration_ms: int = 0


@dataclass(frozen=True)
class TestOutcome:
    call: str
    passed: bool
    expected: str
    actual: str | None  # repr returned by the learner's code, or None when it raised
    error: str | None  # "TypeError: ..." when the call raised


@dataclass(frozen=True)
class CodeGrade:
    status: RunStatus
    score: float  # share of all tests passed, visible and hidden
    correct: bool  # every test passed: what BKT receives
    visible: tuple[TestOutcome, ...]  # shown to the learner
    hidden_passed: int  # only counts are shown for hidden tests
    hidden_total: int
    message_vi: str  # one line for the learner


def same_value(actual: str, expected: str) -> bool:
    try:
        return bool(ast.literal_eval(actual) == ast.literal_eval(expected))
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return actual.strip() == expected.strip()


_STATUS_VI: dict[str, str] = {
    "load_error": "Mã chưa chạy được: kiểm tra lỗi cú pháp hoặc lỗi khi định nghĩa hàm.",
    "timeout": "Mã chạy quá 5 giây và đã bị dừng: kiểm tra vòng lặp có điểm dừng không.",
    "memory": "Mã dùng quá nhiều bộ nhớ và đã bị dừng.",
    "output_limit": "Mã in ra quá nhiều nội dung và đã bị dừng.",
    "crashed": "Lượt chạy bị lỗi ngoài ý muốn; hãy thử lại.",
}


def grade(objective: Objective, outcome: RunOutcome) -> CodeGrade:
    """Grade one run of the objective's tests (in order) against their expected values."""
    tests: tuple[TestCase, ...] = objective.tests
    if not tests:
        raise ValueError(f"objective {objective.id} has no tests")
    if outcome.status != "ok":
        detail = ""
        if outcome.load_error:
            detail = (
                f" ({outcome.load_error.get('error', '')}: {outcome.load_error.get('message', '')})"
            )
        return CodeGrade(
            outcome.status, 0.0, False, (), 0, sum(t.hidden for t in tests),
            _STATUS_VI[outcome.status] + detail,
        )  # fmt: skip
    if len(outcome.results) != len(tests):
        raise ValueError("the runner returned a different number of results than tests sent")
    visible: list[TestOutcome] = []
    passed = hidden_passed = 0
    for test, result in zip(tests, outcome.results, strict=True):
        actual = result.get("repr")
        error = None if actual is not None else f"{result.get('error')}: {result.get('message')}"
        ok = actual is not None and same_value(actual, test.expected)
        passed += ok
        if test.hidden:
            hidden_passed += ok
        else:
            visible.append(TestOutcome(test.call, ok, test.expected, actual, error))
    total = len(tests)
    hidden_total = sum(t.hidden for t in tests)
    correct = passed == total
    if correct:
        message = f"Đúng tất cả {total} kiểm thử."
    else:
        message = f"Đạt {passed}/{total} kiểm thử (ẩn: {hidden_passed}/{hidden_total})."
    return CodeGrade(
        "ok", passed / total, correct, tuple(visible), hidden_passed, hidden_total, message
    )


def run_request(objective: Objective, code: str) -> dict[str, object]:
    """The body sent to the runner: the learner's code and the test calls, never the answers."""
    return {"code": code, "calls": [t.call for t in objective.tests]}
