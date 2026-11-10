# Local development (PowerShell)

Run commands from the repository root unless a different directory is shown.
Install Docker Desktop with Linux containers, Git, Python and uv first. If `uv`
is not on PATH, use `python -m uv` in place of `uv` (install with
`python -m pip install uv`). `uv sync --python 3.12` downloads Python 3.12 if needed.

## P2 durable confirmation integration (local ptest2)

The new P2 application entry point is `app.main:create_content_app --factory`.
It binds P4 learning/tutor to P2 private upload storage and queue, using the durable
GraphConfirmations callback by default. Apply reviewed migration0012 to the private
local database before starting this factory. No public confirmation route or P1
DTO was changed; P3/P5 must connect an authenticated explicit learner action.

See [P2 confirmation handoff](../specs/p2-graph-confirmation/handoff.md) for the
service interface, graph snapshot/revision requirements, rollout and remaining
contract/UI work. Validation: 1,436 full API tests pass with real PostgreSQL;
Ruff/format/mypy pass. Storage/models in automated tests remain fakes. The local
0012 migration is applied; no learner was automatically confirmed.

## Configuration and startup

Copy the environment template yourself, only if `.env` does not exist:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

No provider keys are needed for A–B. The default database URL is
`postgresql://postgres:postgres@localhost:54322/nodetrail`. If your shell or `.env`
sets another URL, set this local URL explicitly in the current shell before
running migrations or the API. Never run the local acceptance checks against a
shared database.

```powershell
docker info --format '{{.OSType}}' # must print linux
docker compose up -d --wait db
Set-Location apps/api
$env:DATABASE_URL = 'postgresql://postgres:postgres@localhost:54322/nodetrail'
uv sync --locked --python 3.12
uv run python -m app.migrate
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, check `Invoke-RestMethod http://localhost:8000/health`
(`status=ok`, `db=ok`) and open <http://localhost:8000/docs>.

## Stop, restart and logs

Stop the API with Ctrl+C. At the repository root:

```powershell
docker compose logs --tail 100 db
docker compose down
docker compose up -d --wait db
```

`down` preserves the named database volume. Repeat migration and API startup
after restarting; migration should print `nothing (up to date)`. API logs appear
in its terminal. For occupied ports, inspect the owner before stopping anything:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,54322 |
    Select-Object LocalAddress,LocalPort,OwningProcess
Get-Process -Id <OwningProcess>
```

Stop the owning development process in its terminal, or choose another API port
and use it in the health/docs URLs. Changing the DB port also requires updating
Compose, `DATABASE_URL` and `TEST_DATABASE_ADMIN_URL` consistently.

**Destructive reset, separate from normal shutdown:** `docker compose down --volumes`
deletes local database data. Use only when intentionally resetting; then start
the database and reapply migrations.

## Verification

From `apps/api`, with the local database healthy:

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
```

The existing session fixture creates a unique `nodetrail_test_*` database and
drops it afterwards. It does not use the dev database. Its admin URL defaults to
`postgresql://postgres:postgres@localhost:54322/postgres`; an override must point
to a local server where the role can create databases. Tests use fake embeddings
and require no model download or LLM keys. CI treats mypy failures as warnings.

## Real ingest: waiting for P3 handoff

P3 must supply one chapter as `data/raw/thinkpython/chapNN.ipynb`, source URL,
license and `SOURCE_SHA` revision. Do not substitute generated fixtures for this
handoff. P2 runs the existing P1 pipeline after checking that migrations and
vector read/write code agree (currently vector(1024), chunks.url; migration 0003
has not been delivered).

From `apps/api`:

```powershell
uv sync --locked --extra embed
$timer = [Diagnostics.Stopwatch]::StartNew()
uv run python -m app.rag.ingest ../../data/raw/thinkpython
$timer.Stop()
$timer.Elapsed
```

The existing embedder uses bge-m3 on CPU. First use downloads roughly 2.3 GB.
Record download time separately from ingest time. Monitor the Python process's
peak working set in Task Manager and record peak RAM, elapsed time and chunk
count. Repeat ingest and verify that the count stays unchanged. At the repo root:

