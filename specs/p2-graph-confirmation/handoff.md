# P2 -> P1/P3/P5 durable confirmation handoff

## Delivered P2 backend

Use `app.main:create_content_app --factory` for the integrated P2 entry point.
It uses P4 learning/tutor, P2 TopicsService/private Storage/queue and, by default,
GraphConfirmations backed by migration0012. The existing P4 factory is unchanged.
No model, engine, public schema or existing route was modified.

The application exposes `app.state.graph_confirmations`. Its synchronous methods
are intended for P3's authenticated boundary (call through asyncio.to_thread):

```python
service = request.app.state.graph_confirmations
graph, revision = await asyncio.to_thread(service.snapshot, authenticated_learner, subject)
# P3 projects the existing learner-safe public graph from THIS graph snapshot.
# P5 displays that graph and keeps the paired revision until explicit acceptance.
await asyncio.to_thread(service.confirm, authenticated_learner, subject, displayed_revision)
```

The snippet describes two separate user actions, not automatic confirmation after
a graph read. Do not serialize P4's private model directly. Do not fetch a new
revision separately from the graph the learner actually saw. Do not infer identity
from a learner UUID supplied by the browser or treat the shared API key as
per-learner identity. The current authentication boundary still needs that wiring.

`snapshot` returns the current validated P4 Graph plus its existing canonical
revision. `confirm` checks learner/topic existence, locks learner then subject,
rejects stale revisions with409 and persists one scoped record. Invalid input422,
missing learner/topic404, unavailable graph503. Graph changes delete acceptance,
including changing back to a previously accepted graph. Identical graph replay
preserves acceptance. The callback checks the stored and current revisions.

Confirmation does not change item status, jobs, BKT, placement or mastery. Tests
prove confirmed-but-unverified content still returns503 and verified synthetic
content becomes selectable only after explicit acceptance. P4 rechecks its callback
for both learning and tutor. Verification audits in tests use fake models.

The callback opens a short independent SQL connection because P4 invokes it while
holding a shared-pool transaction; a second pool checkout could deadlock when all
five pool slots are held by concurrent learner requests. A SQL regression fills
the shared pool and verifies that the callback still completes.

## P1/P3/P5 still required

- P1/P3 approve the public contract that ties the displayed graph and revision in
  one response, and accepts explicit confirmation of that revision. No competing
  endpoint/DTO has been introduced by P2; existing P1 contracts stay unchanged.
- P3 obtains the authenticated learner at the boundary and invokes this service.
  Future routes must return409 for stale acceptance and require fresh review.
- P5 displays the paired graph, sends acceptance only from the learner action and
  handles changed-revision409. Add the agreed operation to its proxy allowlist.
- P5 also completes placement -> next-item practice. P3/P4 complete real verified
  content. New upload/deep embeddings still need their P3/P4 port connection.

## Local startup and rollout

From the ptest2 worktree's apps/api directory, after validating the private local
database URL and the disposable SQL tests:

```powershell
$env:DATABASE_URL = 'postgresql://postgres:postgres@127.0.0.1:54322/nodetrail'
.venv/Scripts/python.exe -m app.migrate
# Configure API_KEY, or opt into localhost-only development explicitly:
$env:ALLOW_UNAUTHENTICATED_LOCAL_DEV = 'true'
.venv/Scripts/python.exe -m uvicorn app.main:create_content_app --factory --host 127.0.0.1 --port 8012
```

Startup validates both P4 schema and migration0012 and closes the platform pool
if validation fails. RLS has no browser-facing policies: confirmation writes are
server-only. Do not apply this development rollout to a shared database implicitly.

Private file uploads additionally require configured Supabase Storage credentials,
an existing private bucket, demo mode and the existing accepted notice. The P2
factory connects that existing service; tests use fake object storage, not a live
bucket. Failed metadata writes remove only the new object.

Rollback can use the previous factory (which continues to deny unconfirmed
learning). Leave the additive private table unused rather than deleting records.
No blanket acceptance or real-model verification is created by migration/startup.
