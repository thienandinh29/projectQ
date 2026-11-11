# Tasks: code sandbox

- [x] Owner decisions: isolation technology, hidden tests, limits (`spec.md`): defaults
- [ ] `CodeItem` and `CodeAttempt` contracts, with validators and mocks
- [ ] Sandbox image and harness (returns reprs or errors per call, output capped)
- [ ] Runner service: one sandbox per request, limits, typed errors, health check
- [ ] Escape-test suite (network, file system, environment, fork, memory, loop, output, `os.system`) in CI
- [ ] `graders/code.py`: compare reprs outside the sandbox, score, per-test results; unit tests
- [ ] Runner client with timeout; API `/attempts` path for code items; BKT and mastery gate wired; traces
- [ ] Grader self-test gate over every code objective
- [ ] Tutor: code hint check (no target function definition, at most 3 lines of code)
- [ ] Python course: code items with visible and hidden tests, reference and wrong solutions
- [ ] Latency report (p50, p95)
- [ ] Next spec: web code editor (dependency decision) and optional in-browser runs
