# P3 integration handoff

**Canonical merge instructions:** [`specs/p3-integration/MERGE.md`](../../../../specs/p3-integration/MERGE.md).
That single file specifies lane owners, every adapter/port method, migration order,
runtime setup and live acceptance. Start there when merging teammate branches.

This branch implements independent P3 modules **and all ten P3 HTTP route factories**.
It does **not** complete the end-to-end P3 acceptance criteria: real services/jobs,
engine/retrieval integration and content/tutor adapters are still needed. Their shared
interfaces are absent in this checkout, as confirmed by the user.

## Available modules

| Module | Entry point / behavior |
| --- | --- |
| `app.llm.gateway` | Async `complete(...)`, `complete_with_metadata(...)`, schema validation, bounded retry/fallback |
| `app.llm.providers` | Vertex Gemini REST with ADC, Bedrock Converse with AWS credential chain, OpenRouter chat completions |
| `app.research.reader` | HTTPS/public-DNS pinning, same-host TLS verification, allowlist per redirect, response limits |
| `app.research.library` | HTML book traversal, licensed provenance, resumable hash-checked cache, transient retries |
| `app.research.agent` | Injectable search, at most 15 searches and 12 document reads, eight-minute overall deadline |
| `app.research.search` | Concrete Brave Web Search adapter with domain filtering and sanitized failures |
| `app.research.pipeline` | Worker-callable Quick/Deep orchestration and verified-item persistence ports |
| `app.uploads.reader` | PDF/DOCX/link text and page extraction; limits and unreadable-file detection |
| `app.uploads.metadata` | Validated row conversion for the reserved 0007 upload migration |
| `app.graders.mcq` | Pure grading and typed learner-safe item projection |
| `app.api.learn` | Graph, placement, attempts, next-item, due reviews and exam-plan routers |
| `app.api.topics` | Topic enqueue and multipart PDF/DOCX or URL upload router |
| `app.api.tutor` | Hint and ask routers with supported/cited response checks |

All provider SDK access stays inside `app/llm`. Credentials come from process
environment / SDK credential chains; no development tool has opened `.env`.

## Runtime configuration

Provider credentials and project/region names are listed in the root `.env.example`.
The additional **model ID** environment names are in this directory's `.env.example`.
P2 should incorporate those names into the root example/configuration. The gateway
reads process environment; it does not implicitly load `.env` files. Loading settings
and injecting environment into the worker/container remains P2's responsibility.

Empty model IDs are skipped and ultimately produce a configuration error if no model
is eligible. There are no speculative defaults or model IDs embedded in code. Family
labels must agree with IDs (`gemini` or `claude`); OpenRouter `:free` IDs are rejected.
Supported task names: `graph`, `items`, `verify`, `tutor`, `ask`; Pro also has `research`.
Free research has no route.

### P4: preserve the actual generator family

```python
from app.llm.gateway import complete, complete_with_metadata, verification_scope

# These names are the application's prompts/messages and Pydantic result models.
generated = await complete_with_metadata("items", tier, system, messages, ItemBatch)
with verification_scope(generated.route.family):
    verified = await complete("verify", tier, verifier_system, blind_messages, Verdict)
```

The gateway excludes the generator's actual family, including after fallback. If
verification has no eligible family it fails closed. P4 must still construct the
blind verifier prompt from cited chunks only, compare its answer with the key, and
enforce supported hints/items. The gateway does not implement P4's content policy.

### P2: telemetry and job deadlines

Use `gateway_scope(Gateway(...))` in each worker job to inject routing, adapters,
deadlines and observers while preserving the agreed `complete(...)` signature.
`observe_attempt` is a **nonblocking synchronous** callback receiving sanitized
`Attempt` metadata for each real call, including validation failures/retries;
`observe` is an optional async successful-completion callback. Neither contains
prompts or credentials. Observer exceptions propagate and must be handled by the
observability adapter. Token counts are reported; cost requires P2's price table.

