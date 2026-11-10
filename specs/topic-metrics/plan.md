# Plan: topic metrics

Spec: `specs/topic-metrics/spec.md`.

- **P1 (done):** `TopicMetrics` in `app/schemas.py` with a count check, tests, the `topic-metrics.response` mock (synthetic
  numbers, `cost_usd: null`), the `TEAM.md` API row.
- **P2:** the route. `items_generated`, `items_verified` and `items_dropped` come from the stored items and their verification
  status; `elapsed_seconds` from the job's start and finish; `cost_usd` only from a recorded billed amount (the gateway's
  per-attempt telemetry has tokens, not dollars), otherwise `null`.
- **P5:** a small panel on the topic screen; show "chưa rõ" for a `null`, never `0`; add `topics/{id}/metrics` to the proxy's
  allowlist (the current pattern only allows one path segment after `topics/`).
- Risk: the numbers are only as good as what P2 records; an honest `null` is the intended failure mode.
