# P3 H7 results — 2026-11-07

This supersedes the pre-merge handoff in `p3-follow-up.md`. The integration trunk
now contains P2's main/P4 merges (`ee5bc3f`). P3 continued directly on `ptest2`,
rebased its unpushed library change over that merge, and pushed each completed part.

## Pre-index library checks

All eight books in `data/sources/library.yaml` now use the existing `subject_slug`,
`subject_name_vi` and `subject_name_en` fields. Slugs are preserved, including
`think-python-2e`; its display name is **Lập trình Python cơ bản**.

The real Think Python export exposed a problem beyond chapter sorting: LibreTexts
navigation, search controls and toolbars were entering the index. The library reader
now selects `mt-content-container`, keeps Python example indentation, and checks
licensing separately against the full original HTML. Extraction changes enter the
source version hash. Numeric page/section order remains natural (2 before 10).

Re-exporting 1,255 cached pages across eight books produced no rejected page.
Think Python has 244 source pages and 391 chunks, down from 2,764 chunks containing
site chrome. Its cleaned chunk lengths are min 342 / median 1,404 / p95 1,785 /
max 1,800 characters. Every source URI is retained; non-whitespace content is retained
through P1's chunker. These HTML sources use exact page URLs and have `page=null`;
inventing PDF page numbers would be wrong. This does not certify extraction of every
other book or replace P1's semantic review.

Artifacts: `data/sources/p3-library-export.json`,
`data/sources/p3-python-library-audit.json` (including readable samples and page order).
P1's ten Vietnamese queries have now arrived in `data/eval/think-python-2e.yaml`.
All ten label snippets and all ten intended numbered sections are present in the
clean export. `data/sources/p3-python-query-label-audit.json` records exact confirmed
page URLs for P1 to review/add to its labels. q06-q10 were checked only for label
existence, without tuning k, prompts or models. This is not a ranked retrieval score;
semantic retrieval and graph quality remain unchecked.

P2 must regenerate its own ignored local exports after pulling, before indexing:

```powershell
# From apps/api; no network, embeddings or database writes.
uv run python ../../scripts/build_library.py --export-only --book think-python-2e
uv run python ../../scripts/build_library.py --audit-only --book think-python-2e `
  --report ../../outputs/python-library-audit.json
uv run python ../../scripts/build_library.py --audit-only --book think-python-2e `
  --queries ../../data/eval/think-python-2e.yaml `
  --report ../../outputs/python-query-label-audit.json
