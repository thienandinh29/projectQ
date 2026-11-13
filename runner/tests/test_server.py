"""The HTTP layer, with a fake sandbox: validation, auth, concurrency, no Docker needed."""

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer

import pytest

from nodetrail_runner.sandbox import RunResult
from nodetrail_runner.server import MAX_CALLS, MAX_CODE_BYTES, bind_problem, make_handler

TOKEN = "test-token"


@pytest.fixture
def server() -> Iterator[tuple[str, list[tuple[str, list[str]]]]]:
    seen: list[tuple[str, list[str]]] = []
    gate = threading.Event()

    def fake(code: str, calls: list[str]) -> RunResult:
        seen.append((code, calls))
        if code == "block":
            gate.wait(5)
        return RunResult("ok", results=[{"repr": "1"} for _ in calls])

    httpd = ThreadingHTTPServer(
        ("127.0.0.1", 0), make_handler(fake, TOKEN, threading.BoundedSemaphore(1))
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", seen
    gate.set()
    httpd.shutdown()


def post(url: str, body: object, token: str | None = TOKEN) -> tuple[int, dict[str, object]]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url + "/run", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("X-Runner-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def test_health(server: tuple[str, list[object]]) -> None:
    with urllib.request.urlopen(server[0] + "/health", timeout=5) as resp:
        assert json.loads(resp.read()) == {"status": "ok"}


def test_a_valid_request_runs(server: tuple[str, list[tuple[str, list[str]]]]) -> None:
    status, body = post(server[0], {"code": "x = 1", "calls": ["x", "x"]})
    assert status == 200 and body["status"] == "ok"
    assert server[1] == [("x = 1", ["x", "x"])]


@pytest.mark.parametrize("token", [None, "wrong"])
def test_requests_without_the_token_are_refused(
    server: tuple[str, list[object]], token: str | None
) -> None:
    status, _ = post(server[0], {"code": "x", "calls": []}, token=token)
    assert status == 401
    assert server[1] == []


@pytest.mark.parametrize(
    "body",
    [
        {"code": "x"},
        {"code": "x", "calls": [], "extra": 1},
        {"code": 1, "calls": []},
        {"code": "x" * (MAX_CODE_BYTES + 1), "calls": []},
        {"code": "x", "calls": ["f()"] * (MAX_CALLS + 1)},
        {"code": "x", "calls": [""]},
    ],
)
def test_invalid_requests_are_refused_before_running(
    server: tuple[str, list[object]], body: object
) -> None:
    status, _ = post(server[0], body)
    assert status in {400, 413}
    assert server[1] == []


def test_a_busy_runner_answers_503_instead_of_queueing(
    server: tuple[str, list[object]],
) -> None:
    first = threading.Thread(target=post, args=(server[0], {"code": "block", "calls": []}))
    first.start()
    for _ in range(50):  # wait until the first request holds the only slot
        if server[1]:
            break
        threading.Event().wait(0.05)
    status, _ = post(server[0], {"code": "x", "calls": []})
    assert status == 503


def test_a_runner_reachable_beyond_loopback_needs_a_token() -> None:
    assert bind_problem("0.0.0.0", "") is not None
    assert bind_problem("0.0.0.0", "secret") is None
    assert bind_problem("127.0.0.1", "") is None  # local development and tests
