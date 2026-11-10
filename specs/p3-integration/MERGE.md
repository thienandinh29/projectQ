# P3 merge and integration instructions for teammate AI agents

Read this file before merging P3. Latest P1 comparison and exact engine calls:
[contract-review.md](contract-review.md). Read `TEAM.md`, `CLAUDE.md` and your own lane guide
first. P1's final contracts take precedence over provisional DTOs here. Keep changes
inside your lane; P2 coordinates application wiring and routine green merges.

The user explicitly requested that **real cross-lane wiring be delegated through this
file**. P3 supplies executable modules, HTTP route factories, the worker-callable topic
pipeline and reserved upload migration. Do not mistake fixture tests for a deployed
system or report live acceptance without running it.

## What to preserve when merging

- Branch is `p3`, named by the user; TEAM's suggested `p3/integration` was overridden.
- P3 source is in `apps/api/app/{llm,research,uploads,graders}/` and
  `apps/api/app/api/{learn,topics,tutor}.py`.
- Tests are in `apps/api/tests/{llm,research,uploads,graders,api}/`.
- Also merge `scripts/build_library.py`, `data/sources/`, `specs/p3-integration/`,
  `supabase/migrations/0007_uploads.sql`, and the approved dependency/lock changes.
- Approved added packages: httpx, google-auth, boto3, PyYAML, pypdf, python-multipart.
  Keep lockfile resolution consistent with P2's branch rather than discarding either
  lane's dependencies. Resolve pyproject first, then regenerate uv.lock.
- P3 deliberately did not edit main.py, config.py, jobs/services, P1 engine/retrieval,
  shared schemas, P4 content/tutor or root MAP. Those changes belong to their owners.
- Raw textbook files are git-ignored in `data/raw/library/`. Rebuild them with the
  command below on the indexing VM; do not assume Git transferred them.

## Merge sequence

1. **P1:** merge pushed schemas, integer-index answers, retrieval, placement,
   remediation/path and traced engine APIs. Review source coverage/subject naming.
2. **P2:** merge migrations in reserved order 0003, 0004, 0005, 0006, then P3's 0007.
   The migration here depends only on existing Postgres, but do not apply it early
   to the shared/demo DB or renumber it. Local tests create a throwaway database.
3. **P4:** merge content generation, item/hint verification and Socratic tutor.
4. **P2 with P1/P4:** implement the adapters described below, configure credentials,
   mount P3 routers and call TopicPipeline from the separate queue worker.
5. **P5:** regenerate types from the merged real OpenAPI and run the full learner flow.
6. Run the final acceptance checklist in this file; only then mark integration done.

## HTTP routers: P2 wires, owners supply algorithms

```python
from app.api import learn, topics, tutor

app.include_router(learn.create_router(learning_adapter))
app.include_router(topics.create_router(topics_adapter))
app.include_router(tutor.create_router(tutor_adapter))
```

The adapters implement structural Python Protocols in the same P3 files. They are
P3's required inputs, **not** pre-existing P1/P2/P4 signatures. Translate real lane
APIs inside adapters; do not rewrite the objective grader or clone the engine.
Unconfigured factories intentionally return Vietnamese 503 responses.

### LearningBackend — app/api/learn.py

| Required method | Real integration responsibility |
| --- | --- |
| `graph(learner_id, subject)` | P2 loads subject/concepts/edges/mastery; P1 determines mastered flags. Return GraphResponse; edge JSON key is `from`. |
| `placement(LearnerSubject)` | P1 graph-walk next question/gap/trace; P2 loads previous answers. Return PlacementSelection with internal Item, or `item=None, done=True`. |
| `next_item(learner_id, subject)` | P1 selects the next verified item/reason; P2 loads it; return NextSelection or None. |
| `get_item(item_id)` | P2 loads internal answer key, source, chunk_ids, verification status and misconception tags; return Item or None. |
| `apply_attempt(request, item, Grade)` | P2 opens one transaction: save attempt/hints; run P1 BKT/traced/root-cause/review logic; persist mastery, traces and review schedule; return AttemptUpdate. P3 already graded the answer. |
| `reviews_due(learner_id)` | P2 loads scheduled cards; P1 owns scheduling rules. Return ReviewsResponse. |
| `exam_plan(ExamInput)` | P1 derives the schedule; P2 supplies current data. Return ExamResponse. |