Use one outer job deadline for Quick mode's 60-second target. The gateway's standalone
default is a 100-second total timeout with 35-second per-attempt bounds; it is not a
guarantee of Quick mode performance. SDK calls offloaded to threads have their own
network timeouts; cancelling an await cannot forcibly terminate a running SDK thread.

### P2: research worker

Construct `ResearchAgent(search_backend)` and enter `research_scope(agent)` before
calling `research(goal, on_event)`. The search backend has the typed signature
`(query: str, domains: Sequence[str]) -> Awaitable[Sequence[SearchResult]]`.
The default backend is implemented: `SEARCH_PROVIDER=brave` plus a Brave Web Search
`SEARCH_API_KEY`. `research_scope` still supports injected backends. Merge
`app/research/.env.example` into P2's runtime configuration.

Progress callbacks contain Vietnamese `search/read/select` text, URL and elapsed
seconds. P2 supplies timestamps, persists trail/job state and exposes SSE heartbeat
and reconnect behavior. Failures/deadlines raise `SourceError`; the worker owns the
transition to failed/fallback. No generated curriculum is fabricated on failure.

## Pending shared integration

| Owner | Needed before integration |
| --- | --- |
| P1 | Merge pushed schemas/engine/retrieval; approve source coverage/subject naming |
| P2 | Services for uploads/attempts/mastery/traces/reviews; job submission and progress; Storage interface; router mounting |
| P4 | Source/chunk-to-graph/items pipeline, answerability gate, tutor interfaces |
| P5 | Confirm exact OpenAPI-generated client compatibility and Vietnamese failure display |

The MCQ models are internal validation types derived from TEAM's item fixture.
P3 HTTP DTOs have been compared against P1 ml-core 5245e56; they retain local names
until the shared schemas are merged. Public `answer` is now a strict zero-based
integer index, graded directly without an answer-label resolver. See
[contract-review.md](../../../../../specs/p3-integration/contract-review.md) for the
exact P1 engine/retrieval calls, library format and remaining P2 integration work.

All ten P3 endpoints are implemented as `create_router(backend)` factories, with
protocols in the same P3-owned files. Each protocol is P3's adapter requirement, not
a claim about the final signatures in P1/P2/P4 code. P2 can mount them as follows
once the adapters exist:

```python
from app.api import learn, topics, tutor

app.include_router(learn.create_router(learning_adapter))
app.include_router(topics.create_router(topics_adapter))
app.include_router(tutor.create_router(tutor_adapter))
```

Factories without a backend return Vietnamese 503 errors rather than fixture data.
The attempt route performs objective grading and safe projection before persistence;
the learning adapter owns the atomic engine/update transaction. A file upload is
extracted with an empty provisional source URI; the persistence adapter must assign
its actual Storage URI before indexing. The topic adapter enqueues only and must
check that an upload exists and has readable text; it must not run research inside
the HTTP request. Topic/learner not-found and authorization errors are the adapters'
responsibility, mapped to sanitized HTTP errors. P2 still owns API-key/CORS wiring.

`GET /topics/{id}`, `/events`, `/cached`, learners and the worker belong to P2.
Migration `supabase/migrations/0007_uploads.sql` supplies upload metadata and RLS;
P2 reviews and merges it after preceding reserved migrations, writes the private
Storage/DB adapter and mounts routers. No production queue or main-app mounting was
added. Call `TopicPipeline` from P2's separate worker; its port mapping and failure/
retry rules are in MERGE.md.

## Frontend development before integration

A fixture-only preview uses the actual P3 router implementations with test backends:

```powershell
# From apps/api. Requires the development dependencies; binds to loopback only.
uv run uvicorn tests.api.preview:app --host 127.0.0.1 --port 8013
```

