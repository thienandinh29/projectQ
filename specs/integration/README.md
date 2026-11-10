# Local integration: P1 + P2 + P3 + P4 + P5

This branch merges the published work into one checkout; it is not a completed H7
runtime. No changes have been pushed to main or any remote lane. P4's original local
files are preserved in the safety stash named `P4 local checkpoint before integrating
P1 P2 P3 P5` (retained, not popped/deleted).

## Included work and integration fixes

- P1 via origin/main (5245e56): contracts, engine, retrieval, migrations 0003/0004,
  library ingestion and evaluation. P1's additional ready/model/evaluation branches
  are already included by that main history, so they are not merged twice.
- P2 origin/p2/platform (651bc7b): platform app, persistence helpers, queue/worker,
  logging and migration 0006.
- P3 origin/p3 (f8239ee): gateway/providers/search, research pipeline, uploads,
  route factories, migration 0007 and library manifests.
- P4: local golden topics, generation, verification, tutor, metrics and migration 0005.
- P5 origin/p5 (d45cc3e): existing web UI and mock/API client, retained.

The P3 dependency merge conflicted only in pyproject.toml and uv.lock. All declared
requirements were retained, including google-auth and runtime httpx, and uv regenerated
the combined lockfile (109 resolved packages). No new feature dependency was invented.

P4 adapter task names now map to graph/items/tutor/verify. The adapter consumes P3's
actual Completion.value/route, and places the actual generator family in request-local
verification_scope, outside all model-visible payloads. Known gpt-family agent-authored
golden drafts may be checked by a configured Gemini/Claude verifier; unknown families
are blocked. Tests run actual gateway orchestration with a fake provider, not paid calls.

P4 content/integration.py exports canonical P1 KnowledgeGraph/ItemSet values and gated
P3 items. Pending/stale items are filtered before crossing this adapter. The P2 app now
mounts all ten P3 routes and accepts explicit backend adapters through create_app kwargs.
Without adapters those routes return 503; tests.api.preview is never imported by it.

Public conventions now match P1: answer is a zero-based integer (labels are rejected),
hints_used defaults to zero, last_answer is an optional zero-based integer, hint levels
are 1..4 in HTTP. P4 currently implements levels 1..3 only; a level-4 request must be
withheld by its backend adapter rather than inventing a hint. P3 uploads use `file`
and 20,000,000 bytes. P5 API config defaults now use those confirmed values. P2 stores
integer percent in DB but snapshot() normalizes progress to P1 TopicState's 0..1.

P5 now reads P1's real fixture files in contract tests. Trace prior/posterior can be
null, and nullable evidence is treated as absent; the UI displays 'Không áp dụng'
rather than inventing zero mastery. Existing mock demonstrations remain labelled.

## Current P4 runtime completion (uncommitted working tree)

The adapters previously missing below now exist in app/content/repository.py,
ports.py, backends.py and runtime.py. They reuse P2's pool/queue/persistence, P1's
engine/chunker and P3's gateway/TopicPipeline/routes. Worker --pipeline connects the
committed claim to P4 ports. Start app.content.runtime:create_app --factory to bind
the existing dependency ports; default app.main still intentionally has no adapters.

Candidate app/content/sql/0008_p4_runtime.sql supplies the required additive schema
and transactional invalidation/cache/audit triggers. It is outside the migration
glob and NOT applied. Historical0005 remains unchanged. P2 must review/promote it,
confirm numbering and run isolated DB/rollback checks.

The learner adapter excludes pending/stale items and partial/failed topic jobs;
tutor releases only independently verified hints with actual citations. See
[the current handoff](../../apps/api/app/content/HANDOFF.md),
[demo commands](../../apps/api/app/content/runtime-demo.md) and
[fresh validation](../../apps/api/app/content/runtime-validation.json).

H7 is still NOT demonstrated: real-model verified count0; no real generation,
DB import/migration or live learning/tutor run. DATABASE_URL and all model routes/
credentials are absent. PostgreSQL127.0.0.1:54322 times out, including outside
sandbox. No local Docker/pg_ctl/psql available; WSL not installed. File upload
Storage/consent remains P2/P3 work; Free Python indexed-source path is independent.
OpenStax sources remain blocked. P5 remains mock by default; API browser tests await
services/configuration. exam-plan/tutor-ask are explicitly unavailable.

## Historical pre-runtime missing-pieces report

The following records the earlier integration checkpoint; the current adapters
above supersede its missing-code statements. Environment blockers remain.


P2's branch provides save_attempt/save_mastery/save_review and queue primitives, but
does not implement/register concrete LearningBackend, TopicsBackend or TutorBackend.
It also lacks learner/placement session storage orchestration and a DB-backed adapter
for P1 algorithms. Default mounted routes therefore intentionally return 503.

The worker still has its original explicit fixture/missing-pipeline handling. P3's
TopicPipeline is present, but its PipelinePorts (indexed source selection, persistent
chunks, graph/item generation and save callbacks) have not been bound into that worker.
topic_jobs also lacks persisted mode/upload_id fields needed for full deep/upload jobs.
Do not report queued->ready as live content until those concrete pieces exist.

No PostgreSQL server was reachable at localhost:54322, including a retry outside the
sandbox. No migrations were executed. Keep 0001..0007 in order and let P2 review 0005
on a throwaway DB. No credentials were opened or model/search calls performed. The
45 golden items remain needs_review; OpenStax topics retain their source-use restriction.

Thus this handoff establishes source/contract/route integration, not real DB learning,
live generation, verified golden fallback, or H7 acceptance. Frontend remains mock by
default. Do not turn on API mode expecting learning to work until adapters are bound.

## Validation

From apps/api with project dependencies:

```powershell
uv run pytest --no-db -q
uv run ruff check . ../../scripts/build_library.py ../../data/guardrails/build_cases.py
uv run ruff format --check . ../../scripts/build_library.py ../../data/guardrails/build_cases.py
uv run mypy . ../../scripts/build_library.py
```

--no-db is an explicit new local-test flag, skipping only tests whose fixture graph
requires database_url. CI/default pytest still runs those tests and fails if DB is
missing. The earlier explicit DB attempt produced 2 errors with connection timeout,
not passing migration tests. See validation.json for final counts.

From apps/web: npm.cmd run lint, npm.cmd run typecheck, npm.cmd test, npm.cmd run build.
The OpenAPI snapshot is generated from app.main.create_app, not tests.api.preview.
P5's runtime decoders remain in place even when generated types are used.
