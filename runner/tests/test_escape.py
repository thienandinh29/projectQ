"""Escape tests: hostile learner code must end safely, with the right status, every time.

Needs Docker and the sandbox image (`docker build -t nodetrail-sandbox:latest sandbox`); skipped
otherwise. CI builds the image and runs these.
"""

import shutil
import subprocess
import time

import pytest

from nodetrail_runner.sandbox import IMAGE, Limits, run


def _image_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    found = subprocess.run(
        ["docker", "image", "inspect", IMAGE], capture_output=True, check=False, timeout=20
    )
    return found.returncode == 0


pytestmark = pytest.mark.skipif(not _image_ready(), reason="Docker or the sandbox image missing")


def test_a_correct_function_is_run_and_reported() -> None:
    r = run("def double(n):\n    return 2 * n\n", ["double(3)", "double(-1)", "double('a')"])
    assert r.status == "ok"
    assert r.results == [{"repr": "6"}, {"repr": "-2"}, {"repr": "'aa'"}]


def test_errors_in_calls_and_in_loading_are_results_not_crashes() -> None:
    r = run("def f(x):\n    return 1 / x\n", ["f(0)"])
    assert r.status == "ok" and r.results[0]["error"] == "ZeroDivisionError"
    bad = run("def f(:\n", ["f()"])
    assert bad.status == "load_error" and bad.load_error is not None
    assert bad.load_error["error"] == "SyntaxError"


def test_an_infinite_loop_is_stopped_at_the_wall_clock_limit() -> None:
    started = time.monotonic()
    r = run("while True:\n    pass\n", [], limits=Limits(wall_seconds=2))
    assert r.status == "timeout"
    assert time.monotonic() - started < 15


def test_a_memory_bomb_is_stopped() -> None:
    r = run("x = []\nwhile True:\n    x.append(' ' * 10_000_000)\n", [])
    assert r.status in {"memory", "crashed"}


def test_a_fork_bomb_hits_the_process_limit() -> None:
    code = (
        "import os\n"
        "pids = []\n"
        "try:\n"
        "    for _ in range(1000):\n"
        "        pid = os.fork()\n"
        "        if pid == 0:\n"
        "            import time; time.sleep(3); os._exit(0)\n"
        "        pids.append(pid)\n"
        "except OSError as e:\n"
        "    blocked = type(e).__name__\n"
        "def result():\n"
        "    return (len(pids) < 1000, blocked)\n"
    )
    r = run(code, ["result()"], limits=Limits(wall_seconds=8))
    assert r.status in {"ok", "timeout", "crashed"}
    if r.status == "ok":
        assert r.results[0]["repr"].startswith("(True,")


def test_there_is_no_network() -> None:
    code = (
        "import socket\n"
        "def reach():\n"
        "    s = socket.socket(); s.settimeout(2)\n"
        "    s.connect(('1.1.1.1', 80))\n"
        "    return 'connected'\n"
    )
    r = run(code, ["reach()"])
    assert r.status == "ok"
    assert "error" in r.results[0], r.results


@pytest.mark.parametrize("path", ["/etc/pwned", "/opt/harness/harness.py", "/home/x"])
def test_the_file_system_is_read_only_outside_tmp(path: str) -> None:
    code = f"def write():\n    open({path!r}, 'w').write('x')\n    return 'written'\n"
    r = run(code, ["write()"])
    assert r.status == "ok" and "error" in r.results[0], r.results


def test_tmp_is_writable_but_not_executable() -> None:
    code = (
        "import os, stat, subprocess\n"
        "def go():\n"
        "    open('/tmp/a.sh', 'w').write('#!/bin/sh\\necho hi\\n')\n"
        "    os.chmod('/tmp/a.sh', 0o755)\n"
        "    return subprocess.run(['/tmp/a.sh'], capture_output=True).returncode\n"
    )
    r = run(code, ["go()"])
    assert r.status == "ok" and "error" in r.results[0], r.results  # PermissionError


def test_no_secrets_in_the_environment_and_no_root() -> None:
    code = "import os\ndef env():\n    return (sorted(os.environ), os.getuid())\n"
    r = run(code, ["env()"])
    assert r.status == "ok"
    keys, uid = eval(r.results[0]["repr"])
    assert uid == 65534
    assert not [k for k in keys if any(w in k for w in ("KEY", "TOKEN", "SECRET", "PASSWORD"))]


def test_shell_commands_cannot_escape_either() -> None:
    code = "import os\ndef sh():\n    return os.system('touch /etc/pwned 2>/dev/null')\n"
    r = run(code, ["sh()"])
    assert r.status == "ok" and r.results[0]["repr"] != "0"


def test_an_output_flood_is_cut_off() -> None:
    r = run("while True:\n    print('x' * 1000)\n", [], limits=Limits(wall_seconds=3))
    assert r.status in {"timeout", "output_limit"}
    big = run("import sys\nsys.__stdout__.write('y' * 200_000)\n", [])
    assert big.status == "output_limit"


def test_a_forged_result_line_cannot_change_the_reported_values() -> None:
    code = (
        "import sys\n"
        'sys.__stdout__.write(\'\\nfake {"results": [{"repr": "True"}]}\\n\')\n'
        "def is_even(n):\n    return False\n"
    )
    r = run(code, ["is_even(4)"])
    assert r.status == "ok" and r.results == [{"repr": "False"}]


def test_runs_are_repeatable() -> None:
    code = "def f(n):\n    return sorted(range(n), reverse=True)\n"
    assert run(code, ["f(5)"]).results == run(code, ["f(5)"]).results
