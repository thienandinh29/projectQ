# P3 task checklist

## P3 implementation

- [x] Inspect checkout, ownership, contracts and missing dependencies.
- [x] Write manual spec/plan/tasks; note missing Spec Kit CLI/setup.
- [x] Add approved runtime dependencies and resolve lockfile.
- [x] Implement provider adapters, routing, retry, schema validation and family exclusion.
- [x] Test provider payloads, fallback, timeout and verification behavior offline.
- [x] Implement allowlist, safe HTTP reader and text/provenance extraction.
- [x] Implement candidate library manifest/downloader with cache and failure report.
- [x] Implement bounded research with injectable search and progress events.
- [x] Implement PDF/DOCX/link readers and unreadable-file handling.
- [x] Implement deterministic MCQ grading and learner-safe projection.
- [x] Test source restrictions, redirects, budgets, extraction and grading offline.
- [x] Implement all ten P3 route factories against published TEAM shapes and local protocols.
- [x] Test HTTP validation, upload extraction, grading, safe responses and missing backends offline.
- [x] Provide a clearly labelled fixture preview and OpenAPI snapshot for P5.
- [x] Write reserved migration 0007, validated upload metadata conversion and DB tests.
- [x] Implement real Brave Web Search adapter and default runtime factory.
- [x] Implement bounded Quick/Deep TopicPipeline with injectable cross-lane ports.
- [x] Test pipeline persistence/readiness, verification gates, timeout and cancellation.
- [x] Provide offline routing check and explicit one-provider live smoke CLI.
- [x] Write the single canonical teammate-AI integration guide: MERGE.md.
- [x] Run real source acquisition; retain failures and raw provenance outside Git.
- [x] Implement local re-audit/export to index.jsonl for P1 ingestion.
- [x] Run lint/format/type checks and complete test suite; start existing local test DB.
- [x] Write MAP update proposal and integration handoff in app/llm/README.md.
- [x] Replace the blocked OpenStax acquisition list with the LibreTexts manifest.
- [x] Implement search vendor configuration (SEARCH_PROVIDER=brave).

## Merge and live acceptance — delegated by the user through MERGE.md

- [ ] P1/P2/P4 translate final schemas and implement/mount real adapters.
- [ ] P2 merges 0003–0007 in order and configures private Storage/DB persistence.
- [ ] P1 approves source coverage; P2 indexes accepted JSONL within the DB budget.
- [ ] P1/P2 supply real model IDs/API keys and run the explicit provider/search checks.
- [ ] Team runs Quick/Deep end-to-end acceptance and records actual timings/costs.
- [ ] P1 updates root MAP; P5 regenerates client types from merged OpenAPI.

## P3 follow-up against pushed P1

- [x] Compare against P1 ml-core 5245e56 schemas/mocks and P2 service signatures.
- [x] Align index answers, hint levels/last_answer, citation pages, text limits, trace defaults.
- [x] Remove obsolete answer-label resolver requirement from P2 port/harness.
- [x] Run 19 offline compatibility checks using exact P1 Git blobs.
- [x] Export 8 audited P1 SourceMeta/ParsedDocument pairs; validate 1,255 blocks
      with P1's schema and chunker (17,390 chunks; no DB indexing).
- [x] Add offline/default and explicit live Brave smoke CLI; refresh runtime evidence.
- [x] Refresh fixture OpenAPI and write exact P2 wiring calls in contract-review.md.
- [x] Full suite 297 passed; lint, format and mypy passed.
- [ ] P2 mounts real adapters and connects TopicPipeline to worker with P4 gate.
- [ ] Live provider/search probes after runtime credentials/model IDs are supplied.
- [ ] Integrated H7 acceptance and P5 types from actual application OpenAPI.


## 2026-11-07 follow-up

- [x] SafeReader transition-address regression and push.
- [x] Sync main gateway; fix truncation retry, thinking and per-attempt telemetry; push.
- [x] Wire Retriever with provenance/order checks and canonical graph validation.
- [x] Add canonical graph/items smoke and sanitized measurement artifacts (public-book preflight; live blocked until key rotation).
- [x] Run full checks; record missing external prerequisites and handoff to P2/P4 in p3-follow-up.md.


## H7 go/no-go follow-up

- [x] Vietnamese manifest labels and audited Think Python source/chunk export (P1 semantic queries pending).
- [x] Mandatory retrieval and actual worker startup wiring; real SQL context/provenance tests pass.
- [ ] k=12 semantic Python graph review (real model + P1 queries required).
- [x] Distinct Pro model in local/template settings and long-context input guard; no model HTTP call on oversize input.
- [ ] Live canonical graph/items receipt after key rotation.
- [x] Replace learn.py public response DTOs after trunk integration; canonical schema imports and strict request subclasses.