Do not return `correct`, a new mastery calculation or an answer key from another
model. The handler attaches the real deterministic grade and projects learner items
to `{id, kind, prompt_vi, options:[{label}]}`. Items with `needs_review` cannot be
served or graded. Correct attempts suppress wrong-answer misconception/remediation.

P1 should replace provisional DTOs in these P3 files with imports from schemas.py
once merged. P1 has finalized `answer` as a zero-based integer index; P3 now
grades it directly and no longer requires an answer-label resolver. Preserve JSON
null for a completed placement's `item`, and preserve timezone-aware trace dates.

### TopicsBackend — app/api/topics.py

- `enqueue(TopicInput) -> TopicResponse`: validate goal/upload ownership/existence and
  readable text. Reuse a ready cached topic if appropriate; otherwise insert a queued
  job and return `{topic_id, cached}` immediately. Never research in the request.
- `persist_upload(document, body, filename) -> upload_id`: persist source bytes in a
  **private** Storage bucket and metadata in the new `uploads` table. File documents
  initially have empty `source_uri`; replace it with the actual durable Storage URI.
  Linked documents already have their final HTTPS URL. Preserve each page number.
- Use `app.uploads.metadata.prepare_metadata(...)` to build/validate the exact row
  fields and `UploadMetadata.document()` to reconstruct a pipeline input.
- Pass `document.media_type` into that conversion. The extractor preserves actual
  PDF/DOCX/HTML MIME information even for links; do not infer MIME solely from the URL.
- Columns in 0007: id, source_uri, filename, media_type, byte_size, sha256, page_count,
  text_ok, pages, created_at. Bind SQL parameters; serialize `pages` as JSONB.
- For file uploads, generate the UUID **before** choosing the object path, then pass
  the same UUID to `prepare_metadata(upload_id=...)`. If metadata insertion fails,
  remove only the newly written object or queue cleanup; do not leave orphaned bytes.
- Preserve unreadable uploads as `text_ok=False`; do not generate curriculum from them.
- `uploads` has RLS and no client policies. Server DB credentials must have the needed
  access; do not add public/anonymous read policies just to fix a permission error.
  Demo has no Supabase Auth; do not assume learner UUID equals auth.uid().
- Create a private Storage bucket with the 20 MB limit and allowed MIME types using
  P2's infrastructure process. Do not put a service-role key in the web client.

P2 still owns `/learners`, `GET /topics/{id}`, `/topics/{id}/events`, `/topics/cached`,
route mounting, API-key checks, CORS, queue storage, worker claims and SSE heartbeats.

### TutorBackend — app/api/tutor.py

- `hint(HintInput) -> VerifiedText`: P2 loads the item and cited chunks; P4 calls
  `app/tutor/hints.py` and its verification gate. Map the checked hint/citations and
  set `supported` from the **gate verdict**, not from LLM-generated JSON.
- `ask(AskInput) -> VerifiedText`: P1 retrieves cited chunks; generate through P3's
  gateway and validate support via P4. Map the checked answer/citations.
- Routes withhold unsupported, blank or uncited text. Citation DTOs carry title,
  section and URL. Map private Storage paths to authorized citation URLs; do not
  make the bucket public. P4 retains responsibility for no-final-answer behavior.

## Topic worker pipeline — P2 calls; P1/P4 implement ports

```python
from app.research.pipeline import TopicPipeline

# Run in P2's separate claimed-job worker, never in uvicorn's HTTP request handler.
result = await TopicPipeline(pipeline_adapter).run(topic_input, save_progress, save_trail)
```

Implement `PipelinePorts` in `app/research/pipeline.py`:

