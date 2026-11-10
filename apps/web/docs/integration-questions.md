# P5 integration status on ptest

Source of truth: `TEAM.md`, `specs/contracts/mocks/` and the integrated app's OpenAPI.
P5's web branch is now included in ptest. Mock mode remains an explicitly labeled
UI simulation; API errors never fall back to sample answers or a sample graph.

## Confirmed consumer conventions

| Setting or shape             | Confirmed value                       | Evidence                                             |
| ---------------------------- | ------------------------------------- | ---------------------------------------------------- |
| API key header               | `X-API-Key`                           | `app/main.py`                                        |
| Multipart upload field       | `file`                                | P3 upload router                                     |
| API file limit               | 20,000,000 bytes, 200 pages           | P3 upload reader/router                              |
| File types                   | PDF and DOCX                          | P3 upload router                                     |
| Answer encoding              | `index0`                              | P1 `attempts.request.json`, deterministic MCQ grader |
| Trace probabilities          | nullable `prior` / `posterior`        | P1 correct-attempt and placement mocks               |
| Trace evidence               | object with optional nullable members | P1 trace model and mocks                             |
| Graph edges                  | `{from, to}`                          | P1 graph mock                                        |
| Placement completion         | `done: true`, `item: null`            | P1 placement mock                                    |
| Citations in tutor responses | `{title, section, url}`               | P1 mock / P3 router                                  |
| Topic progress               | API integer 0..100                    | P2 queue and P3 pipeline                             |

For API mode set server-only `NODETRAIL_DATA_MODE=api`, `NODETRAIL_API_URL`,
`NODETRAIL_API_KEY`, `NODETRAIL_API_KEY_HEADER=X-API-Key`,
`NODETRAIL_UPLOAD_FIELD=file`, `NODETRAIL_MAX_UPLOAD_BYTES=20000000` and
`NODETRAIL_ANSWER_ENCODING=index0`. Configure a lower upload cap if the deployment
platform requires it. Never expose API credentials through `NEXT_PUBLIC_` variables.

`NODETRAIL_HINT_FIRST_LEVEL=1` follows P1's `HintRequest` contract (levels 1..4).
The mounted tutor handler still returns 503 until P4 supplies the verified backend.

## Remaining owner inputs and acceptance

- P4: deliver verified graph/item generation, Socratic tutor/gate and migration 0005.
  A mounted route with an unavailable backend is not a working hint or topic pipeline.
- P1/P3: align the provisional hint DTO with P1 `HintRequest`: P1 uses an integer
  option index for optional `last_answer` and levels 1..4; P3 currently declares
  `last_answer` as a string and permits any nonnegative level. The current web
  client omits `last_answer` and begins at level 1.
- P4/P2: serve authorized citation URLs for private uploaded sources; the web does
  not build private Storage URLs or make buckets public.
- A map node does not choose a live placement concept. The engine selects it through
  `{learner_id, subject}`; the UI follows `trace.concept_slug`. Direct per-node lesson
  content remains mock-only because the API has no lesson-content endpoint.
- Web uses cancellable snapshot polling/retry. Backend SSE state/heartbeat events
  are available separately; SSE reconnection is not implemented by this client.
- P2/P5: verify desktop/mobile/keyboard using `verification.md`, then the deployed
  API flow. Deployment URL/configuration and a recorded/replayed backup video are
  still pending; code checks cannot replace those observations.
