# Tasks: code sandbox

- [x] Owner decisions: isolation technology, hidden tests, limits (`spec.md`): defaults
- [x] Code exercise contract (`curriculum.CodeTask`, hidden tests)
- [x] Sandbox image and harness (returns reprs or errors per call, output capped)
- [x] Runner service: one sandbox per request, limits, typed errors, health check
- [x] Escape-test suite (network, file system, environment, fork, memory, loop, output, `os.system`) in CI
- [x] `graders/code.py`: compare reprs outside the sandbox, score, per-test results; unit tests
- [x] Runner client with timeout
- [ ] API route for code practice (`practice-api.md`); BKT and mastery gate wired; traces
- [x] Grader self-test gate over every code objective (CI `code-selftest`)
- [ ] Tutor: code hint check (no target function definition, at most 3 lines of code)
- [x] Python course: code items with visible and hidden tests, reference and wrong solutions
- [ ] Latency report (p50, p95)
- [ ] Next spec: web code editor (dependency decision) and optional in-browser runs