```

## Real worker retrieval construction

`TopicPipeline` now requires both retriever and subject; construction without them
fails. Retrieval is unconditional before model work. The actual `app.jobs.worker
--pipeline` path validates explicit `RESEARCH_SUBJECT` before claiming a job and
creates one cached `Retriever(pool, WorkerEmbedder())` for that worker pool.
Each embedding HTTP client closes in its own event loop because the worker uses
`asyncio.run` per job. `RETRIEVAL_K` defaults to 12 and is bounded to 1..50.

The P4 call-site/adapter now receives these dependencies, restricts library selection
to the configured subject, and supplies only selected chunks to graph/items/verifier.
The read-only bridge recognizes P1-indexed public library rows through the reviewed
manifest, retaining explicit denials in existing P4 metadata; unknown sources fail
closed. It does not rewrite metadata, embed the library again, or invent chunk IDs.

Prepared chunks retain both exact `chunks.source_uri` (the page) and the registered
`sources.url` (the book). Retriever content/ID/page/URI comparisons remain exact.
Graph/item book-level URLs are accepted only through the stored source associated
with cited chunks; unrelated URLs are still rejected.

`tests/research/test_runtime.py` uses real PostgreSQL/pgvector and migrations, with
fake embeddings/models: 15 indexed chunks → 12 retrieved chunks → restored reading
order → bounded P4 graph context. This proves wiring/provenance, not semantic quality
or real model speed. For uploads/deep sources, P2/P4 must index their actual explicit
subject and preserve the existing model-use gate; a public-library subject is not
a bypass for unindexed private material.

Two small merge defects surfaced during this verification and were corrected:
the P4 runtime SQL tolerates the `mode`/`upload_id` columns already added by P2;
the API mounts each router once so injected P4 backends are used. PostgreSQL REAL
difficulty is compared in float32 on both sides, preserving legitimate audit hashes
without concealing actual numeric edits. Existing invalidation/database tests cover
the latter. The integrated web test now expects canonical explicit null evidence.

## Models, input limits, measurements

Local `.env` and templates now distinguish Free `deepseek-flash` and Pro
`deepseek-v4-pro`; only those model/subject settings were changed, not API keys.
Local demo settings are `RESEARCH_SUBJECT=think-python-2e`, `RETRIEVAL_K=12`.

DeepSeek's [model table](https://api-docs.deepseek.com/quick_start/pricing/) and
[chat API](https://api-docs.deepseek.com/api/create-chat-completion/), checked on
2026-11-07, list the two model IDs, a 1M context, and up to 384K output tokens.
The adapter uses conservative decimal budgets (1,000,000 / 384,000), counts UTF-8
bytes as an input upper bound with framing/schema/output reserved, and rejects
oversize requests before any paid call. This is not an exact tokenizer measurement.
The multibyte long-input regression confirms no HTTP call and no retry. Graph output
remains 16,384 tokens by default, so passing a context budget is not a promise that
a whole book can be extracted reliably; retrieve a topic-sized subset.

`uv run python -m app.llm.smoke --live` now defaults to DeepSeek then independent
Gemini. Use `--output` to save every attempt's model, tokens, latency and error.
Single-provider isolation is still available via `--provider`. Imported golden items
use P4's known generator-family taxonomy (including GPT); route models remain
DeepSeek/Gemini and verifier identity is never taken from model-authored text.

Canonical topic smoke uses `KnowledgeGraph` and `ItemSet`, with `--k` up to 50 for
comparison. Receipts distinguish end-to-end elapsed time from successful
`Attempt.latency_ms`. Token totals include failed/repaired calls, and thoughts are
recorded separately. Items stay drafts even when the blind verifier agrees.

```powershell
# After rotating both keys locally:
uv run python -m app.llm.smoke --live --output ../../outputs/gateway-live.json
uv run python -m app.research.smoke `
  --book ../../data/raw/library/think-python-2e `
  --uri-contains /01:_The_way_of_the_program --k 12 `
  --goal "Các khái niệm cơ bản của chương trình Python" `
  --live --output ../../outputs/python-k12-live.json
```

Book-mode smoke is explicitly not vector retrieval. For a real research-worker run,
P2 must apply the reviewed schemas, start TEI, index the audited chapter/library,
then run `uv run python -m app.jobs.worker --pipeline`. P1 should compare the resulting
graph with its expected Python sections at k=12, then try k=24 if coverage is missing.
No k increase is justified by model-quality evidence in this session.

`data/sources/p3-python-k12-preflight.json` is preflight only.
`data/sources/p3-h7-readiness.json` records the actual environment checks: local DB
connects but has no base/P4 schema, TEI health is unreachable, and no live model call
was made because the user last reported the keys unrotated. Live token/latency fields
remain null. These prerequisites are not hidden by fixture results.

## Canonical learning schemas

After the merge, `learn.py` imports public response models and traces from P1 schemas
instead of duplicating them. Existing adapter port records remain internal. Request
subclasses preserve strict integer/length validation; no API contract was changed.
Frozen trace test fixtures use `model_copy` rather than mutating P1's evidence.

The board ticks only the completed library/runtime/schema/model-configuration work.
P1 label-existence checking is complete. Semantic k=12 graph review, rotated-key live
measurements and full deployment acceptance remain unticked.

The earlier P2 index snapshot (12:54 UTC) listed 2,764 pre-cleaning Python chunks.
The newer receipt at 13:09 UTC (`915b231`) confirms Python completed with **391**
chunks, matching the cleaned export; Logic completed with 331 chunks and Statistics
was in progress. Do not reindex Python solely because of the obsolete snapshot.
This session did not interrupt P2's process; current P2 host state remains P2-owned.


## Verification of the final integrated code

Verified at `b7b6619c50e60e8b1c21655dc32c78100d7e9eca`, including P2's retry/demo updates through `915b231`:

| Check | Result |
|---|---|
| API Ruff lint / format | Pass; 166 files formatted |
| API mypy | Pass; 159 source files |
| API tests | 1,394 passed; one existing Starlette/httpx deprecation warning |
| Web lint / typecheck | Pass |
| Web tests | 46 passed across six files |
| P1 source labels | 10/10 snippets and 10/10 intended sections confirmed |
| Actual P3 live graph/items and k=12 quality | Not run; no invented token/latency/quality score |

P2's separate `docker/p2-live-gateway.json` is synthetic route evidence: DeepSeek
answered, but Gemini returned HTTP 503. It is not P3's canonical-topic acceptance.