| Method | Required mapping |
| --- | --- |
| `load_upload(id)` | P2 loads UploadMetadata and returns its Document, with canonical Storage URI and text_ok. |
| `quick_sources(goal)` | P1/P2 select from the indexed approved library, preserving title/publisher/URL/license/text. No web search. |
| `index(sources, upload)` | P1 chunk/embed/retrieve code plus P2 persistence. Return PreparedChunk values with **real persisted IDs**, text, source_uri, page. Reuse indexed library chunks instead of re-embedding the library per topic. |
| `build_graph(goal, chunks, tier)` | P4 builds/validates a cited prerequisite DAG. Return GraphDraft with subject_slug, graph payload and gate-derived supported. Use `marked_chunks(chunks)` for exact ID markers. |
| `save_graph(graph)` | P2 upserts the subject/concepts/edges atomically; reject cycles through P1's loader. |
| `build_items(graph, chunks, tier, count)` | P4 generates at least the initial six **verified** placement items. Preserve misconception tags and cited IDs. |
| `save_items(subject_slug, items)` | P2 retry-safe upsert of verified items/options. Do not reset existing learner state on retry. |

Quick mode has a 60-second outer deadline; Deep has a 480-second outer deadline.
Deep uses real research (three final source URLs, at least two publishers). Quick
upload mode never invokes search. After persistence, callbacks transition through
researching → indexing → graph → items → ready. Progress includes source summaries,
readiness flags and dropped item counts; do not serialize source full text into SSE.
Trail events have UTC `at`, kind, Vietnamese text and URL.

Pipeline rejects pending items, duplicate IDs and citations outside the prepared
chunk set. Failure preserves current readiness flags and publishes failed; it does
not silently replace the learner's topic with a golden topic. P2 owns explicit
fallback selection and worker retry/reclaim policy. Worker cancellation propagates
without writing a misleading failed state. SDK threads have their own network
timeouts; enforce resource/process limits in P2's worker for hostile document parsing.

The pipeline stops after the initial verified batch. P2/P4 should schedule remaining
items as subsequent background work, preserving the already-ready initial path.

## LLM/search configuration — P2 deploys, P1 selects models, P4 uses gate

- Load the root environment through P2's settings/deployment. P3 intentionally reads
  process environment and does not silently open .env.
- Merge additional names from `app/llm/.env.example` and `app/research/.env.example`
  into root `.env.example` and P2 config. Configure real model IDs permitted in the
  account; all routing slots were unconfigured during the local dry check.
- The exact process-environment dry result is in `runtime-status.json`; it does not
  inspect a teammate's .env or cloud account. Supply model IDs and a Brave key to
  the deployed process before running the explicit live commands below.
- Vertex: GOOGLE_CLOUD_PROJECT, VERTEX_LOCATION, ADC/attached service account.
  Bedrock: AWS_REGION and normal IAM credential chain/profile. OpenRouter:
  OPENROUTER_API_KEY. Do not share personal passwords or commit key files.
- Search: SEARCH_PROVIDER=brave and SEARCH_API_KEY for **Brave Web Search**. A real
  adapter is implemented in `app/research/search.py`; no extra SDK is needed.
  Missing keys fail explicitly. There is no paid call in the test suite.
- Configure per-job Gateway using `gateway_scope(...)`; attach P2 telemetry to
  `observe_attempt` (nonblocking callback) and successful `observe` if desired.
  Count token usage for rejected/retried responses too. P2 supplies prices/costs.
- P4 must call `complete_with_metadata` for generation and enter
  `verification_scope(generated.route.family)` for `complete("verify", ...)`.
  Family refers to the **actual fallback model**, not the preferred model.
- The verifier sees cited chunk text and the question only, without the key; P4
  compares its blind answer against the key. Gateway filtering alone is not the gate.

From apps/api, perform an offline routing check and explicitly opt into one-provider
live probes only after credentials/model IDs are configured:

```powershell
uv run python -m app.llm.smoke
uv run python -m app.llm.smoke --live --provider vertex --tier free --task items
uv run python -m app.llm.smoke --live --provider bedrock --tier pro --task items
uv run python -m app.llm.smoke --live --provider openrouter --tier free --task items
```

Each live command selects only that provider and cannot disguise its failure by
falling back to another provider. Never paste credential values in the PR or logs.

