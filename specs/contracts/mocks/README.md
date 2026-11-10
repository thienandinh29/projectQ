# Mock JSON for the web app (P5)

One file per response/request shape in the `TEAM.md` API table. Build screens against these until P2's stubs
serve the same shapes (H3). Topic: **Python cơ bản**, a 7-concept diamond graph; the learner is solid on
variables, shaky on booleans.

**Do not edit by hand.** They are generated from the contract models and real engine output:
`cd apps/api && uv run python -m tests.engine.mocks`. A test fails if a file drifts from `app/schemas.py`.
Need a different mock? Ask P1.

| File | Route | Notes |
|---|---|---|
| `learners.request/response` | `POST /learners` | |
| `topics.request/response` | `POST /topics` | `cached: false` |
| `topics-id.researching` / `.ready` | `GET /topics/{id}` and each SSE `state` payload | research trail, 3 sources from 3 publishers |
| `topics-cached.response` | `GET /topics/cached` | |
| `uploads.request-link` / `.response` | `POST /uploads` (link body) | file upload is multipart; response shape is the same |
| `graph.response` | `GET /graph` | `edges` use the key `from`; node brightness = `p_known` |
| `graph-review.response` | `GET /graph/review` | the generated map (concepts and edges) before mastery, with its `graph_revision` and `confirmed`; learner from the session cookie |
| `graph-confirm.request` / `.response` | `POST /graph/confirm` | the learner explicitly accepts the revision they were shown; no learner id in the body; 409 if stale (`specs/graph-confirmation-contract/`) |
| `topic-metrics.response` | `GET /topics/{id}/metrics` | synthetic numbers; `cost_usd: null` means unknown (`specs/topic-metrics/`) |
| `placement-next.request` / `.question` / `.done` | `POST /placement/next` | `.question` and `.done` are real `placement.next_question` output; `.done` (4 questions, learner's real gap = booleans) has `gap_slug` and `item: null` |
| `next-item.response` | `GET /next-item` | |
| `attempts.request` | `POST /attempts` | `answer` = 0-based option index |
| `attempts.wrong` | `POST /attempts` | wrong on loops → `remediation` to booleans; traces `bkt_update` + `root_cause` |
| `attempts.correct` | `POST /attempts` | `mastered: true`; traces `bkt_update` + `review` (the praise + review moment) |
| `tutor-hint.request/response` | `POST /tutor/hint` | every hint has ≥ 1 citation |
| `ask.request/response` | `POST /ask` | |
| `reviews-due.response` | `GET /reviews/due` | |
| `exam-plan.request/response` | `POST /exam-plan` | |

Rules the web app can rely on: `item` never contains the answer or `correct`; traces carry `rule_vi` ready to
display in the "Vì sao?" panel; `prior`, `posterior` and `evidence` fields can be `null`; the SSE stream also sends
a `heartbeat` event (no payload) every 15–20 s.
