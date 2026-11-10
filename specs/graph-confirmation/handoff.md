# P3 -> P2/P5: graph review and confirmation

The backend and proxy are ready for UI integration on ptest2.
The learner must press an explicit button: **Xac nhan ban do va bat dau hoc**
(Vietnamese UI: Xác nhận bản đồ và bắt đầu học).

## P2 rollout

Review/apply migrations 0012 and 0013 with the existing migration runner on the
intended database. Start `app.main:create_content_app --factory`, not the legacy
P4 factory. Startup refuses to run without the session table. These changes were
validated on disposable local PostgreSQL databases; no shared database was migrated.
The existing P2 Storage, upload consent, queue and P4 gates remain in this factory.

## P5 request sequence

All browser calls use the existing `/api/backend` proxy on the same origin.
The proxy now allows `graph/review` and `graph/confirm` and carries only the opaque
HttpOnly learner cookie. The API key stays on the server.

1. `POST /api/backend/learners` with `{"display_name":"Demo"}` creates a learner
   AND its session. Keep the returned learner_id for existing learning requests.
   Existing UUID-only localStorage state cannot claim a learner session; offer
   explicit creation of a fresh anonymous learner if review returns401. Do not
   silently replace an existing learner or copy its progress.
2. `GET /api/backend/graph/review?subject=python-conditions`. Display the returned
   `graph` and retain its paired `graph_revision`. Use the response learner_id
   as the identity for subsequent learning calls. Reading never confirms.
3. Only on the button click, `POST /api/backend/graph/confirm` with
   `{"subject":"python-conditions","graph_revision":"<displayed 64-char hash>"}`.
   Do not send learner_id in this body. The server obtains identity from the cookie.
4. On200, proceed to placement using the existing learner_id/subject contract.
   On409, reload the review and require a fresh explicit click. Never automatically
   accept a newer revision. On401, prompt to create a session; on503, show retry.
5. Reloading review preserves confirmation. Duplicate confirm requests have the
   same response and one scoped DB row. Graph changes revoke the confirmation.

UI confirmation screen, placement -> next-item and the complete user journey
remain P5/P2 acceptance work. No browser E2E or live LLM acceptance is claimed.

## Validation

API: 1,443 tests pass, including seven new real-SQL HTTP tests. Ruff check/format
and mypy pass. Web: 50 tests pass, ESLint/typecheck and production build pass.
Models/storage are fakes in these tests; verification is never granted by hand.
See verifier-readiness.json for the separate read-only live-content audit.
