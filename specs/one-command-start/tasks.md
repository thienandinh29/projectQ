# Tasks: one-command start

- [x] API image (API, worker, migrations) and web image, both non-root
- [x] Compose: db → migrate → api/worker; sandbox → runner; web after api; TEI as an opt-in profile; localhost only
- [x] Runner refuses to listen beyond loopback without a token (test)
- [x] `scripts/stack-smoke.sh`: health, key enforcement, web page, web proxy, code right/wrong/timeout in the
      sandbox, worker finishes a queued job
- [x] CI job `stack`
- [x] `docker/LOCAL.md` runbook, `.env.example`, MAP
- [ ] Owner: run the stack and the TEI indexing on their own machine; record time, chunk count and peak memory in
      `docs/v2/decision-log.md`
