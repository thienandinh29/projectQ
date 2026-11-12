"""Code practice through the API (specs/code-sandbox/practice-api.md), with a fake runner.

The real sandbox is covered by runner/tests and the CI code-selftest job; here the runner is a
fake so the tests exercise grading, BKT, the mastery gate, persistence and the route contract.
"""

from collections.abc import Iterator
from pathlib import Path

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from app.api import code as code_routes
from app.config import Settings
from app.curriculum.course import load_course
from app.graders.code import RunOutcome
from app.graders.runner_client import RunnerUnavailable
from app.main import create_app
from app.services.code_practice import RATE_PER_MINUTE, CodePractice

COURSES = Path(__file__).resolve().parents[3] / "data" / "courses"
COURSE = load_course(COURSES / "python-basics.yaml")
EVEN = COURSE.objective("conditions-even")


class FakeRunner:
    """Answers like the real runner: the value each call produced, never pass or fail."""

    def __init__(self) -> None:
        self.mode = "right"
        self.bodies: list[dict[str, object]] = []

    async def run(self, body: dict[str, object]) -> RunOutcome:
        self.bodies.append(body)
        if self.mode == "down":
            raise RunnerUnavailable("runner unreachable: ConnectError")
        if self.mode == "timeout":
            return RunOutcome("timeout")
        calls = body["calls"]
        assert isinstance(calls, list)
        expected = {t.call: t.expected for t in EVEN.tests}
        if self.mode == "right":
            return RunOutcome("ok", tuple({"repr": expected[c]} for c in calls))
        return RunOutcome("ok", tuple({"repr": "None"} for c in calls))  # "wrong"


Setup = tuple[TestClient, "FakeRunner", str, str]


@pytest.fixture
def setup(database_url: str) -> Iterator[Setup]:
    runner = FakeRunner()
    pool = ConnectionPool(database_url, open=True)
    practice = CodePractice(lambda: pool, runner, COURSES)
    app = FastAPI()
    app.include_router(code_routes.create_router(practice))
    with psycopg.connect(database_url) as conn:
        row = conn.execute(
            "insert into learners(display_name) values ('Code') returning id"
        ).fetchone()
        assert row
    with TestClient(app) as client:
        yield client, runner, str(row[0]), database_url
    pool.close()


def attempt(
    client: TestClient, learner: str, hints: int = 0, code: str = "def is_even(n): ..."
) -> httpx.Response:
    response: httpx.Response = client.post(
        "/code/attempts",
        json={"learner_id": learner, "course": "python-basics", "objective": "conditions-even",
              "code": code, "hints_used": hints},
    )  # fmt: skip
    return response


