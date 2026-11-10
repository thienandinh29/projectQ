# Contract review (H0–H1 draft) — reply "OK" or list problems by the deadline P1 sets

Implemented in `apps/api/app/schemas.py` and `apps/api/app/engine/trace.py`, tested in
`apps/api/tests/engine/test_contracts.py`. `TEAM.md` → "Contracts" stays the source of truth; the points below are
the choices the code makes where `TEAM.md` is silent. Each needs an answer before the H3 freeze.

| # | Decision in the draft | Affects |
|---|---|---|
| 1 | `POST /attempts.answer` and `/tutor/hint.last_answer` are the **option index** (0-based, order as sent), not the label | P3, P5 |
| 2 | Item ids in the API are the **fixture id string** (e.g. `plr-001`); the DB `items.id` is a uuid, so `0005` should add a unique `items.external_id` (or P3 maps them) | P3, P4, P2 |
| 3 | `CitationRef` (hint/ask citations) adds optional `page` beside `{title, section, url}` so the web opens the right PDF page | P3, P4, P5 |
| 4 | `DecisionTrace.prior` / `posterior` may be `null` (e.g. a `review` trace); all `evidence` fields optional | P2, P5 |
| 5 | Every contract model rejects **unknown keys** (`extra="forbid"`): typos in YAML or requests fail loudly | all |
| 6 | Items without `status` load as `needs_review` (safe default: never served until verified) | P4 |
| 7 | `Concept.sources` needs ≥ 1 entry; `Item.chunk_ids` ≥ 1; slugs are kebab-case, ≤ 80 chars | P4 |
| 8 | `/tutor/hint.level` is 1–4; `HintResponse.citations` needs ≥ 1 (no citation, no hint) | P4, P5 |
| 9 | `retrieve.search` returns `Citation{chunk_id, source_title, publisher?, license, chapter?, section?, source_uri, page?, content, score}` | P3, P4 |
| 10 | SSE `GET /topics/{id}/events` sends `TopicState` as the event payload; event names `state` and `heartbeat` | P2, P5 |
| 11 | Migration `0003` drops the HNSW index; `app.rag.store.build_vector_index(conn)` rebuilds it after bulk loading | P2 |
| 12 | `placement.gap(...)` returns `str \| None` (None = no gap found, e.g. top question answered correctly), matching the optional `gap_slug` | P3 |
| 13 | Placement is stateless: P3 loads the learner's placement answers `[(concept_slug, correct, item_id)]` and calls `next_question(graph, answers)`; P2 persists `placement.seed_mastery(...)` as the starting `p_known` | P2, P3 |
| 14 | An item is attached to a concept (`ItemSet.concept`), so P3 picks an unserved `verified` item of the slug placement returns | P3, P4 |
| 15 | `retrieve.search` needs a pool and an embedder, so P3 builds one `Retriever(pool, embedder)` at startup and calls `await retriever.search(query, subject, k)` (also `search(..., retriever=)`); it is **async** | P3, P2 |
| 16 | P2 adds `EMBEDDING_BACKEND` (`tei`\|`local`), `TEI_URL`, optional `TEI_API_KEY` to `config.py` and `.env.example`, then `make_embedder(...)` builds the client | P2 |
| 17 | `sources` has no publisher column, so `Citation.publisher` is always `None`; the web's source list needs one (additive migration, P3's `0007` is the natural place) | P3, P2 |
| 18 | `httpx` moved from dev to runtime dependencies in `apps/api/pyproject.toml` (already locked; P2 owns the lockfile, please re-check) | P2 |
| 19 | Migration `0004` `decision_traces` (P2 stores, P3 returns): one row per `DecisionTrace`; `kind, at, prior, posterior, rule, rule_vi` are columns, `evidence` and `alternatives` are jsonb written with `trace.model_dump(mode="json")` and read back by passing the row to `DecisionTrace.model_validate` (round trip is tested). The slug has no foreign key: it is stored with `subject_id` so history survives a graph rebuild. `attempt_id` links the attempt (nullable, cleared if the attempt is deleted). `prior`/`posterior` are `double precision` so stored numbers equal the engine's exactly | P2, P3 |
| 20 | `graph.root_cause` now treats a prerequisite as weak below `WEAK_THRESHOLD` (0.5), not "not yet mastered" (0.95): fixed a bug that sent a learner placed as known (0.85) back to a concept they know. P3 should call `remediation.remediate(...)` after a wrong answer instead of `root_cause`; `plan.to_contract()` is the API `remediation` (`None` → omit it) and the returned trace goes in `traces` | P3 |
| 21 | `misconceptions` has no `slug` column, but item files identify misconceptions by slug and remediation counts repeats by key. P4's `0005` should add `misconceptions.slug` (unique per concept); until then traces would carry database ids | P4, P2 |
| 22 | P2/P3 need "the misconception keys of this learner's earlier wrong answers on a concept" (from `attempts.misconception_id`) to pass as `earlier_misconceptions`; a service for it belongs in P2's `app/services/` | P2, P3 |
| 23 | New contract, P3 → P1 → P2: a book is a folder with `source.json` (`SourceMeta`) and `document.json` (`ParsedDocument`: blocks in reading order). Readers do **not** split text; `chunker.py` does. Example: `specs/contracts/library-example/`. `app.rag.library` indexes every folder, validating all before embedding any | P3, P2 |
| 24 | `ND` (NoDerivatives) licences are rejected when `source.json` is read, as `SPEC.md` requires; the library folder location (e.g. `data/library/`, git-ignored) is P3's choice, the command takes any path | P3 |
| 25 | `Chunk.page` is now stored in `chunks.page` (the column already existed); PDF citations carry the page; `chapter_no` may be `null` for uploads | P3, P5 |
| 26 | `GET /next-item` (P3): call `path.next_step(graph, mastery, now=..., resume_origin=..., due_reviews=...)`; it returns the **concept**, a `target_difficulty` (0-1) and `reason_vi`, and P3 serves an unserved `verified` item of that concept with difficulty near the target. `NextItem.reason_vi` is the step's reason; the trace goes to "Vì sao?". `kind == "done"` (`concept_slug is None`) means nothing is left to learn: show reviews or the exam plan instead | P3 |
| 27 | Inputs P2/P3 must supply to `next_step`: the learner's `p_known` per concept (`mastery`), `due_reviews` as `{concept_slug: due_at}` from `review_cards`, and `resume_origin`, the concept of the learner's most recent `remediation.review_prerequisite` while it is not yet mastered (derive it from the stored traces; nothing new to store) | P2, P3 |
| 28 | Review hardening: duplicate `Item.id` values within an `ItemSet` are rejected before ingestion/grading. P4 generation must repair these rather than overwrite a question. JSON fields are unchanged | P4, P3, P2 |
| 29 | `srs.make_scheduler()` and `review()` now use deterministic scheduling by default. P2 can replay the same stored state/answer/time without randomized due-date drift. Explicit `make_scheduler(fuzz=True)` remains available for callers choosing randomized scheduling | P2 |

