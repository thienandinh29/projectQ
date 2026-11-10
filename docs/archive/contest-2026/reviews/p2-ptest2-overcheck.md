# P2 overall check of ptest2 — 2026-11-07

Result: **NO-GO for the complete live demo**. A green unit/integration suite does
not prove the deployed entry point, worker and web practice flow are connected.
Reviewed the integrated working tree after syncing main `47b74b3` and ptest2
`c05f6e0` (canonical schemas and required retrieval), including P2's API/upload fixes. No generated content was marked verified.

## Open findings, ordered by demo impact

| Severity | Owner | Finding and evidence | Required check |
|---|---|---|---|
| High | P5 | The client has no `nextItem`; `use-learning.ts` calls placement every time `loadLesson` runs. The proxy allowlist excludes `next-item`. Placement completion therefore cannot lead to practice through this web flow. | Placement done → GET next-item through the proxy → practice answer → next question. |
| High | P2/P4 | Default `app.main` mounts `LearningService`, which reads flat `items.payload` and payload status. P4 `Repository.save_items` writes `payload.p4_item`, `external_id` and column status. Generated items cannot be read by the default service; the default tutor is also unconfigured. The separate `app.content.runtime` binds P4 but selects its linked-document-only upload backend, which rejects file bodies even when P2 storage is configured. | One documented production entry point serves a P4 persisted question and accepts a private-storage PDF upload. |
| High | P2/P3/P4 | New uploaded/researched material is persisted by `ContentPorts.index` without embeddings. Mandatory retrieval then searches a separately configured `RESEARCH_SUBJECT`. Library results cannot match the new upload chunk IDs; selecting the new topic subject instead gives NULL vector distances (`Retriever._query` converts the resulting score with `float`). This still prevents upload/deep-research jobs from reaching graph generation with a real retriever. | Embed new material, select its actual subject, and run upload -> actual SQL retrieval -> graph. Keep the exact provenance check. |
| High | P4/P3 | The initial batch requires six verified questions in total, without per-concept coverage or follow-up generation. Placement still returns 503 if its chosen concept has no usable question. All 45 checked-in golden items remain `needs_review`; their declared generator is `gpt`, which the current gateway verification scope rejects before a live verifier call. | Publish a verified batch covering every concept the placement walk can select; run the real verification gate on supported generator metadata. |

A real PostgreSQL probe confirmed that an unembedded chunk returns a NULL score
and `float(score)` raises TypeError. The probe was rolled back.

P3's new `84883ad` addresses the earlier missing retriever, all-chunks equality,
library-metadata bridge and page-URI findings. Those earlier findings are not
reported as still open above. A configured library subject now bypasses the English
slug matcher. Full live generation and graph quality at k=12 remain unverified.

## P2 fixes and verification

- Main and P4 are merged into ptest2; latest P3 gateway preserved; PR #17 targets main.
- Both learning adapters rotate unseen questions, then reuse the oldest answered
  question, and skip concepts with no usable practice question. Regression tests pass.
- API startup fails without a key unless explicit local development is enabled.
- Retry receipts are stored in the learner-locked learning transaction. The web
  supplies one client attempt UUID per submitted answer and preserves it on network retry.
- Overcheck reproduced and fixed retry-after-answer-key-change and reuse of uploaded
  chunks through goal-only selection. Uploaded-source tutor calls also require demo
  mode and recorded consent before cache or model access.
- Uploads require demo mode and accepted notice; consent is persisted and checked by
  the worker. `app.uploads.purge` deletes files and derived topic data after the demo.
  Purge tests use real PostgreSQL with fake object storage, including rollback/retry.
- Migrations 0001–0011 are applied on the local nodetrail database. The P4 proposal
  is promoted to 0009; test setup no longer applies a second conflicting schema.
- Web CI now runs frozen install, lint, type checking and tests.

Final checked code head `5ee95cd`: Python **1,389 passed**, web **46 passed**, ruff,
format and mypy passed. These results include PostgreSQL-backed tests, but model
responses and object storage in those tests are fakes.

Live routing: the exact `uv run python -m app.llm.smoke --live` call reached
DeepSeek successfully. The paired DeepSeek → Gemini probe failed on Gemini HTTP
503 after two attempts; see `docker/p2-live-gateway.json`. This is not an H8 score.

Indexing: clean P3 exports passed all three local chunk audits. Think Python is
committed (391 chunks); Logic is committed (331); Statistics is running. The ordered runner covers **391 Think Python + 331 Logic + 597 Statistics + 15 golden chunks**.
`--build-index` executes only after all material has been loaded. Until its receipt
says `stage=complete`, **ready/library-indexed remains unchecked**. Live progress:
`data/sources/p2-index-progress.json`; local logs: `data/raw/p2-index-runner.*`.
One real TEI + SQL query during bulk indexing took **25.957 seconds** and returned
three citations. This does not meet the ~1-second query target under that load;
finish bulk work and repeat the latency check before the demo. It is not a scored
retrieval evaluation (`docker/p2-python-retrieval-smoke.json`).

Not checked: browser visual QA, real Supabase object deletion, full live
topic → placement → remediation → review flow, or H8 human-labelled quality.
