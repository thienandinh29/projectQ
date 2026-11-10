# P4 runtime demo (PowerShell)

Current business pass: use `python -m tests.content.learning_loop` for the offline
scenario instead. The historical live commands below also require a trusted
per-learner/revision confirmation callback wired by P2/P3/P5; without it learning
and tutor now return409. Model/DB availability alone no longer enables teaching.
No new provider, migration or paid call is requested by the business pass.

Run from D:/SenaEmpire36/apps/api with the locked project dependencies.
Use uv run python (or this session's temporary Python path recorded in validation).
These are reproduction commands, NOT a record of a completed live run.

## Environment and disposable DB

```powershell
uv run python -m app.content.demo environment
docker compose -f ../../docker-compose.yml up -d
uv run python -m app.content.demo prepare-local
```

prepare-local uses TEST_DATABASE_ADMIN_URL or the repository's local54322 admin
default; it creates a new nodetrail_test_p4_* DB and applies0001–0007 plus candidate0008.
It refuses remote hosts; no existing dev/shared DB is migrated. P2 must review the
candidate before use. Set DATABASE_URL in the process to that new DB using your local
credentials (not printed by this command). Do not use a shared DATABASE_URL.
To discard: drop only that exact generated test DB after stopping worker/API.

Set actual gateway configuration in the process (no secrets in commands/history):
Free path: OPENROUTER_API_KEY, OPENROUTER_FREE_MODEL (Gemini family),
OPENROUTER_VERIFY_MODEL (Claude family). P3 must confirm reachable exact IDs.
Alternatively use configured Vertex/Bedrock routes. Model IDs containing ':free'
are rejected by current P3 policy even when the route tier is Free.

```powershell
uv run python -m app.llm.smoke --live --provider openrouter --tier free --task items
uv run python -m app.content.demo import-golden ../../data/golden/python-conditions
uv run uvicorn app.content.runtime:create_app --factory --port 8000
```

All imported items are needs_review; expected placement before verification is503.
Open a second PowerShell, retaining the same DATABASE_URL:

```powershell
$base = 'http://127.0.0.1:8000'
$learner = Invoke-RestMethod "$base/learners" -Method Post -ContentType 'application/json' -Body '{"display_name":"P4 local demo"}'
$selectionBody = @{learner_id=$learner.learner_id;subject='python-conditions'} | ConvertTo-Json
Invoke-RestMethod "$base/placement/next" -Method Post -ContentType 'application/json' -Body $selectionBody
```

A503 at this stage confirms pending golden cannot be learned. It does not validate
a model or content quality.

## Mode A: imported golden, then actual model verification

```powershell
uv run python -m app.content.demo verify-golden ../../data/golden/python-conditions --tier free --output ../../data/python-verified.local.jsonl
```

This uses agent-authored drafts and independent actual gateway verification; it is
NOT live pipeline generation. Audit output can contain needs_review; count printed
servable, never assume15 passed. Do not edit status to verified. OpenStax commands
are blocked by source-use permissions.

Retry placement after at least one suitable verified item exists. Use the local
golden key ONLY in this developer smoke script to deliberately choose a wrong option;
the API learner response does not contain it:

```powershell
$step = Invoke-RestMethod "$base/placement/next" -Method Post -ContentType 'application/json' -Body $selectionBody
$golden = Get-Content ../../data/golden/python-conditions/items.jsonl | ForEach-Object { $_ | ConvertFrom-Json }
$internal = $golden | Where-Object id -eq $step.item.id
$wrong = 0
while ($internal.options[$wrong].correct) { $wrong++ }
$answer = @{learner_id=$learner.learner_id;item_id=$step.item.id;answer=$wrong;hints_used=0} | ConvertTo-Json
Invoke-RestMethod "$base/attempts" -Method Post -ContentType 'application/json' -Body $answer
$hint = @{learner_id=$learner.learner_id;item_id=$step.item.id;level=1;tier='free'} | ConvertTo-Json
Invoke-RestMethod "$base/tutor/hint" -Method Post -ContentType 'application/json' -Body $hint
```

Expected: correct=false plus actual engine traces; hint response contains only
hint_vi/citations. A503 means generation/verification unavailable or rejected; it is
not a successful tutor demo. Level2/3 may progress; level4 remains withheld.
Confirm source citations match actual chunks. Do not infer18/20 rubric success.

## Mode B: actual pipeline generation from indexed Python source

Import-golden indexes sources/chunks even before verification. Submit a fresh job:

```powershell
$job = Invoke-RestMethod "$base/topics" -Method Post -ContentType 'application/json' -Body '{"goal_vi":"Học điều kiện Python","mode":"quick","tier":"free"}'
uv run python -m app.jobs.worker --pipeline
```

Watch the existing topic status/SSE endpoints documented by /docs.
Only after ready/items_ready, use its subject_slug with placement/next and then
attempts/hint. This generates a new job-specific graph and >=6 question drafts and
verifies them through real models. If insufficient verified questions, job fails
and partial content remains hidden. Quick deadline is P3's60 seconds; timeout is a
blocked result. Requeue/reclaim of a failed job is P2 policy, not an extra P4 queue.
Retrying the same claimed job uses stable IDs. A new job intentionally has a new subject.

## Tests and frontend

```powershell
uv run pytest tests/content tests/guardrails tests/tutor tests/api tests/research tests/llm tests/uploads --no-db -q
uv run pytest tests/content/test_runtime_database.py -q
```

The second command requires local PostgreSQL and creates/drops its own isolated DB;
model responses in those tests are fake. Never label them real-model verification.

For P5 use server environment NODETRAIL_DATA_MODE=api,
NODETRAIL_API_URL=http://127.0.0.1:8000, NODETRAIL_ANSWER_ENCODING=index0,
NODETRAIL_HINT_FIRST_LEVEL=1; keep private API secrets server-side.
File uploads remain blocked pending P2 Storage/consent; no upload success claim.
Default frontend stays mock. API shape is unchanged, so no generated type edits here.