## Library handoff — P1 reviews, P2 indexes

```powershell
# From apps/api. Download cache is resumable and ignored by Git.
uv run python ../../scripts/build_library.py --jobs 2 --report ../../data/sources/acquisition-report.json
uv run python ../../scripts/build_library.py --export-only --report ../../data/sources/library-index-report.json
```

`data/sources/library.yaml` selects eight LibreTexts-hosted candidates from the
existing publisher allowlist. Every downloaded page carries license, URL, SHA-256
and text; unsupported/ND/restricted pages are rejected. OpenStax candidates remain
in `openstax-review.yaml` for review because the checked current preface explicitly
restricts LLM ingestion. Do not route around a restriction by using an unreviewed mirror.

The second command performs a fresh **local** hash/license/scope audit and writes
P1-compatible `source.json` / `document.json` pairs as well as
`data/raw/library/<slug>/index.jsonl` containing only accepted records. Ingest those
exports rather than blindly globbing raw files. Each record supplies title, publisher,
source_uri, URL, license, license_url, SHA-256 and extracted text. Use
`library-index-report.json` for the current accepted/rejected page counts.
The checked local receipt contains **1,255 accepted pages across 8 selected books**;
raw content/exports are intentionally ignored by Git. Rebuild on the indexing VM.

Read `acquisition-report.json` for actual completion/failures. `complete` means
bounded HTML discovery exhausted successfully, not a guarantee of publisher-TOC
coverage. Compare discovered pages with the real table of contents; replace blocked
chapters/sources explicitly. All eight candidates are hosted by LibreTexts; this
does **not** itself satisfy Deep Research's two-publisher bar.

P2 runs P1's ingestion code **after 0003 halfvec is merged**, enforces the ~30k chunk/
350 MB stop limit, and builds HNSW after the load. P3's downloader never writes DB
embeddings. Use the exported P1-compatible pairs with `app.rag.library`; see contract-review.md.

## P5 can work now

`specs/p3-integration/openapi.json` is the provisional P3 snapshot. Regenerate from
the real app after merging shared schemas. For a local HTTP contract preview:

```powershell
uv run uvicorn tests.api.preview:app --host 127.0.0.1 --port 8013
```

The title/header clearly mark fake backend data. Never mount `tests.api.preview`
in production. It has no durable storage, real engine or real LLM calls.

## Acceptance before saying the merged product is ready

- [ ] P1 final schemas replace/align provisional DTOs; regenerate P5 types.
- [ ] Migrations 0003–0007 merge and apply in order; private uploads round-trip.
- [ ] All ten P3 routes mount with **real adapters**, no fixture preview imports.
- [ ] Topic requests enqueue; independent worker persists progress; SSE heartbeats
      every 15–20 seconds and reload/reconnect works through the tunnel.
- [ ] All three providers pass explicit live probes and actual fallback is tested.
- [ ] Brave search works; off-allowlist domains/redirects never reach source reading.
- [ ] Nhanh on three unfamiliar topics/files reaches graph plus first placement
      questions in <60 s; file text/pages/citations remain traceable.
- [ ] Deep completes in <8 min with ≥3 sources/≥2 publishers, license/provenance,
      verified items and the Vietnamese research trail.
- [ ] Wrong answer → real deterministic grade → engine trace/remediation; supported
      Socratic hint; correct answer updates mastery and persists a review schedule.
- [ ] needs_review items and unsupported hints never reach learners; no key leaks.
- [ ] Dashboard shows latency/token cost/dropped items, including retry costs.
- [ ] No .env/key files/raw textbook blobs are staged. P1 updates root MAP.

Required local checks from apps/api:

```powershell
uv run ruff check . ../../scripts/build_library.py
uv run ruff format --check . ../../scripts/build_library.py
uv run mypy . ../../scripts/build_library.py
uv run pytest -q
```

Database tests use the existing local compose DB (start at root with
`docker compose up -d db`); no demo DB migration was run. See validation.md for
the actual latest evidence. Do not convert pending live checks into checked boxes
merely because the offline suite passes. Do not commit/push/force-push on behalf of
another member without their authorization.
