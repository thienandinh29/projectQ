# P4 handoff — runtime completion

## Current business-alignment pass (p4, after bc7da3e)

The user's latest product clarification is recorded in [business.md](business.md),
including the business/code/gap/mismatch/owner matrix and unresolved rule decisions.
This pass does not call models, inspect credentials, connect DB, change schema,
migrate, select providers or edit P1/P2/P3/P5 source. Changes remain local/uncommitted.

P4 corrections: trusted per-learner graph-confirmation callback (default409 for
teaching/tutor; map still viewable), explicit structural-chunk evidence exclusion,
in-progress hint versus submitted-feedback separation, diagnostic wording and
existing FSRS concept reviews for wrong answers. Prompt version3 requires fresh
hint checks. No HTTP contract was extended: P2/P3/P5 still need confirmation and
post-submission feedback integration. The default factory no longer permits
teaching solely because jobs/items are ready/verified.

Use `python -m tests.content.learning_loop` from apps/api for the new explicitly
simulated Python loop. It uses real P1 engine functions, fake gateway and in-memory
confirmation/review state; Q/A flashcard is fixture-only. Source golden files stay
needs_review. Exact fresh results: business-validation.json. Prior DB/model counts
below describe earlier probes, not new execution. Live demo instructions below
are historical and require the new confirmation integration before teaching.

## Previous runtime delivery (committed/pushed as bc7da3e on p4)

Checkout confirmed: integration/p1-p5, base HEAD 2128cb2. This session's changes
remain uncommitted. No merge, push, reset, shared migration or real model call.
No applicable AGENTS.md found; TEAM/P4/contracts/integration/gateway read.

## Current implementation

- repository.py: P2 pool/transactions/tables; durable chunks, graph, choices,
  misconceptions, stable external IDs, audits, revision checks and hint cache.
- ports.py: P3 PipelinePorts and TopicPipeline; P1 chunker; actual P3Gateway;
  existing topic_jobs progress/trail. Same-job retries reuse stable slots. Pending
  outcomes persist, but ready requires six current verified questions and save.
- backends.py: existing learning/topics/tutor protocols, P1 placement/BKT/path/
  remediation/FSRS, P2 persistence, sessions and decision traces. Stale and
  non-pending attempts fail. Regular learning selects unattempted items.
- runtime.py: explicit factory binds adapters into P2's existing app/pool/routes.
  Default app.main is unchanged. Worker --pipeline invokes these P4/P3 ports
  after claim commits. The small worker hook needs P2 review.
- answerability.py: opaque choice-N aliases and strict blind whitelist; actual
  post-fallback model family; prompt v2; audit history retained on invalidation.
- hints.py: Vietnamese levels1–3, answer/misconception/history, independent
  verifier, disclosure checks, source citations, audit/cache. Only released hint
  and citations reach learner. Failures503; stale context409. Level4 withheld.
- pipeline.py: source permission checked even with existing graph; bounded
  verification concurrency; deterministic namespaced item IDs.
- demo.py: environment report, disposable-local DB preparation, pending golden
  import and actual gateway golden verification. No manual verified switch.

For topic-* subjects, learner selection/get-item/attempt/tutor require current
verification AND a ready job with items_ready; partial/failed batches are hidden.

## Database proposal — not applied

Historical0005 is unchanged. Migrations0001–0007 already exist. Candidate
[sql/0008_p4_runtime.sql](sql/0008_p4_runtime.sql) stays OUTSIDE automatic migration
discovery for P2 review/promotion and numbering check. It adds missing unique
external_id/misconceptions.slug, option position, job mode/upload_id, metadata,
revision, audit/cache/session tables and transactional invalidation triggers for
item/option/chunk/source/concept-citation/misconception changes. Old audits survive.
New private tables use RLS without browser policies; backend needs privileged access.

This SQL has NOT executed on PostgreSQL. Trigger behavior, extension compatibility,
locking and migration rollback still require P2's disposable-DB review. Tests create
and drop isolated nodetrail_test_* databases only. Deployment rollback must accompany
P2's promotion; historical0005 rollback remains rollback_0005.sql.

## Actual runtime and blockers

Real-model verified questions: **0**. No real pipeline generation, DB import,
migration, learner/API/tutor end-to-end run or live gateway smoke call occurred.
The runnable offline tests use fake models, including the actual P3 orchestration.