```powershell
docker compose exec -T db psql -U postgres -d nodetrail -c "SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding)) FROM chunks; SELECT title, author, license, url, version FROM sources; SELECT chapter_no, chapter, section, url FROM chunks LIMIT 5;"
```

Acceptance requires nonzero chunks, vectors of exactly 1024 dimensions, source
revision/license and chapter citations. Run tests again and confirm dev source
and chunk counts are unchanged. Do not ingest a chapter into an existing full
library: the current pipeline replaces all chunks for the same source title.

## Observed acceptance — 2026-11-07

- Docker Linux engine; Git 2.56.0; uv 0.13.7; uv-managed Python 3.12.16.
- Locked dependency sync passed. Migrations 0001–0002 applied; repeated run
  applied nothing.
- API `/health` returned `status=ok, db=ok`; `/docs` returned HTTP 200.
- Database recreated with `down` then `up --wait`, preserving both migration
  records. Dev chunks remained zero before and after tests/restart.
- 133 tests passed. Ruff lint and formatting passed; mypy passed (25 files).
- One dependency warning: Starlette deprecates using httpx with TestClient.
- No `.env` read or created. No real model/LLM calls. Real ingest, its timing,
  peak RAM and provenance acceptance remain pending the P3 chapter handoff.

## Phase C platform foundation

> Historical foundation record below. See the current integration update at the
> end of this file and `planv2.md` section 8 for the integrated checkout status.

Specification, implementation plan and tasks are in `specs/p2-local/`. They were
written manually before code; Spec Kit CLI/commands are not installed here.

Migration `0006_platform.sql` supplies independent `topic_jobs` and `llm_calls`
tables. It is verified on the temporary test database. Do not apply it to the
shared/integration database ahead of P1's 0003–0004 and P4's 0005: review/merge
those lane-owned migrations first, in TEAM.md order. Local dev has intentionally
not been migrated ahead of that handoff.

Implemented P2 routes: `POST /learners`, `GET /topics/cached`,
`GET /topics/{id}`, `GET /topics/{id}/events`. Snapshot JSON follows TEAM.md.
The stream sends a fresh snapshot on every connection, changed snapshots as
`message` events, and a `heartbeat` every 15 seconds. Terminal status closes the
stream; clients should stop reconnecting after ready/failed. Last-Event-ID is
accepted but history is not replayed; GET/current snapshot recovers current state.
Use a streaming fetch client to send `X-API-Key` (native EventSource cannot set it).

Set shell variables before API startup, without editing secrets:

```powershell
$env:API_KEY = '<your-local-shared-key>'
$env:CORS_ORIGINS = 'http://localhost:3000'
```

The key is optional for local development. When configured, all routes except
health require `X-API-Key`. CORS preflight remains available. Request responses
include `X-Request-ID`; topic responses include `X-Data-Fixture`. JSON logs use
Python's standard logging, requiring no added package. Langfuse is not initialized
and cannot block startup; actual per-LLM telemetry awaits P3's gateway.

After migrations are integrated, run the worker in a separate terminal:

```powershell
Set-Location apps/api
uv run python -m app.jobs.worker
# Explicit smoke-test mode only:
uv run python -m app.jobs.worker --fixture
```

P3 can enqueue with `app.jobs.queue.enqueue(conn, goal_vi, tier)` in its transaction.
There is no P3 POST /topics route yet. Tests enqueue fixtures directly. Claims
commit before work and use `FOR UPDATE SKIP LOCKED`. Missing P3 processing marks
real jobs failed; fixture ready is possible only with BOTH fixture=true on the
job and --fixture on the worker. Fixture jobs have no graph/items and are excluded
from cached topics. Do not use this fixture as an end-to-end demo.

Crash recovery limit: a process killed after claim leaves the job researching.
Inspect it before manually retrying; automatic leases/retry need the real P3
pipeline's idempotency contract. Database outages are logged and retried by the
worker; an SSE database failure closes the connection and clients must reconnect.

