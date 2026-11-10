# Plan: graph confirmation contract

Spec: `specs/graph-confirmation-contract/spec.md` (the contract, P1). The routes' own spec is `specs/graph-confirmation/` (P3, on `ptest2`).

## History
P1's first version (merged in PR #21) put `revision` on `GraphView`, used `POST /graph/confirm {learner_id, subject,
revision}` and named no session. P3 had already built `GET /graph/review` and `POST /graph/confirm {subject, graph_revision}`
with the learner taken from the session cookie. P1 aligned the contract to P3's routes rather than make P3 change them close
to the freeze: the code is live, P5's branches already call `graph/review`, and identity from the session is what the spec
asks for. `GraphView.revision` was removed again (nothing used it).

## Done by P1
- `app/schemas.py`: `GraphReview`, `GraphConfirm`, `GraphConfirmed`, `GRAPH_REVISION_PATTERN`; all `extra="forbid"`.
- Mocks: `graph-review.response`, `graph-confirm.request`, `graph-confirm.response`; `graph.response` is back to its original
  shape. `TEAM.md` API table and the mocks README updated.

## Needed from others
- **P3:** replace the duplicate DTOs in `app/api/graph_confirmation.py` (`ConfirmationInput`, `GraphReview`, `GraphConfirmed`)
  with imports from `app/schemas.py` (`GraphConfirm` is the request model); same field names, so the wire does not change.
- **P5:** call `GET /graph/review?subject=` and `POST /graph/confirm {subject, graph_revision}` from the main workspace with the
  session cookie; keep the revision from the response that was displayed; re-fetch on 409; allow both paths in the proxy and
  forward the cookie.
- **P2:** keep `GraphConfirmations` and migration `0012` as delivered.

## Risks
Two meanings of 409 (stale revision; not yet confirmed). Accepted for the demo; a machine-readable `code` can be added later.