DATABASE_URL is absent; local127.0.0.1:54322 timed out inside and outside sandbox.
No Docker/pg_ctl/psql found; WSL reports not installed. No DB was created.
P3 configuration reports zero configured model routes. Credentials are absent;
root .env was not read and no secret values were printed.

| Owner | Still required |
|---|---|
| P2 | Local PostgreSQL with vector extension; review/promote/test0008 and worker hook; migration rollout/rollback and job reclaim/requeue |
| P3 | Model IDs/credentials and live gateway tests including fallback identity; search credentials for Deep |
| P2/P3 | Private Storage for uploaded file bytes and explicit upload model-use permission port |
| P5 | API-mode configuration against runtime factory, then desktop/mobile browser flow; default frontend remains mock |
| P1/P4/team | Live evaluation, retrieval labels, human review and source permission resolution |

Minimal Free OpenRouter path requires OPENROUTER_API_KEY,
OPENROUTER_FREE_MODEL (Gemini), OPENROUTER_VERIFY_MODEL (Claude). Use real IDs whose
family agrees with P3 routing. Vertex alternatively needs GOOGLE_CLOUD_PROJECT,
ADC/GOOGLE_APPLICATION_CREDENTIALS and VERTEX_*_MODEL; Bedrock needs AWS_REGION,
credentials/profile and BEDROCK_*_MODEL. Pro Claude tutor needs an independent Gemini
verifier route. Different provider/model names alone do not establish independence.

Linked document metadata persists; uploaded file bytes return503 until P2 Storage
exists. Worker upload processing currently blocks because explicit consent has no
port (default false). This does not block Quick Python from indexed golden sources.
Deep code ports exist but have no live search validation. exam-plan and tutor/ask
remain503, outside the requested P4 hint path. Automatic job retry/reclaim stays P2's.

## Data and remaining P4 evaluation

Existing3 topics ×15 MCQs =45; 15 chunks. Python can be processed independently.
OpenStax fractions/cell-basics retain model_ingestion_allowed=false; obtain
permission or replace sources. Existing agent review is recorded in review.md;
this session does not claim fresh source review or any human approval.
Human reviewer/time fields stay blank. All45 on-disk golden questions remain pending.

Existing evaluation:50 item cases (44 originals +6 planted variants),20 candidate
hints, agent expectations and70 pending human-label templates. No human quality
metric or18/20 tutor acceptance result. TEAM deliverables still pending:20 held-out
cases based on truly verified items (10 flipped,10 untouched), >=36 planted cases,
>=20 Vietnamese retrieval judgments and metrics-runner alignment with P1 evalkit.
Do not treat six planted variants as36 or agent expectations as human labels.

## Fresh verification and reproduction

Exact fresh counts/environment/errors are in runtime-validation.json; older
validation.json and the notes below are historical. Focused tests cover worker
orchestration/retry, blindness/fallback, pending/stale gates, audit/cache, hint
release, metrics and golden structure. Real DB tests are explicitly separate.

See [runtime-demo.md](runtime-demo.md) for setup, pending-item check, golden
verification, wrong answer/hint and worker generation commands. Import+verify golden
and pipeline generation are distinct modes. H7 acceptance is still blocked.

---

## Historical pre-runtime handoff (superseded above)


Integration update: the original notes below describe the pre-merge P4 checkpoint.
P1/P2/P3/P5 are now present on integration/p1-p5; P3 routers are mounted, and the P4
gateway adapter consumes actual P3 Completion metadata/task names. See
../../../../specs/integration/README.md for CURRENT wiring, validation and blockers.
Real DB adapters, worker wiring and live model verification remain incomplete.

Branch: p4/content. No commits, merges, pushes or shared database migrations performed.
No applicable AGENTS.md was found in the repository or its D:/ parent on this run.
TEAM.md and team/P4.md were read. Existing API has only /health; gateway, learner
routes, services and dashboard do not exist in this checkout. No other lane's source
was changed. MAP.md belongs to P1; please add P4 modules there during integration.

## Artifacts and review states