def test_the_exercise_never_reveals_hidden_tests_or_solutions(setup: Setup) -> None:
    client, _, learner, _ = setup
    r = client.get(
        "/code/exercise",
        params={"learner_id": learner, "course": "python-basics", "objective": "conditions-even"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["function"] == "is_even" and body["hidden_tests"] == 2
    assert len(body["visible_tests"]) == 3
    text = r.text
    assert "is_even(-3)" not in text and "is_even(-8)" not in text  # hidden calls
    assert "return n % 2 == 0" not in text  # reference solution


def test_the_runner_never_receives_expected_values(setup: Setup) -> None:
    client, runner, learner, _ = setup
    assert attempt(client, learner).status_code == 200
    assert set(runner.bodies[0]) == {"code", "calls"}
    assert "expected" not in str(runner.bodies[0])


def test_correct_code_raises_mastery_and_needs_two_unaided_wins(setup: Setup) -> None:
    client, _, learner, db = setup
    first = attempt(client, learner).json()
    assert first["correct"] and first["score"] == 1.0 and first["hidden_passed"] == 2
    assert first["p_known"] > 0.2
    assert not first["mastered"]  # one unaided win is not enough evidence
    second = attempt(client, learner).json()
    assert second["mastered"] and second["p_known"] >= 0.95
    assert any(t["kind"] == "review" for t in second["traces"])  # reviews start at mastery
    with psycopg.connect(db) as conn:
        rows = conn.execute(
            "select a.answer->>'kind',a.answer->>'status',a.is_correct from attempts a "
            "where a.learner_id=%s",
            (learner,),
        ).fetchall()
        traces = conn.execute(
            "select count(*) from decision_traces where learner_id=%s", (learner,)
        ).fetchone()
    assert rows == [("code", "ok", True), ("code", "ok", True)]
    assert traces and traces[0] >= 3


def test_hints_weaken_the_evidence(setup: Setup) -> None:
    client, _, learner, _ = setup
    helped = attempt(client, learner, hints=3).json()["p_known"]
    client2 = client  # same app; a fresh learner gives a clean prior
    with psycopg.connect(setup[3]) as conn:
        row = conn.execute(
            "insert into learners(display_name) values ('B') returning id"
        ).fetchone()
        assert row
    unaided = attempt(client2, str(row[0])).json()["p_known"]
    assert helped < unaided


def test_wrong_and_stopped_runs_are_incorrect_attempts(setup: Setup) -> None:
    client, runner, learner, _ = setup
    runner.mode = "wrong"
    wrong = attempt(client, learner).json()
    assert not wrong["correct"] and wrong["score"] == 0.0 and wrong["p_known"] < 0.2
    assert [t["passed"] for t in wrong["visible"]] == [False, False, False]
    runner.mode = "timeout"
    stopped = attempt(client, learner).json()
    assert stopped["status"] == "timeout" and not stopped["correct"]
    assert "5 giây" in stopped["message_vi"]


def test_an_unreachable_runner_records_nothing(setup: Setup) -> None:
    client, runner, learner, db = setup
    runner.mode = "down"
    r = attempt(client, learner)
    assert r.status_code == 503
    with psycopg.connect(db) as conn:
        n = conn.execute("select count(*) from attempts where learner_id=%s", (learner,)).fetchone()
    assert n == (0,)


def test_limits(setup: Setup) -> None:
    client, runner, learner, _ = setup
    assert attempt(client, learner, code="x" * (20 * 1024 + 1)).status_code == 422
    runner.mode = "wrong"
    for _ in range(RATE_PER_MINUTE):
        assert attempt(client, learner).status_code == 200
    assert attempt(client, learner).status_code == 429


def test_unknown_course_objective_or_learner(setup: Setup) -> None:
    client, _, learner, _ = setup
    base = {"learner_id": learner, "course": "python-basics", "objective": "conditions-even"}
    assert client.get("/code/exercise", params={**base, "course": "nope"}).status_code == 404
    assert (
        client.get("/code/exercise", params={**base, "objective": "loops-concept"}).status_code
        == 404
    )
    other = "00000000-0000-0000-0000-000000000000"
    assert client.get("/code/exercise", params={**base, "learner_id": other}).status_code == 404


def test_course_sync_is_idempotent(setup: Setup) -> None:
    client, _, learner, db = setup
    attempt(client, learner)
    from app.curriculum.store import sync_course

    with psycopg.connect(db) as conn:
        sync_course(conn, COURSE)
        sync_course(conn, COURSE)
        concepts = conn.execute(
            "select count(*) from concepts c join subjects s on s.id=c.subject_id where s.slug=%s",
            ("python-basics",),
        ).fetchone()
        items = conn.execute(
            "select count(*) from items where external_id like 'code:python-basics:%%'"
        ).fetchone()
    assert concepts == (3,) and items == (2,)


def test_routes_are_mounted_only_with_a_runner(database_url: str) -> None:
    off = create_app(Settings(database_url=database_url, allow_unauthenticated_local_dev=True,
                              _env_file=None))  # fmt: skip
    on = create_app(Settings(database_url=database_url, allow_unauthenticated_local_dev=True,
                             runner_url="http://runner.invalid", _env_file=None))  # fmt: skip
    assert not [p for p in off.openapi()["paths"] if p.startswith("/code")]
    assert {"/code/exercise", "/code/attempts"} <= set(on.openapi()["paths"])
