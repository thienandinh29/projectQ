# P3 follow-up on ptest2 — 2026-11-07

The user requested aborting the unfinished main merge and continuing directly on
ptest2. That merge was aborted; these changes do not merge main or P4 and do not
claim deployment or end-to-end acceptance. Each completed change was pushed to ptest2.

## Delivered

- SafeReader rejects NAT64 `64:ff9b::/96` and IPv4-compatible `::/96` before HTTP,
  including mixed DNS answers and redirect destinations through the existing check.
- Gateway synchronized from main cb5c2f4: DeepSeek generation, independent Gemini
  verification, no silent switch to another generator family. Graph output defaults
  to 16,384 tokens, verify to 8,192; task limits are injectable. Truncated responses
  are non-retryable and retain token usage. Gemini thinking configuration is explicit;
  thoughts are observable separately, included in output usage. Attempt latency
  excludes retry backoff; Completion latency remains end-to-end.
- TopicPipeline accepts P1's async Retriever and explicit indexed subject. It checks
  returned IDs, content, URI and page against prepared material, rejects an empty or
  inconsistent result before generation, and restores prepared document reading order.
  Graph and item publication use P1 canonical validators; foreign graph/item sources
  fail closed. This adds an injection point; it does not activate P2's worker.
- Library export sorts numeric chapter/section URLs naturally (2 before 10), retaining
  order within each page. Books without ordered numeric URLs still need a TOC review;
  deterministic URL order is not proof of a correct reading sequence.
- `app.research.smoke` runs canonical KnowledgeGraph → ItemSet → blind Gemini answers.
  It never publishes or labels an item verified, even on agreement. `--live` is required
  for network model calls. Per-attempt receipts contain route, model, token counts,
  thoughts, latency, status and sanitized error codes, including paid failed outputs.

## Measured evidence and limits

`data/sources/p3-topic-smoke.json` is a **preflight only** receipt from three public
Think Python chapter-1 chunks (3,930 characters). Local book fingerprints are explicit;
they are not persisted database chunk IDs or vector-retrieval results. Live token and
latency fields are null, not measured zeroes. The user confirmed the exposed provider
keys have not been rotated, so no live model calls were made in this session.

Local Docker has PostgreSQL running, but the `nodetrail` database has no `subjects`
table; TEI is not running. No dev schema/data were modified to work around this.
The API test suite uses throwaway databases with the actual migrations, including
retriever SQL tests, and does not claim live embedding/model acceptance.

## P2 / P4 integration

After P2 merges the actual content adapter, construct the library pipeline with one
startup Retriever, using the **library** subject (not a new empty topic slug):

```python
from app.rag.retrieve import Retriever
from app.research.pipeline import TopicPipeline

retriever = Retriever(pool, async_embedder)
pipeline = TopicPipeline(
    content_ports,
    retriever=retriever,
    retrieval_subject="python-basics",  # actual indexed subjects.slug
    retrieval_k=12,
)
```

`content_ports.index` must return the exact stored chunk content, `chunks.source_uri`,
page and persistent ID, in document order. All selected sources must be indexed first.
P4's current `ContentPorts` on origin/p4 maps chunk URIs through `Source.url`, which may
be a book root while `chunks.source_uri` is a chapter page. Preserve the actual page
URI at that boundary; do not weaken P3's mismatch check to hide this difference.

P2 must bring main's DeepSeek/Gemini Settings fields and worker environment exports
into its config integration. They are absent on ptest2 after aborting the main merge;
P3 has not edited P2's config. Configure rotated keys locally, select distinct tier
models if desired, and keep uploads blocked from model calls pending P1's privacy
decision. `app/llm/.env.example` documents the process variables without real keys.

Run a small public chapter first, after exporting rotated keys/model IDs into the
process environment (the smoke CLI itself never reads .env):

```powershell
# From apps/api; omit --live for safe preflight.
uv run python -m app.research.smoke `
  --book ../../data/raw/library/think-python-2e `
  --uri-contains /01:_The_way_of_the_program `
  --goal "Các khái niệm cơ bản của chương trình Python" `
  --output ../../outputs/p3-live-topic.json --live
```

This book-mode route check does not exercise worker/DB retrieval. For that, P2 must
apply the integrated migrations in order, run TEI, index only the demo chapter, and
use the injection above. Then run the full topic → graph/items → placement → answer
→ mastery/review sequence with P4's verification gate and retry/failure scenarios.
P1/P4 still own human labels and H8 quality acceptance; no benchmark score is inferred
from these route tests. G4 tier policy, G5 upload privacy and G7 job deadlines remain
their respective owners' decisions; G6 shared HTTP/concurrency is a scaling follow-up.


## Final verification in this session

| Check | Result |
|---|---|
| API ruff check / format | Pass; 123 files formatted |
| API mypy | Pass; 122 source files |
| API pytest | 1,260 passed; one existing Starlette/httpx deprecation warning |
| Web frozen install | Pass via npx pnpm@10.20.0; lockfile unchanged |
| Web lint / typecheck | Pass |
| Web vitest | 38 passed across five files |
| Public chapter preflight | Pass; no model API call or published item |
| Live graph/items + worker/TEI | Not run; blockers described above |