- data/golden/python-conditions: Think Python 3e 5.1-5.6; 15 MCQs, 5 chunks, 5 concepts.
- data/golden/fractions: OpenStax Prealgebra 2e 4.1; 15 MCQs, 5 chunks, 5 concepts.
- data/golden/cell-basics: OpenStax Biology 2e 4.2-4.3; 15 MCQs, 5 chunks, 5 concepts.
- data/guardrails: 50 evaluation questions, 20 hint candidates, agent expected labels,
  70 pending human-label templates, empty prediction example and initial null metrics.

The topics exercise branching, linear and broad graphs, numerical reasoning and
descriptive knowledge. They are fallback/testing topics, not a pre-built subject
claim for the live contest. All learner material is Vietnamese. .yaml files are JSON
syntax, valid YAML 1.2, so no YAML parser dependency was added.

Sources were opened on publisher sites. All chunks are explicitly marked Vietnamese
agent paraphrases, not quotations. Web sections are named; page is null rather than
invented. UUID chunk IDs are fixed identifiers, independent of text changes; a
separate SHA-256 detects revisions. Option IDs are stable UUIDs derived from the item
ID and label, not a correctness code. Correct option positions rotate.

Agent review re-solved all 45 MCQs and compared each with the source rule; review.md
records reasoning per item. Mathematical/Python subsets also have independent code
checks. This is NOT human review. All human reviewer/time fields are blank. No real
LLM verifier has run; no golden item is currently verified or learner-servable.
Graph edges are explicitly labelled pedagogical inferences requiring review.

OpenStax's current publisher pages say CC BY-NC-SA 4.0, and separately require prior
written permission for ingestion into generative AI offerings. model_ingestion_allowed
is false for those sources. CLI verification/generation blocks them before a model
call. Resolve with the source owner or replace the source with suitably permitted
material; changing source/chunks requires review and re-verification. Think Python
text is also CC BY-NC-SA 4.0; keep attribution/share-alike and noncommercial scope.
Source URLs, authors, access version and attribution are in each sources.yaml.

## Modules

- models.py: Pydantic source/chunk/graph/item schemas; DAG, reference and option checks.
- prompts.py / pipeline.py: delimited inert source data, graph extraction, draft item
  generation and mandatory independent gate. Generator cannot self-set review state.
- gateway.py: P3 adapter, no provider SDK/HTTP access. Models are parsed strictly.
- guardrails/answerability.py: fresh blind whitelist request, strict verdict/evidence,
  actual-family separation, timeout/error blocking, audit/hash, learner_item release.
- tutor/hints.py: levels 1-3, answer/history-aware prompts, separate independent rubric
  check, disclosure blocking, release only after a current successful audit. No arbitrary
  generated fallback is displayed. hint returns a learner-safe object or None.
- guardrails/metrics.py: human ground truth only; positive = faulty content to block;
  unknown rates are null; includes denominators, counts, rubric coverage and 18/20 target.
- supabase/migrations/0005_item_verification.sql: uuid[] chunk_ids, needs_review default,
  status constraint, verified citation constraint, partial index, item update invalidation.
  Manual rollback is content/rollback_0005.sql, outside the migration glob by design.

## P3 integration: gateway identity is mandatory

TEAM's complete(task, tier, system, messages, schema=None) is supported for drafts.
Its plain str/BaseModel return does NOT establish the actual model identity, so it
cannot pass verification. P3 should expose complete_with_metadata with those same
arguments, returning this trusted PER-CALL envelope (including after fallback):

```python
{
    "content": structured_response,
    "identity": {
        "provider": actual_provider,
        "model": actual_model_id,
        "family": canonical_family,
        "identity_source": "gateway",
    },
}
```

Do not derive metadata from model-authored JSON or a global last_call value. Families
are gpt/claude/gemini/llama/mistral/qwen/deepseek, never a provider or versioned model
name. P1/P3 review taxonomy changes. An unknown family or same-family fallback blocks.
Tasks to route: extract_graph, generate_items, verify_item, generate_hint, verify_hint.
Verifier tasks need a different actual family from their corresponding generator.
Gateway retries/fallback policy remains owned by P3; P4 enforces independent identity,
validation and verification timeouts. No provider configuration was invented.

## P1/P2/P3 integration: persistence and serving

P4 models carry private metadata; they do not redefine app/schemas.py contracts.
graph.team_payload() exports TEAM's concepts/edges shape. P1 should review proposed
P4 metadata and binding names before contracts are frozen. The richer internal item
stores exactly one correct option and a misconception object referenced by each wrong
option. It must never be serialized directly to the web.

