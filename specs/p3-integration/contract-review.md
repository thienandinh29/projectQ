# P3 follow-up: P1 contracts and H7 handoff

Reviewed 2026-11-07 against pushed P1 `origin/p1/ml-core` at `5245e56`
(includes remediation, next-item, retrieval and library contracts), and P2
`origin/p2/platform` persistence services. No other lane's files were changed.

## HTTP boundary changes

- `AttemptInput.answer`: strict nonnegative integer index into public options.
  `hints_used` defaults to zero. The handler grades that index directly; the old
  `LearningBackend.resolve_answer` port has been removed. Preserve option order
  when loading from DB. Out-of-range indexes never write an attempt.
- Hint: level 1..4; `last_answer` is a nonnegative integer index or null.
- Citation: nullable section and optional page; retain signed upload URLs/pages.
- Topic goal limit 500 characters; ask question limit 1,000 characters.
- Trace prior/posterior, evidence and alternatives now have P1-compatible defaults.
  Timezone awareness and strict answer validation remain stronger boundary checks.
- Local DTO names remain to keep this lane runnable before P1 is merged. P2 must
  convert P1 models through `model_dump(mode="json", by_alias=True)` and
  `P3Model.model_validate(...)`, rather than passing unrelated BaseModel instances.
  No shared P1 contract was changed.

`tests/api/test_p1_contracts.py` validates 18 P1 request/response mocks in both
schemas and validates the library pair (19 checks). It reads pinned local Git
blobs, with no network; a shallow clone lacking the revision explicitly skips.
An additional HTTP test runs actual P1 placement/BKT/remediation/path with memory
storage. Neither check establishes DB durability or a live learner flow.
The refreshed P3 OpenAPI remains a **fixture preview**, not the integrated app.

Intentional policy/validation differences: P3 rejects Deep on Free, unsafe upload
links, bool/string answer indexes, blank IDs, naive trace dates and uncited tutor
text. These do not change P1 JSON field meanings. P2/P5 must use the integrated
app's OpenAPI for final client types.

## Exact P2 engine wiring

Mount factories as described in MERGE.md. The pushed P2 learning service currently
only has `save_attempt`, `save_mastery`, `save_review`; it does not yet implement
LearningBackend, learner history, graph/item loading or trace storage.

| P3 port | P1 calls and P2 responsibilities |
| --- | --- |
| `graph` | Load DAG/mastery, `Graph.from_contract`, `bkt.is_mastered`; keep prerequisite edge direction. |
| `placement` | Build ordered `placement.Answer` history; `placement.next_question(graph, answers)` returns a **concept slug**, not an item. Load a verified MCQ for that slug, convert trace. On completion call `placement.gap`; keep item=null. Persist `seed_mastery` once, not on every retry. |
| `next_item` | `path.next_step(graph, mastery, now=..., resume_origin=..., due_reviews=...)` returns NextStep + trace. Select verified item by concept and distance from target_difficulty; persist trace. A done step maps to None (route returns 404). |
| `apply_attempt` | In one P2 transaction, save the deterministic Grade, run `bkt.update_traced`, store mastery and traces, run `remediation.remediate` only for wrong answers, map `plan.to_contract()`, persist review state using P1 srs. Count only **earlier** misconceptions before this attempt. Store the remediation origin for later `path.next_step` resume. |
| `ask` | Create P1 `Retriever(pool, embedder)` at startup; await its search(question, subject, k=5), or module search(..., retriever=retriever). Use cited chunks with gateway + P4 support gate. Map source_title to title, section, authorized source_uri to url, and page. Never equate retrieved citations with verification. |

P2's `save_attempt` expects JSON-object answer data: wrap the index as
`{"index": request.answer, "hints_used": request.hints_used}` (internal storage,
not a new public contract). Map misconception slug to its DB ID separately.
The service currently has no hints parameter or trace API; P2 must persist these
within the same transaction rather than discard them. The topic worker must still
call TopicPipeline with P1/P4-backed ports. These are pending P2/P4 integration,
not completed by the fixture harness.

## Library ready for P1's reader

The existing export-only command now emits `source.json` (SourceMeta) and
`document.json` (ParsedDocument) in every audited book folder, alongside index.jsonl.
It preserves source URI/text and rechecks hash/license/scope. A zero-page audit
removes stale pairs. Manifest overrides `subject_slug`, `subject_name_vi`, and
`subject_name_en` are supported; defaults are book slug/title. Sections derive from
page URL paths; chapter is the book title. URL sorting is deterministic but is
**not publisher TOC order** or an inferred prerequisite order.

Actual local export: 8 books, 1,255 accepted pages, no rejected cached pages.
Validated all pairs with P1's exact schema and chunker/notebook at `5245e56`:
17,390 chunks. **No embeddings or database indexing were performed.** Raw files
are git-ignored and must be rebuilt/copied to P2's indexing machine.

```powershell
# Run from apps/api after merging P1's library/halfvec work.
uv run python ../../scripts/build_library.py --export-only --report ../../data/sources/library-index-report.json
uv run python -m app.rag.library ../../data/raw/library --tei-url http://localhost:8080 --build-index
```

P2 must enforce total DB/chunk limits, including other sources and uploads. P1
still reviews source coverage and subject naming before indexing. Acquisition
failures in acquisition-report.json are unchanged; TOC completeness is not claimed.

## Runtime and remaining H7 gates

Process-only check: zero of 31 gateway routing slots configured; Brave key absent.
No .env/credential files inspected, no paid model/search probe attempted.
The new Brave CLI defaults to offline config and --live makes exactly one scoped
search, rejecting empty/off-domain-only results without printing key/raw response.

```powershell
uv run python -m app.research.search
uv run python -m app.research.search --live
uv run python -m app.llm.smoke --live --provider vertex --tier free --task items
uv run python -m app.llm.smoke --live --provider bedrock --tier pro --task items
uv run python -m app.llm.smoke --live --provider openrouter --tier free --task items
```

Deploy must supply the model IDs/credentials in the existing LLM/search env
examples. P2 still mounts the routers, persists engine state/traces/reviews and
connects the worker; P4 supplies verified generation and tutor gates. Only then
can the team run topic -> worker -> graph/items -> attempt -> persisted mastery
and claim H7. P5 should regenerate types from that app and check the browser flow.
