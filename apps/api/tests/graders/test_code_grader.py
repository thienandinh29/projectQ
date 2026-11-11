"""Code grading on this side of the sandbox: comparison, hidden tests, statuses, the client."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.curriculum.course import CourseSpec, load_course
from app.graders.code import RunOutcome, grade, run_request, same_value
from app.graders.runner_client import RunnerClient, RunnerUnavailable, parse_outcome

COURSE = load_course(Path(__file__).resolve().parents[4] / "data/courses/python-basics.yaml")
EVEN = COURSE.objective("conditions-even")  # 3 visible tests, then 2 hidden


def outcome(*reprs: str | None) -> RunOutcome:
    return RunOutcome(
        "ok",
        tuple(
            {"repr": r} if r is not None else {"error": "TypeError", "message": "bad"}
            for r in reprs
        ),
    )


def test_the_request_carries_calls_but_never_expected_values() -> None:
    body = run_request(EVEN, "def is_even(n): ...")
    assert body == {"code": "def is_even(n): ...", "calls": [t.call for t in EVEN.tests]}
    assert "expected" not in json.dumps(body)


def test_all_passing_is_correct() -> None:
    g = grade(EVEN, outcome("True", "False", "True", "False", "True"))
    assert g.correct and g.score == 1.0
    assert g.hidden_passed == g.hidden_total == 2
    assert len(g.visible) == 3 and all(t.passed for t in g.visible)


def test_hidden_failures_count_but_their_details_are_not_shown() -> None:
    g = grade(EVEN, outcome("True", "False", "True", "True", "True"))
    assert not g.correct and g.score == pytest.approx(0.8)
    assert g.hidden_passed == 1
    assert [t.call for t in g.visible] == ["is_even(4)", "is_even(7)", "is_even(0)"]
    assert "ẩn: 1/2" in g.message_vi


def test_errors_are_reported_per_test() -> None:
    g = grade(EVEN, outcome(None, "False", "True", "False", "True"))
    assert not g.visible[0].passed and g.visible[0].error == "TypeError: bad"


@pytest.mark.parametrize(
    ("actual", "expected", "same"),
    [
        ("5.0", "5.0", True),
        ("5.00", "5.0", True),
        ("{'b': 2, 'a': 1}", "{'a': 1, 'b': 2}", True),
        ("True", "1", True),  # Python equality: True == 1
        ("'5'", "5", False),
        ("<object at 0x1>", "<object at 0x1>", True),  # not literals: compared as text
    ],
)
def test_values_compare_as_python_literals(actual: str, expected: str, same: bool) -> None:
    assert same_value(actual, expected) is same


@pytest.mark.parametrize("status", ["timeout", "memory", "output_limit", "crashed"])
def test_stopped_runs_score_zero_with_a_vietnamese_reason(status: str) -> None:
    g = grade(EVEN, RunOutcome(status))  # type: ignore[arg-type]
    assert not g.correct and g.score == 0.0 and g.message_vi


def test_load_errors_name_the_error() -> None:
    g = grade(EVEN, RunOutcome("load_error", load_error={"error": "SyntaxError", "message": "x"}))
    assert "SyntaxError" in g.message_vi


def test_a_result_count_mismatch_is_refused() -> None:
    with pytest.raises(ValueError):
        grade(EVEN, outcome("True"))


# --- course validation for code objectives --------------------------------------------------------


def _course(**code_objective: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "o",
        "concept": "k",
        "text_vi": "x",
        "modality": "code",
        "code": {
            "function": "f",
            "prompt_vi": "Viết f",
            "starter": "def f():\n    pass\n",
            "reference": "def f():\n    return 1\n",
            "wrong": ["def f():\n    return 2\n"],
        },
        "tests": [
            {"call": "f()", "expected": "1"},
            {"call": "f()", "expected": "1", "hidden": True},
        ],
    }
    base.update(code_objective)
    return {
        "slug": "c",
        "title_vi": "C",
        "title_en": "C",
        "source": "authored",
        "modalities": ["code"],
        "objectives": [base],
    }


def test_a_valid_code_objective_loads() -> None:
    CourseSpec.model_validate(_course())


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"tests": [{"call": "f()", "expected": "1"}]}, "visible and hidden"),
        ({"tests": [{"call": "f()", "expected": "1", "hidden": True}]}, "visible and hidden"),
        ({"code": None}, "needs a CodeTask"),
        ({"tests": [{"call": "g()", "expected": "1"}, {"call": "f()", "expected": "1",
                                                        "hidden": True}]}, "must call f"),
    ],
)  # fmt: skip
def test_code_objectives_must_be_complete(change: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        CourseSpec.model_validate(_course(**change))


# --- runner client ------------------------------------------------------------------------------


def _client(handler: object) -> RunnerClient:
    return RunnerClient(
        "http://runner",
        "tok",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )


OK_BODY = {"status": "ok", "results": [{"repr": "1"}], "load_error": None, "output": ""}


def test_client_sends_the_token_and_parses_the_outcome() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={**OK_BODY, "duration_ms": 5})

    out = asyncio.run(_client(handler).run({"code": "x", "calls": ["f()"]}))
    assert out.status == "ok" and out.results == ({"repr": "1"},)
    assert seen[0].headers["X-Runner-Token"] == "tok"
    assert seen[0].url.path == "/run"


@pytest.mark.parametrize("code", [401, 503, 500])
def test_client_errors_become_runner_unavailable(code: int) -> None:
    client = _client(lambda r: httpx.Response(code, json={}))
    with pytest.raises(RunnerUnavailable):
        asyncio.run(client.run({"code": "", "calls": []}))


def test_an_unreachable_runner_is_runner_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(RunnerUnavailable, match="unreachable"):
        asyncio.run(_client(handler).run({"code": "", "calls": []}))


def test_malformed_bodies_are_refused() -> None:
    with pytest.raises(RunnerUnavailable):
        parse_outcome({"status": "pwned"})
    with pytest.raises(RunnerUnavailable):
        parse_outcome({"status": "ok", "results": "x"})