P2 seed/service implementation should preserve chunk UUIDs; map human-readable item
and concept slugs into existing UUID DB rows explicitly. Any ID/content changes affect
the verification hash and require re-verification after mapping. Store full P4 internal
item/audit in protected persistence, e.g. existing payload.p4_verification for the audit
plus a versioned P4 artifact. Do not trust user-uploaded audits or status fields.

After loading the CURRENT chunks, every placement/next-item/question endpoint must use:

```python
from app.guardrails.answerability import learner_item

payload = learner_item(internal_item, current_chunks)
if payload is None:
    # Skip this item and use another genuinely verified item, or report no ready item.
    ...
```

The public shape is exactly {id, kind, prompt_vi, options:[{label}]}; no key, explanation,
misconceptions, model identity or internal audit is exposed. The P4 CLI preview already
uses this boundary. LIVE API routes do not exist and are NOT protected by this change.
Querying status='verified' alone is insufficient: current hash, families and evidence
must pass. Item row changes invalidate status via migration trigger. Changes to separate
item_options/chunks rows must also invalidate affected item statuses in P2's service;
the release helper provides a second check against stale hashes. No DB was migrated.

For tutor, P3 calls hint(item, level, last_answer, chunks, tier, gateway=adapter,
sources=sources, history=previous_hint_texts). Require model-use source permission
before invoking any model. Keep histories intact: combined hints may disclose an answer.
On None return a neutral localized message, never an unverified replacement. Returned
citations have chunk/source IDs, title, section, URL and optional page; adapt to P1's
public schema in P3's route. Semantic disclosure and misconception quality remain
model/human evaluation tasks; no unit test proves that all such defects are caught.

## P2 migration review

0005 was absent at start and created in P4's reserved slot. Merge after 0003 and 0004.
Only 0001/0002 existed in the checkout; do not renumber anyone else's reserved files.
The existing migrator uses forward SQL files, no downgrade framework. The rollback is
manual, transactional and intentionally outside supabase/migrations/*.sql; inspect it
before use. Review with a throwaway DB and apply through P2, not a shared DB from P4.

## Run and demo

From apps/api, with existing dependencies installed:

```powershell
uv run python -m app.content validate ../../data/golden/python-conditions
uv run python -m app.content validate ../../data/golden/fractions
uv run python -m app.content validate ../../data/golden/cell-basics
uv run python -m app.content preview ../../data/golden/python-conditions
```

Currently preview returns items=[] and blocked=15. That is the expected safe result,
not a completed learner demo. Once P3 provides a real metadata-aware gateway:

```powershell
uv run python -m app.content verify ../../data/golden/python-conditions --output ../../data/golden/python-conditions/items.verified.jsonl
```

Inspect audits and have a real human complete review.md/human_review. With approved
results and P2 integration, use the verified output as the topic's items.jsonl in a
separate demo staging directory (copy sources.yaml, chunks.jsonl and graph.yaml there).
Do not set verified by hand or substitute fake-gateway outputs for demo content.
OpenStax topics additionally require the permission issue above to be resolved first.

Generate from another permitted source set (output directory must already exist):

```powershell
uv run python -m app.content generate --sources <sources.yaml> --chunks <chunks.jsonl> --output <staging-directory> --count 15 --tier pro
```

For dashboard metrics and human annotation instructions see data/guardrails/README.md.
The current report has 0 confirmed human labels and null quality metrics. 18/20 is an
acceptance target, not an achieved result. predictions.example.jsonl is intentionally
empty; expected agent labels are never passed to the metrics as human ground truth.

## Validation commands

```powershell
uv run pytest tests/content tests/guardrails tests/tutor tests/engine tests/rag/test_notebook.py tests/test_config.py -q
uv run ruff check . ../../data/guardrails/build_cases.py
uv run ruff format --check . ../../data/guardrails/build_cases.py
uv run mypy .
```

In this environment a temporary uv-managed Python 3.12 and the EXISTING locked project
dependencies were installed outside the repository because the system Python alias
did not work. No dependency/lockfile changes were made. Database integration tests are
not part of these focused checks; Docker/Postgres is unavailable. Migration up/down
has not been executed. Exact results are recorded in validation.json after the run.
