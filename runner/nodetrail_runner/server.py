"""The runner's HTTP interface: POST /run and GET /health, standard library only.

The runner has one job and no other access: no database, no model keys. Only the API should reach
it (same private network); when RUNNER_TOKEN is set, every /run request must carry it in the
`X-Runner-Token` header.

Environment: RUNNER_HOST (default 127.0.0.1), RUNNER_PORT (8090), RUNNER_TOKEN,
RUNNER_CONCURRENCY (4).
"""

import hmac
import json
import os
import threading
from collections.abc import Callable
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from nodetrail_runner.sandbox import RunResult, available_runtime, run

MAX_CODE_BYTES = 20 * 1024
MAX_CALLS = 50
MAX_CALL_CHARS = 500
MAX_BODY = MAX_CODE_BYTES + MAX_CALLS * MAX_CALL_CHARS + 4096

Runner = Callable[[str, list[str]], RunResult]


class BadRequest(ValueError):
    pass


def parse(body: bytes) -> tuple[str, list[str]]:
    try:
        data = json.loads(body)
    except ValueError:
        raise BadRequest("body is not JSON") from None
    if not isinstance(data, dict) or set(data) != {"code", "calls"}:
        raise BadRequest("expected exactly the fields code and calls")
    code, calls = data["code"], data["calls"]
    if not isinstance(code, str) or len(code.encode()) > MAX_CODE_BYTES:
        raise BadRequest(f"code must be a string of at most {MAX_CODE_BYTES} bytes")
    if (
        not isinstance(calls, list)
        or len(calls) > MAX_CALLS
        or not all(isinstance(c, str) and 0 < len(c) <= MAX_CALL_CHARS for c in calls)
    ):
        raise BadRequest(f"calls must be at most {MAX_CALLS} strings of 1-{MAX_CALL_CHARS} chars")
    return code, calls


def make_handler(runner: Runner, token: str, slots: threading.BoundedSemaphore) -> type:
    class Handler(BaseHTTPRequestHandler):
        server_version = "nodetrail-runner"

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._send(200, {"status": "ok"})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/run":
                self._send(404, {"error": "not found"})
                return
            given = self.headers.get("X-Runner-Token", "")
            if token and not hmac.compare_digest(given, token):
                self._send(401, {"error": "unauthorised"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                self._send(413, {"error": "body too large or empty"})
                return
            try:
                code, calls = parse(self.rfile.read(length))
            except BadRequest as exc:
                self._send(400, {"error": str(exc)})
                return
            if not slots.acquire(blocking=False):
                self._send(503, {"error": "busy, retry shortly"})
                return
            try:
                result = runner(code, calls)
            finally:
                slots.release()
            self._send(200, asdict(result))

        def log_message(self, format: str, *args: Any) -> None:
            pass  # never log request bodies: they contain learner code

    return Handler


def serve() -> None:
    runtime = available_runtime()
    token = os.environ.get("RUNNER_TOKEN", "")
    slots = threading.BoundedSemaphore(int(os.environ.get("RUNNER_CONCURRENCY", "4")))
    handler = make_handler(lambda code, calls: run(code, calls, runtime=runtime), token, slots)
    host = os.environ.get("RUNNER_HOST", "127.0.0.1")
    port = int(os.environ.get("RUNNER_PORT", "8090"))
    state = "set" if token else "unset"
    print(f"runner on {host}:{port} runtime={runtime or 'default'} token={state}", flush=True)
    ThreadingHTTPServer((host, port), handler).serve_forever()


if __name__ == "__main__":
    serve()
