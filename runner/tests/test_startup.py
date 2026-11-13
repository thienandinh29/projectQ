"""The learner's time limit starts once the sandbox is up, never while Docker starts it.

These use plain subprocesses in place of `docker run`, so they need no Docker.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nodetrail_runner.sandbox import READY, _await_ready

HARNESS = Path(__file__).resolve().parents[1] / "sandbox" / "harness.py"


def _proc(script: str) -> "subprocess.Popen[bytes]":
    # Pipes are block-buffered without PYTHONUNBUFFERED (as in CI): every script flushes.
    return subprocess.Popen(
        [sys.executable, "-c", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )


def test_a_slow_start_is_waited_for_and_not_counted() -> None:
    proc = _proc(f"import sys, time; time.sleep(1.5); sys.stdout.write({READY.decode()!r}); "
                 "sys.stdout.flush(); sys.stdin.read()")  # fmt: skip
    began = time.monotonic()
    assert _await_ready(proc, seconds=10) is None
    assert time.monotonic() - began >= 1.4  # it really waited for the slow start
    proc.kill()
    proc.wait()


@pytest.mark.parametrize(
    ("script", "why"),
    [
        ("import time; time.sleep(5)", "did not start within 0.5 s"),
        ("pass", "exited before it was ready"),
        (
            "print('learner output first', flush=True); import sys; sys.stdin.read()",
            "unexpected first line",
        ),
    ],
)
def test_a_sandbox_that_never_gets_ready_is_reported(script: str, why: str) -> None:
    proc = _proc(script)
    problem = _await_ready(proc, seconds=0.5)
    assert problem is not None and why in problem
    proc.kill()
    proc.wait()


def test_the_harness_announces_ready_before_reading_the_request() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-I", str(HARNESS)], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    assert _await_ready(proc, seconds=10) is None  # before any request was sent
    request = {"nonce": "n0", "code": "def f():\n    return 2\n", "calls": ["f()"]}
    out, _ = proc.communicate(json.dumps(request).encode(), timeout=10)
    assert out.decode().rstrip().endswith('n0 {"results": [{"repr": "2"}]}')
