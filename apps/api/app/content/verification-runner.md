# P4 sequential verification handoff

Scope: use the existing P3 gateway and P4 blind verifier; add safe checkpoints,
bounded retries, provider Retry-After classification and paired evaluation. No DB
migration or learner publication is performed by this command.

From `apps/api`, with the current root `.env` configured:

```powershell
.venv/Scripts/python.exe -m app.content.verify_batch ../../data/golden/python-conditions --checkpoint ../../data/guardrails/python-conditions-checkpoint.json --interval 15 --retries 2
```

This command reads the existing golden authorship metadata unchanged. These are
agent-authored golden questions, not evidence of live DeepSeek generation.
Gemini receives only question/options/cited chunks through `blind_request`.
The backend compares the independent response to the candidate answer.

The checkpoint contains full validated Item results under `items[id].result`,
fingerprints, audits, actual gateway identity, provider attempts and a summary.
P2 should deserialize results with `Item.model_validate` and check
`is_currently_verified(item, current_chunks)` before using the existing repository
import path. Never import a result based only on its stored status. Unfinished
questions remain in the original golden file as needs_review.

Resume reuses only currently verified results with identical item/source/config.
The summary's `elapsed_seconds` covers the latest invocation; attempts and token
totals are cumulative across checkpoint resumes. Unknown token usage/cost is null.
Expected evaluation labels are agent labels; human review is pending.

The 20 evaluation records pair 10 unchanged questions with 10 flipped backend keys.
Question/options/chunks remain identical, so one independent verdict is reused for
both keys. The receipt reports actual calls separately from reused results.
Infrastructure failures are unfinished cases, not correct detections or false alarms.

Retry stops on classified daily/zero quota or configuration failures. Unknown 429
is treated as transient with a finite retry budget, not assumed to mean rate limit.
Provider raw bodies, key values and user-specific error text are never persisted.

Completion requires >=6 current verified items, >=3 concepts and an edge/chain in
the accepted graph. Human map acceptance is distinct from the structural golden DAG;
this runner does not pretend a learner or a teammate accepted the graph.

## Infrastructure clarification, 2026-11-07

The existing checkpoint stores 64589.0 **seconds** (17h56m29s). Its saved resume
instant is 2026-11-08T07:59:46.168208Z, or 2026-11-08 14:59:46 in Vietnam.
The previous Vietnamese punctuation "64.589 seconds" meant 64,589 integer seconds,
not 64.589 fractional seconds. The old raw HTTP response was not retained; the
source header/body field and exact quota ID/value cannot be reconstructed. The
classifier recorded quota (daily quota ID or zero quota value), so this is not
evidence that every 429 means a per-minute rate limit. Future errors retain safe
quota ID/value and delay-source metadata without raw bodies/secrets.

No new live API call was made during this clarification. Invoking the runner before
the saved time returned its prior summary, made no request, and left the checkpoint
SHA256 unchanged. After that time, probe one item and inspect its saved audit first:

```powershell
.venv/Scripts/python.exe -m app.content.verify_batch ../../data/golden/python-conditions --checkpoint ../../data/guardrails/python-conditions-checkpoint.json --max-items 1 --retries 0
```

Only if this produces a current verified result, use the full sequential command
above. A new quota response stops the batch and persists its next permitted time.
The time is a minimum retry time, not a guarantee that quota has recovered.

Postgres check: this process runs on the Windows host, not in a container. API and
worker both use P2 Settings.database_url; current configured endpoint is localhost:
54322. TCP attempts to localhost:54322, 127.0.0.1:54322 and 127.0.0.1:5432 timed
out. No Docker/psql/pg_isready executable or PostgreSQL/Docker Windows service was
found in this session. This does not prove Docker is absent from every location.
No migration was run. On the host, start the repository's private dev DB with
`docker compose up -d db` once Docker is installed/running. Compose publishes
54322 on the host to db:5432. A future API/worker container on that Compose network
must address db:5432; localhost inside it refers to the container itself.

Owner actions: check Gemini project's model quota and billing/entitlement in AI
Studio/Cloud console; the exact previous numeric limit is unknown, not inferred.
Restore/start the private local Postgres service. Keep P4 blocked until the live
verification coverage and paired evaluation have valid results.
