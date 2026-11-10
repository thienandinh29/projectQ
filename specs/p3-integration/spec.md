# P3 integration specification

Scope: the P3 lane in [TEAM.md](../../TEAM.md#lanes). Public shapes and ownership
come exclusively from its Contracts section; this document does not redefine them.

Deliverables: a typed LLM gateway with provider fallback and cross-family verification;
licensed source acquisition; bounded Deep Research; PDF/DOCX/link extraction; deterministic
MCQ grading; API orchestration using P1 engine/retrieval, P2 services/jobs, P4 content/tutor.

Acceptance: gateway validates structured responses and never verifies with the actual
generator family, including fallbacks. Source acquisition checks allowed domains on every
redirect and records provenance/license. Research has at most 15 searches, 12 reads, an
eight-minute deadline and requires three sources from two publishers. Uploads preserve
page provenance and reject oversized/unreadable documents. MCQ grading never uses an LLM.
Only verified items reach learners; response serialization excludes answer keys.

Integration acceptance: quick mode on three unfamiliar topics/files has graph and first
placement items within 60 seconds; deep mode within eight minutes. These require other
lanes and configured cloud credentials and must be reported separately from offline tests.

Non-goals: engine algorithms, new shared contracts, P2 infrastructure, authentication,
OCR, content generation prompts and verification policy owned by P4.

All automated tests use fixtures and fake transports. Secrets are never read from `.env`
by tooling or printed. No commit/push without authorization.

## API preparation before other lanes exist

Implement P3's published TEAM routes now as injectable router factories. Keep provisional
HTTP DTOs and backend protocols inside the three P3-owned route files. Do not create
or modify P1 schemas, P2 services/jobs/main, or P4 algorithms. These protocols describe
what P3 consumes; adapters can translate real lane interfaces later without changing
the published JSON shapes. Tests mount these factories in a test app with fake backends.
Production factories with no backend return 503 and never silently serve fixtures.
Only P3's route owners are included; topic status/SSE remain P2's.

Acceptance: all ten P3 endpoints have contract, invalid-input, missing-backend and
response-safety coverage. Topic creation enqueues rather than running research in HTTP.
Multipart/URL uploads enforce byte/type limits and invoke the real extractor. The
attempt route runs the real deterministic grader before asking the backend to apply
and persist engine updates. Pending items/hints and empty citations never reach learners.

## Finish P3-owned work; delegate cross-lane wiring in one merge guide

Add a concrete Brave search adapter (existing httpx dependency), default research
construction from explicit runtime settings, a bounded worker-callable topic pipeline
with injectable P1/P2/P4 ports, and the P3-reserved upload metadata migration 0007.
Provide opt-in provider smoke/config commands and exhaustive offline integration tests.
The single merge entry point is `specs/p3-integration/MERGE.md`, with exact ownership,
port methods, routing/configuration, migration order and acceptance commands.

Bulk source acquisition must produce a reproducible receipt and must not silently
accept content blocked by the source's own license notice. Downloaded files remain
git-ignored; manifest and acquisition summaries are reviewable. Missing credentials,
source approvals and cross-lane live acceptance remain explicit operational checks,
not fabricated successes. Do not commit/push or read .env.

## Follow-up: P1 contract alignment and library handoff

Compare against pushed P1 ml-core 5245e56 without modifying P1-owned files.
Align answer indexes, hint rungs/last_answer, citation pages and text limits. Grade
indexes directly rather than requiring an obsolete P2 answer-label translation.
Add a repeatable offline contract check using the exact pushed P1 schema/mocks.
Export the audited library as SourceMeta/ParsedDocument pairs alongside JSONL;
never export a rejected page or leave stale ingestible pairs after an empty audit.
Add an explicit opt-in Brave probe with sanitized results and no network by default.
P2 still owns DB adapters, transactions, mounting and worker wiring. Record exact
P1 engine calls and missing P2 services in the handoff, without claiming H7 is live.


## P3 retrieval and canonical smoke follow-up (2026-11-07)

Connect P1's async Retriever to TopicPipeline with an explicitly supplied library
subject. Select only durable indexed IDs from the prepared material, verify text,
URI and page against retrieval citations, and restore document reading order before
graph/items. Reject empty or inconsistent retrieval before model calls. Existing
ports remain compatible for uploads and P4 adapters awaiting integration. Validate
graph structure and item provenance with P1 contracts at publication.

Add an explicit live-only CLI under research that retrieves a small public topic,
calls graph/items with KnowledgeGraph/ItemSet, independently asks Gemini for blind
answers, and records per-attempt tokens, latency and sanitized errors. Artifacts are
smoke evidence, never a verified P4 topic or H8 acceptance; item status stays draft.
No new dependencies, HTTP routes or changes to P1/P2/P4-owned modules.


## H7 follow-up

Require retrieval in every TopicPipeline construction. Supply a production factory
inside the P3 research runtime for P2 worker loading, with one managed pool/embedder/
Retriever, explicit indexed subject, and lazy P4 content ports. Audit public book
exports before indexing: Vietnamese labels, article-only text, code whitespace,
natural page order, chunk sizes, source/page retention, and no lost non-whitespace
content. Record k=12 coverage as structural only until P1 queries and real models
are available. Never claim semantic graph quality from source or fake-model tests.
