# Feature: topic metrics for the demo dashboard

Lane P1 (contract) with P2 (route and numbers) and P5 (panel). Status: **contract proposed by P1 on 2026-11-07, additive.**

## Why
`SPEC.md` demo step 4 shows, for the topic the judge just built, the time it took, the cost and the questions dropped by the
verifier. No API field carried those numbers, so there was nothing for a dashboard to show.

## The contract (`app/schemas.py`)
`GET /topics/{topic_id}/metrics` → `TopicMetrics {topic_id, elapsed_seconds, cost_usd, items_generated, items_verified,
items_dropped}`.
- `elapsed_seconds`: wall time of the build, or `null` when unknown.
- `cost_usd`: **measured** model-call cost, or `null` when unknown. It is never estimated from token counts alone; if the
  gateway returns no billing amount the value stays `null` and the panel says so.
- `items_dropped`: items that failed verification and were therefore never served. `items_verified + items_dropped` may not
  exceed `items_generated` (some may still be pending), enforced by the model.
- A separate route, not a field on `TopicState`, so no existing response or mock changes.

## Out of scope
Per-model breakdowns, search and storage costs (the cap in `specs/model-test/run-procedure.md` reserves them separately),
history across topics, authentication of the route beyond what every route has.

## Acceptance
Contract tests and the `topic-metrics.response` mock pass. P2's route returns real numbers for a built topic: `items_*`
match the database, and `cost_usd` is `null` unless a billed amount was recorded.