`app.services.learning` persists attempts, mastery and review cards using a
caller-owned transaction; it never runs grading or engine decisions. Serialize
updates for one learner/concept in the P3 orchestration transaction before doing
read/compute/write. Decision-trace persistence awaits P1's migration 0004 and
schemas; P3 route stubs and real gateway wiring remain pending. No real LLM calls
or fabricated content were added.

## Current integration update (2026-11-07)

P1 contracts and migrations 0003–0004, P3 routes/gateway and P5 web now exist in
this checkout. `app.main` mounts learning, topic/upload and tutor routes. Learning
routes use the durable P2 adapter; tutor/ask return 503 until a verified backend
is supplied. SSE emits `state` and `heartbeat`, superseding the `message` event
description above. Web currently uses snapshot polling.

P2 settings expose `EMBEDDING_BACKEND=local` by default, `TEI_URL=http://localhost:8080`
and optional secret-masked `TEI_API_KEY`. They are available to pipeline adapters;
API startup does not load a model or create an unused retriever. P1 CLI selection
uses explicit flags: `--embedder local`, or `--embedder tei --tei-url http://localhost:8080`.
Set `TEI_API_KEY` in the shell for an authenticated TEI endpoint. Do not assume
`EMBEDDING_BACKEND` in `.env` controls those CLIs. No TEI container was started here.

Worker/storage setup and pending real pipeline factory:
[`specs/p2-integration/worker-handoff.md`](../specs/p2-integration/worker-handoff.md).
Migration 0005 and real P4 generation/gates/item mapping remain pending. Do not
run the example factory path until the adapter exists. Dev/shared migrations are
still deferred; isolated tests apply all available migrations, including 0008.

Latest checks: 1172 API tests, Ruff lint/format and mypy passed; 38 web tests,
ESLint, TypeScript and production build passed. Development chunks stayed at zero.
No local raw book files exist despite acquisition receipts in `data/sources/`;
real ingest, elapsed time, peak RAM and vector/provenance acceptance remain open.

## P2 continuation: indexing, runtime and Spec Kit

`app.services.indexing.index_document` now connects P1 documents/chunking/embedding
to transactional P2 persistence. Identical retries preserve chunk IDs and avoid a
second embedding call. Changed snapshots require an explicit new source identity;
the adapter rejects replacement to protect existing citations. See the worker handoff
for its signature, CPU selection and the remaining P4/factory dependencies.

The worker now exports supported P3 search/provider/model settings from Settings to
process environment before constructing the pipeline factory. Shell values win;
credentials are secret-masked in Settings and are never logged by this forwarding.
The root `.env.example` includes `SEARCH_PROVIDER=brave` and all ten model ID names.
This is configuration support, not evidence of successful provider calls.

Spec Kit CLI `1.3.3.dev0` was installed from the official GitHub repository at
`c43849408ac0de2ca6a52f14eaae71449776057b`. Its `init --help` now uses
`--integration claude --script ps --non-interactive`. Initialization was run in a
temporary directory and its 27 non-memory scaffold files were installed here after
checking for collisions; the existing constitution was retained. No repository
branch was changed and no git commit was created. Generated Claude skills use
`/speckit-specify`, `/speckit-plan`, `/speckit-tasks` (hyphenated names).

`specify check` passed. `create-new-feature.ps1 -DryRun -Json -ShortName p2-smoke`
computed `001-p2-smoke` without creating a spec or changing `ptest`. This CLI version
stores feature selection in `.specify/feature.json` for actual creation; do not assume
it switches a Git branch. Existing manually written P2 specs remain the active work.

PowerShell smoke command when local script execution is restricted:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .specify/scripts/powershell/create-new-feature.ps1 -DryRun -Json -ShortName p2-smoke 'P2 scaffold smoke check'
```

Web verification on Windows can use `npm.cmd run lint`, `npm.cmd run typecheck` and
`npm.cmd test` with the installed node_modules when pnpm is unavailable. This invokes
the same package scripts without installing packages or changing the pnpm lockfile.
