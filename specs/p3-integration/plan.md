# P3 implementation plan

Follow [TEAM.md](../../TEAM.md#timeline); work on the user-selected `p3` branch.
Spec Kit commands/constitution are absent in this checkout; these three documents are
the manually authored specify/plan/tasks artifacts, not output claimed from that CLI.
P2 must supply its Spec Kit setup before the team's formal workflow can be completed.

1. Build injectable asynchronous provider adapters and gateway. Use existing public
   `complete` interface; add request-scoped gateway metadata for actual selected model
   and generator-family exclusion. Keep provider SDK imports inside `app/llm/`.
2. Share a bounded HTTP reader between research, library downloads and uploaded links.
   Check HTTPS, domain boundaries, public DNS addresses and redirects; enforce response
   byte limits. Parse HTML with stdlib; preserve page/section provenance.
3. Add PDF and DOCX text extraction, licensed library manifest/CLI with resumable cache,
   research search-provider injection, strict budgets and Vietnamese progress events.
4. Implement pure MCQ grading and safe learner item projection.
5. Implement P3 route factories against the published TEAM HTTP shapes now. Local typed
   protocols define P3's backend needs without claiming to be P1/P2/P4 interfaces. Use
   fixtures only in test backends, validate behavior at the HTTP boundary, and provide
   503 responses when no backend is configured. Translate real lane APIs with adapters
   once available. Do not edit P2 main/services/jobs or P1 schemas.

User approved httpx, google-auth, boto3, PyYAML, pypdf and changes to API pyproject/lock.
Other dependencies require separate approval. Models and search provider remain runtime
configuration decisions, not assumptions about account access or current model support.
User additionally approved python-multipart for the published file-upload contract.

Checks: ruff lint/format, mypy, pytest; isolated offline tests first, full suite afterward.
Report missing DB/cloud prerequisites honestly. Coordinate MAP updates with P1.


Follow-up execution: pin P1's pushed contract revision for offline regression,
update P3 boundary fields and eliminate answer-label translation, retain lane
ownership. Extend audited library export with P1's two-file format; validate both
sample exports and actual cached library against P1. Add explicit Brave smoke CLI;
record only process presence/config booleans. Refresh OpenAPI/runtime receipts and
hand P2 exact engine/transaction/retrieval calls through contract-review.md.


Follow-up: add optional Retriever injection and explicit subject/k to TopicPipeline;
validate returned provenance and canonical KnowledgeGraph before save. Test reversed
rank order, foreign IDs, changed text/URI/page, empty retrieval, malformed graphs and
foreign item sources. Add a bounded canonical graph/items smoke CLI with explicit
--live, a local PostgreSQL read and TEI, plus a read-only book-folder mode when
retrieval is unavailable. Keep live results separate from deterministic tests.


H7 execution: label all eight manifest subjects, re-export cached HTML without UI
chrome, add audit-only to build_library; require Retriever/subject parameters and
connect a production research runtime factory. Extend live smoke defaults and
per-successful-attempt latency reporting; configure distinct Pro model without
printing or transmitting secrets. Keep live calls pending key rotation.
