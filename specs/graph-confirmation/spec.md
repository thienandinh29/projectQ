# Graph review and explicit confirmation

P3 HTTP boundary on P2 commit 657c09f, descending from the agreed 3c3a8e0 baseline.
Uses P2 GraphConfirmations and migration 0012; no duplicate confirmation store.
Use `app.main:create_content_app --factory`.

`POST /learners` retains its learner_id response and issues an opaque HttpOnly,
SameSite=Lax session cookie (Secure over HTTPS). Migration 0013 stores only its
SHA256 hash with a 30-day expiry; RLS exposes no browser policies. Possession of a
learner UUID or the shared server API key does not grant a confirmation identity.
Existing learners need a new anonymous session; no UUID-only session claiming.
This supplies confirmation identity, not a complete account/login system. Existing
learning endpoints keep their existing learner_id contract.

`GET /graph/review?subject=python-conditions` returns:
`{learner_id, subject, graph_revision, graph, confirmed}`.
Identity comes from the session, regardless of a learner_id query parameter.
The public KnowledgeGraph and revision are derived from the SAME P2 snapshot.
GET never confirms. It may return an old snapshot during a concurrent graph edit;
POST always compares against the locked current graph before accepting it.

`POST /graph/confirm` accepts ONLY `{subject, graph_revision}`.
Returns `{learner_id, subject, graph_revision, confirmed:true}`.
Missing/expired/invalid session:401; malformed body (including learner_id):422;
missing topic:404; stale revision:409; unavailable configuration/SQL:503.
The existing shared API key requirement also remains active.

Confirmation is scoped to learner + subject + canonical P4 graph revision.
Retries have the same public result and one database row. P2 may refresh the
internal confirmed_at timestamp. Graph edits revoke acceptance, including edits
that later restore the old content. No item verification or mastery is granted.
P4 placement, practice and tutor continue to enforce their existing callback.
