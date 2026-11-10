# P4 material import / confirmation / verifier handoff

Code changes: index allocation uses actual mapped DB source IDs. Existing chunk
UUID/index are retained; new UUIDs receive max stored index+1 per source. Subject
and source row locks serialize concurrent P4 retries. P2 index_document also locks
the source through its upsert; future writers must follow that protocol. Book
identity remains `(subject_id,title)`, with one deterministic metadata upsert per
book. Each chunk preserves its original Source record and source_uri, so separate
chapter provenance survives canonical book mapping. No constraint was removed.

Regression DB coverage: `tests/content/test_material_database.py` tests shared book
mapping, stable UUID/index/provenance on reordered replay, new chunks, concurrent
replay, transaction rollback and successful retry. These are real PostgreSQL tests,
not simulated evidence. PostgreSQL CI for code commit b2f8190 passed:
https://github.com/thienandinh29/SenaEmpire36/actions/runs/42386105551
API job's full `uv run pytest -q`, Ruff/format and web job all succeeded. No exact
CI test-count is inferred from job status. P2's own import run remains pending.
Local full checks:1303 passed,116 DB tests skipped by explicit `--no-db`; Ruff,
format and strict mypy passed. Local skips are not counted as DB passes.

## P2: import golden material twice without overwriting item verification

Use only P2's private development database, with its reviewed migrations already
applied and `/health` returning db:ok. The command does not migrate, delete rows,
replace items or invoke embeddings/models. From apps/api, set private DATABASE_URL
without posting it, then explicitly acknowledge the target:

```powershell
$env:P4_CONFIRM_PRIVATE_DEV_DATABASE = 'yes'
@'
import json, os
from pathlib import Path
from urllib.parse import urlsplit
from app.config import get_settings
from app.content.artifacts import load_topic
from app.content.repository import Repository
from app.db import create_pool
settings = get_settings()
target = urlsplit(settings.database_url)
assert os.environ.get('P4_CONFIRM_PRIVATE_DEV_DATABASE') == 'yes'
assert target.hostname in {'localhost', '127.0.0.1', '::1', 'db'}, 'Private local dev DB only'
with create_pool(settings.database_url) as pool:
    repository = Repository(lambda: pool)
    repository.require_schema()
    snapshots = []
    for iteration in (1, 2):
        ids = []
        for path in sorted(Path('../../data/golden').iterdir()):
            if not (path / 'sources.yaml').exists():
                continue
            sources, chunks, _, _ = load_topic(path)
            repository.save_material(path.name, sources, chunks)
            ids.extend(c.chunk_id for c in chunks)
            with repository.transaction() as conn:
                actual_sources, actual_chunks = repository.material(conn, [c.chunk_id for c in chunks])
                assert actual_chunks == chunks
                assert {s.source_id:s for s in actual_sources} == {s.source_id:s for s in sources}
        with repository.transaction() as conn:
            rows = conn.execute('select id,source_id,chunk_index,source_uri,content,p4_metadata from chunks where id=any(%s) order by id', (ids,)).fetchall()
            assert len(rows) == len(set(ids))
            assert len({(r[1],r[2]) for r in rows}) == len(rows)
            snapshots.append(rows)
        print(json.dumps({'iteration':iteration, 'chunks':len(rows)}))
    assert snapshots[0] == snapshots[1], 'Retry changed stable chunk data'
    print(json.dumps({'two_imports_equal':True,'duplicates':False}))
'@ | uv run python -
```

Then P2 can resume its existing `scripts/index_demo.py --build-index`; this remains
P2's indexing task, not evidence that P4's verifier or learning path is accepted.
For isolated PostgreSQL regression tests use:

```powershell
uv run pytest tests/content/test_material_database.py tests/content/test_runtime_database.py -q
```

These fixtures create/drop their own nodetrail_test_* databases through the local
test admin URL, never use an existing shared database.

## Shared Gemini diagnosis for P2 / P3

No new provider/model selected. Fixed manifest:
`data/guardrails/gemini-shared-request.json`. Fingerprint:
`c119eca84d2d116ecf330a829e5bab7b0596dcc74c54a4367c107beb72b95fc8`.
This hashes provider, v1beta, exact model and actual JSON HTTP request (system/schema,
question/options/cited chunk, generation parameters). No candidate answer is sent.
The diagnostic lists credential-accessible models and checks generateContent.
Provider90s timeout is explicitly scoped; all ordinary calls retain30s. No external
P3 review or P2 run has been claimed. P3 should review the scoped timeout helper.

Each machine runs at most once, with a fresh machine-specific output path:

```powershell
uv run python -m app.content.shared_diagnostic --output ../../data/guardrails/gemini-shared-p2.json
```

The P4 run is saved in gemini-shared-p4.json. It received HTTP429 in0.797s:
RESOURCE_EXHAUSTED, quota ID GenerateRequestsPerDayPerProjectPerModel-FreeTier,
quotaValue20, metric generativelanguage.googleapis.com/generate_content_free_tier_requests,
model gemini-3.8-flash, location global; provider retryDelay60782s. Request ID/header
Retry-After were absent. This is explicit daily Free Tier quota exhaustion for the
credential's project, not an invalid-key conclusion. The project ID is not derivable
from the local key. A model-list response confirmed generateContent support.
Do not bypass project quota with another key. Owner can inspect AI Studio project's
Usage/Rate Limits and billing/tier; no service or paid billing was enabled.

If P2 succeeds while P4 times out, compare the manifest fingerprint first, then
network/proxy/egress and configuration. If both fail, inspect their actual provider
errors; do not infer a key/model failure from a timeout.

## Real verification / graph confirmation acceptance remains pending

If P2 diagnostic succeeds, its output is a resumable checkpoint with the successful
Item/audit saved immediately. Continue that SAME checkpoint (skips current verified):

```powershell
uv run python -m app.content.verify_batch ../../data/golden/python-conditions --checkpoint ../../data/guardrails/gemini-shared-p2.json --interval 15 --retries 2
```

The runner records 20 paired cases, actual calls, reused blind results and separate
infrastructure failures. If the diagnostic fails, do not continue batch; preserve
receipt/cooldown. Target remains >=6 verified/3 concepts/accepted prerequisite chain.
Current P4 real results:0 verified with current audit,0 covered concepts;20 cases
still unfinished. Human review pending; no mock is counted as real verification.

See graph-confirmation-handoff.md: production needs the agreed P2/P3/P5 confirmation
operation and persistent learner/topic/revision record. No competing route/button
was introduced. Changed graphs require a fresh confirmation; placement/practice/
tutor fixtures explicitly approve only the intended triple, while negative tests
retain409. E2E must confirm the displayed graph revision before learning/tutor.
