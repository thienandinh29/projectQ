# P3 validation record — 2026-11-07

Branch: `p3`. Python 3.14.7, Windows, existing Postgres/pgvector compose service.

| Check | Result |
| --- | --- |
| Ruff lint, including library CLI | Pass |
| Ruff format check, including library CLI | Pass |
| mypy, including library CLI | Pass (69 source files) |
| Full API pytest suite | 268 passed, 1 existing Starlette/httpx deprecation warning |
| git diff --check | Pass |
| Library CLI --help | Pass |
| P3 HTTP router tests | 54 passed with fake backends, including real multipart extraction |
| P3 OpenAPI snapshot | Generated from the ten P3 route factories; fixture preview labelled explicitly |
| Vertex credential transport import | Pass |
| Live HTTPS source reader | OpenStax preface fetched; ~380 KB HTML, ~19K text characters |
| Source acquisition/export | 1,255 accepted pages across 8 books; all exported rows passed fresh hash/license/scope checks |
| Upload migration | 0007 tested on throwaway local DB: metadata, CHECK constraints and RLS denial |
| Worker orchestration | Quick/Deep pipeline, cited-item filtering, persistence/readiness, deadline and cancellation tests |
| Concrete search adapter | Brave request/response, domain filtering and sanitized failures tested with fake HTTP |
| Offline runtime config | runtime-status.json: 0/31 model slots configured; Brave key absent from process environment |
| Web tests | Not applicable: apps/web absent |
| Paid LLM calls / live search | Not run: runtime credentials/model IDs are not configured |
| API integration / end-to-end timing | Not run: other lane interfaces absent |

Initial full-suite run: 171 passed, 11 database setup errors (`connection timeout
expired`, localhost:54322). Started the repository's existing compose DB with
`docker compose up -d db`; subsequent full suite passed. The DB is still running;
no compose, engine, shared schema or main-app files were changed.

P3 offline coverage includes malformed structured output, provider fallback,
generator-family exclusion, missing verifier context, timeout/cancellation,
per-attempt telemetry (including rejected paid outputs), provider request mapping,
allowlist domain boundaries, redirect checks, private DNS rejection, body limits,
licenses/restrictions, research budgets, cached acquisition, retry, PDF/DOCX parsing,
unreadable/oversized documents, MCQ validation and answer-key removal.

HTTP coverage includes topic enqueue and Free/Pro restrictions, required inputs,
answer-key projection, pending-item rejection, objective attempt grading, invalid
answers without writes, null completed-placement items, multipart/URL upload, type/
body limits, unreadable files, verified/cited hint checks and unconfigured-backend 503s.

Additional checks cover upload MIME preservation, canonical Storage provenance,
non-bypass-role RLS denial, per-page hash/license export rechecks, encoded book URL
boundaries, footer license evidence and undeclared-page rejection. Pipeline progress
sink failure is bounded and sanitized rather than leaking internal errors.

All automated tests use fake model/network transports. No `.env` was inspected,
no real model call was made, and no commit/push was performed. See
`specs/p3-integration/MERGE.md` for the canonical teammate-AI merge instructions.

Final data receipts: `data/sources/acquisition-report.json` records the latest per-book
attempts and skipped/unlicensed pages (`complete=false` intentionally preserves these
gaps). `data/sources/library-index-report.json` records successful re-audit and export
of 1,255 usable pages from all eight selected books, with no rejected cached records.
The per-book `index.jsonl` files are in git-ignored `data/raw/library/`; rebuild them
on the indexing machine. Full publisher-TOC coverage is not claimed.

Final offline suite was rerun after the bounded concurrent export optimization:
268 passed, lint/format/mypy passed. There are no running acquisition/export jobs.


## 2026-11-07 P1 contract follow-up

- P1 reference: pushed ml-core `5245e56`; P2 services reviewed read-only.
- Ruff check/format and mypy: passed (70 source files).
- Full pytest: **297 passed**, one existing Starlette/httpx deprecation warning.
  Initial run had 283 passes and 13 DB setup errors because local DB was stopped;
  `docker compose up -d db` restored it and the complete rerun passed.
- 19 tests validate P3 models against pinned P1 schemas/mocks/library contract.
  These are local Git-blob checks; clones missing that commit explicitly skip them.
- Export-only audit: 8 books / 1,255 accepted pages / zero rejected cached pages.
  P1 schema + exact chunker/notebook loaded from the pinned revision validated
  every real pair: 1,255 blocks -> 17,390 chunks. No embedding/DB indexing.
- Gateway config: 0/31 slots configured; Brave key absent. No paid/live probes.
- Fixture OpenAPI refreshed. Production routers, persistence, worker and H7
  end-to-end flow still require P2/P4 integration; see contract-review.md.
- No .env read, dependencies added, commit or push performed.

One additional integration check runs the exact P1 placement/BKT/remediation/path
modules through P3 HTTP routes with in-memory storage. This confirms the wrong-answer
engine-to-DTO path; it does not verify DB transactions, retrieval or live H7.
