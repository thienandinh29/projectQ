"""Start one locked-down container per run, feed it the code and the test calls, read the result.

Limits (specs/code-sandbox, owner decision 2026-11-11): 5 s wall time, 256 MB memory, 32 processes,
64 KB output, no network, read-only file system with a small /tmp, non-root, no capabilities.
gVisor (`runsc`) is used when the Docker host has it.
"""

import json
import os
import secrets
import select
import subprocess
import time
from dataclasses import dataclass, field
from typing import Literal

IMAGE = "nodetrail-sandbox:latest"
Status = Literal["ok", "load_error", "timeout", "memory", "output_limit", "crashed"]


@dataclass(frozen=True)
class Limits:
    wall_seconds: float = 5.0
    memory_mb: int = 256
    pids: int = 32
    output_bytes: int = 64 * 1024
    tmp_mb: int = 16
    cpus: float = 1.0


@dataclass(frozen=True)
class RunResult:
    status: Status
    results: list[dict[str, str]] = field(default_factory=list)
    load_error: dict[str, str] | None = None
    output: str = ""  # what the learner printed (capped), for feedback only
    duration_ms: int = 0


def docker_args(name: str, limits: Limits, image: str, runtime: str | None) -> list[str]:
    args = [
        "docker", "run", "-i", "--name", name,
        "--network", "none",
        "--read-only",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,size={limits.tmp_mb}m",
        "--memory", f"{limits.memory_mb}m",
        "--memory-swap", f"{limits.memory_mb}m",
        "--pids-limit", str(limits.pids),
        "--cpus", str(limits.cpus),
        "--user", "65534:65534",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--ulimit", "nofile=64:64",
        "--env-file", "/dev/null",
        "--log-driver", "none",
    ]  # fmt: skip
    if runtime:
        args += ["--runtime", runtime]
    return [*args, image]


def available_runtime() -> str | None:
    """`runsc` (gVisor) when the Docker host offers it, otherwise the default runtime."""
    try:
        info = subprocess.run(
            ["docker", "info", "--format", "{{json .Runtimes}}"],
            capture_output=True, text=True, timeout=10, check=False,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None
    return "runsc" if '"runsc"' in info.stdout else None


def _cleanup(name: str) -> bool:
    """Remove the container; returns whether it was killed for memory."""
    inspect = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.OOMKilled}}", name],
        capture_output=True, text=True, timeout=10, check=False,
    )  # fmt: skip
    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=20, check=False)
    return inspect.stdout.strip() == "true"


def _exchange(
    proc: "subprocess.Popen[bytes]", payload: bytes, limits: Limits, started: float
) -> tuple[bytes, Status | None]:
    """Send the request, read stdout without ever holding more than the output cap.

    Returns the output and, when the run had to be stopped, why ("timeout" or "output_limit").
    """
    assert proc.stdin is not None and proc.stdout is not None
    try:
        proc.stdin.write(payload)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    os.set_blocking(proc.stdout.fileno(), False)
    chunks: list[bytes] = []
    size = 0
    while True:
        remaining = limits.wall_seconds - (time.monotonic() - started)
        if remaining <= 0:
            return b"".join(chunks), "timeout"
        ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 0.2))
        if ready:
            chunk = proc.stdout.read(65536)
            if not chunk:  # end of output: the harness finished
                return b"".join(chunks), None
            size += len(chunk)
            if size > limits.output_bytes:
                return b"", "output_limit"
            chunks.append(chunk)
        elif proc.poll() is not None:
            rest = proc.stdout.read() or b""
            if size + len(rest) > limits.output_bytes:
                return b"", "output_limit"
            return b"".join([*chunks, rest]), None


def run(
    code: str,
    calls: list[str],
    *,
    limits: Limits | None = None,
    image: str = IMAGE,
    runtime: str | None = None,
) -> RunResult:
    limits = limits or Limits()
    name = "nt-run-" + secrets.token_hex(8)
    nonce = secrets.token_hex(16)
    payload = json.dumps({"nonce": nonce, "code": code, "calls": calls}).encode()
    started = time.monotonic()
    proc = subprocess.Popen(
        docker_args(name, limits, image, runtime),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    stopped: Status | None = "crashed"
    out = b""
    oom = False
    try:
        out, stopped = _exchange(proc, payload, limits, started)
    finally:
        if stopped is not None:
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=20, check=False)
            assert proc.stdout is not None
            proc.stdout.close()  # unblocks the docker client if it was writing into a full pipe
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        oom = _cleanup(name)  # always remove the container, whatever happened above
    duration = int((time.monotonic() - started) * 1000)
    if stopped is not None:
        return RunResult(stopped, duration_ms=duration)
    if oom:
        return RunResult("memory", duration_ms=duration)
    text = out.decode("utf-8", errors="replace")
    marker = "\n" + nonce + " "
    at = text.rfind(marker)
    if at < 0:
        return RunResult("crashed", output=text[-2000:], duration_ms=duration)
    printed = text[:at]
    try:
        report = json.loads(text[at + len(marker) :].strip().splitlines()[0])
    except (ValueError, IndexError):
        return RunResult("crashed", output=printed[-2000:], duration_ms=duration)
    if "load_error" in report:
        return RunResult(
            "load_error", load_error=report["load_error"], output=printed, duration_ms=duration
        )
    return RunResult("ok", results=report["results"], output=printed, duration_ms=duration)