Open `/docs`. Its title and every response's `X-NodeTrail-Backend: fixture` header
identify the fake backend. This preview has fake engine/queue/Storage/tutor, no paid
calls and no durable data. It must not be imported by the production main app.
The current OpenAPI snapshot is `specs/p3-integration/openapi.json`; P5 can generate
client types now and regenerate after P1's final schemas are substituted.

P1 MAP update proposal: mark `app/llm/`, `app/research/`, `app/uploads/`, `app/graders/`
and `data/sources/` implemented; add P3 route factories, `scripts/build_library.py`,
the OpenAPI snapshot and these P3 tests.
Root MAP is left to its P1 owner.

## Validation

From `apps/api`:

```powershell
uv run ruff check . ../../scripts/build_library.py
uv run ruff format --check . ../../scripts/build_library.py
uv run mypy . ../../scripts/build_library.py
uv run pytest -q
```

The existing full suite requires `docker compose up -d db` at repository root.
P3-focused tests (including two local database checks for upload migration):

```powershell
uv run pytest -q tests/llm tests/research tests/uploads tests/graders tests/api
```

For checks without a database, omit `tests/uploads/test_metadata.py`; all model/search
transports in automated tests are fakes, and no paid network calls occur.

Validated on Python 3.14.7 (the available interpreter; project minimum remains 3.12).
Live cloud/search probes and Quick/Deep real-backend timing are **not** validated.
Run `python -m app.llm.smoke` for a network-free routing check, or explicitly opt
into a single-provider `--live` probe after configuration. Actual library acquisition
results are in `data/sources/acquisition-report.json`. No paid call was used.
There is no `apps/web` folder to lint/typecheck/test.


## P3 follow-up on `ptest2` (2026-11-07)

Routing is synchronized with `main` cb5c2f4: DeepSeek generates and Gemini verifies,
with no cross-family generation fallback. P2 must carry the five DeepSeek/Gemini
settings and their worker exports from main's `app/config.py` during integration;
this P3 patch does not modify P2 configuration. Configure `DEEPSEEK_FREE_MODEL`,
`DEEPSEEK_PRO_MODEL`, `GEMINI_VERIFY_MODEL` and the provider keys in the host environment.
Do not paste keys into chat. Rotate the two exposed keys before live acceptance.

Gateway output limits default to 16,384 tokens for graph, 8,192 for verification,
and 4,096 for other tasks. Override with `Gateway(task_limits={...})` using
`GenerationLimits`. These are output limits, not proof that an arbitrary book fits:
use retrieved topic chunks and chunk-ID markers rather than the entire library.
DeepSeek's [current model table](https://api-docs.deepseek.com/quick_start/pricing/)
lists a 1M context; re-check the selected model and leave room for output.

Truncation (`length`, `MAX_TOKENS`, `max_tokens`) stops the route without paying for
an identical retry. Usage from truncated replies remains in `Attempt`; invalid JSON
and transient errors retain bounded retries. Gemini 3 uses LOW thinking, Gemini 2.5
a 1,024-token thinking budget; `thoughts_tokens` is separately observable and remains
included in total output usage. See [Gemini thinking](https://ai.google.dev/gemini-api/docs/generate-content/thinking).
`Completion.latency_ms` includes the whole request. `Attempt.latency_ms` excludes
retry backoff: use the successful attempt for per-model latency and count all attempts
for token totals. Neither token counts nor route smoke constitute H8 quality acceptance.


## Current H7 integration

See [H7 results](../../../../specs/p3-integration/h7-results.md) for the current
post-merge status. Free and Pro settings are distinct; oversize DeepSeek input is
rejected before HTTP with schema/framing/output reserved. The conservative context
and output limits were checked against the official model table on 2026-11-07.
`uv run python -m app.llm.smoke --live --output ../../outputs/gateway-live.json`
now defaults to the agreed generator/verifier pair. It records each Attempt and
successful-attempt latency. Rotate the exposed keys locally before running live.
`app.research.smoke --live` uses normal app settings and canonical P1 schemas.
This session's k=12 receipt is preflight only, with no real model metrics.
