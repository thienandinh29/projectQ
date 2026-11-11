# Plan: code sandbox

## Architecture
```
web ──► API /attempts (code) ──► CodeGrader ──► Runner (HTTP, separate container) ──► one throwaway sandbox per run
                     ▲                │                                                  │
                     └── BKT, traces ◄┘◄──────────── reprs of actual values ◄────────────┘
```
- **`app/graders/code.py`** (pure): builds the run request (learner code + test *calls* only), compares returned reprs
  with expected values, computes the score, never imports or executes learner code.
- **`app/graders/runner_client.py`**: async HTTP client to the runner, with timeout and typed errors.
- **`runner/`** (new top-level service, own Dockerfile): a small HTTP server that, per request, starts a fresh
  sandbox container from a locked-down image and returns the results. The runner holds no database access and no
  secrets.
- **Sandbox image** `runner/sandbox.Dockerfile`: `python:3.12-slim`, non-root user, a fixed harness script that
  `exec`s the learner code in a fresh namespace, evaluates each call, and writes `{"repr": ...}` or
  `{"error": type, message}` per call.
- **Isolation** (recommended): `docker run --network none --read-only --tmpfs /tmp:size=16m --memory 256m
  --pids-limit 32 --cpus 1 --user 65534 --cap-drop ALL --security-opt no-new-privileges` with a wall-clock kill at
  5 s; `--runtime runsc` (gVisor) when the host has it. Alternatives considered: nsjail (strong, more setup),
  a hosted sandbox API (no host risk, costs money, code leaves the machine).
- **Contracts:** `CodeItem` (prompt, signature, starter code, visible and hidden tests, reference and wrong solutions,
  citations) added next to the MCQ item; `CodeAttempt` request/response bodies. `items.kind = 'code'` is already
  allowed by migration `0001`; code-specific fields live in `items.payload`. No migration expected.
- **Tutor:** code hints reuse the verified-hint path; a new deterministic check rejects hints that contain the target
  function's definition or more than 3 lines of code.

## Evaluation
- `evals/` gate: grader self-test over every code objective (reference passes, known-wrong fails).
- Escape-test suite runs in CI against the sandbox image (needs Docker in CI; GitHub runners have it).
- Latency report (p50, p95) per objective in `docs/v2/`.

## Risks
| Risk | Mitigation |
|---|---|
| Container escape | Least privilege, no network, gVisor where available, image without compilers or tools, no secrets on the host side reachable from the sandbox |
| Docker socket in the runner is powerful | The runner is its own service with no other duties; only the API can reach it; it accepts only the run schema |
| Slow cold starts | Keep the image small; measure; a warm pool is a later optimisation |
| Learners hard-code visible answers | Hidden tests; compare outside the sandbox |
