# Runner: learner code in a sandbox

Runs untrusted learner code for code exercises (`specs/code-sandbox/`). The API never executes learner code itself;
it sends `{"code", "calls"}` here and compares the returned values with the expected ones.

- `sandbox/`: the sandbox image (Python and a fixed harness; no pip, non-root, empty environment).
- `nodetrail_runner/sandbox.py`: one container per run with no network, a read-only file system, a 16 MB `/tmp`
  that cannot execute files, 256 MB memory, 32 processes, 1 CPU, 5 s wall time, 64 KB output, no capabilities;
  gVisor (`runsc`) when the host offers it.
- `nodetrail_runner/server.py`: `POST /run`, `GET /health`; size limits, `X-Runner-Token`, a concurrency cap.

```bash
docker build -t nodetrail-sandbox:latest sandbox
```

```bash
uv sync && uv run pytest -q
```

`tests/test_escape.py` runs hostile code (network, file system, environment, fork bomb, memory bomb, infinite loop,
output flood, shell commands, forged result lines) and needs Docker and the sandbox image; it is skipped without them.

Security note: the runner container uses the host Docker socket to start sandboxes. Keep it on a private network,
set `RUNNER_TOKEN`, and give it no other duty. Prefer a host with gVisor installed.
