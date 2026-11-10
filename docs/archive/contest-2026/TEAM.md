# TEAM — 24-hour parallel build (5 people + AI agents)

Goal: the demo in `SPEC.md` ("Competition demo"): a judge names **any** topic (or uploads a file) and NodeTrail
builds a cited learning path live. No subject is prepared in advance. Every agent reads this file; follow it exactly.

Before H0, ask the organizers: (1) are AI coding agents allowed, (2) may the textbook library be indexed before
the contest, (3) may code written before the contest be reused, (4) how long is the final-round demo (the last pitch
was cut to 3 minutes). If (3) is "no", start a fresh repo with this same plan; (4) decides the demo script.

The plan has two versions, chosen by the answers to (2) and (3); see "Before H0 checklist":
- **Pre-H0 allowed:** the draft `schemas.py`, the throwaway-schema `conftest.py`, migration `0003` and (if (2) is
  "yes") the library download + index are done before H0. The timeline below still holds; those rows become checks.
- **Everything from H0:** follow the timeline exactly as written.

## Rules that make parallel work possible
1. **Contracts first.** P1 drafts data formats, API shapes and Python interfaces by **H1**; frozen at **H3**.
2. **Stay in your lane.** Edit only the paths your lane owns. Need a change elsewhere? Ask the owner.
3. **Fixtures, golden topics and stubs until integration.** No lane waits for another: P4's golden topics give real
   data from H3, P5 builds on mock JSON from H1, P2's stubs serve every route by H3.
4. **Small PRs, CI green.** P2 merges routine PRs; contract or architecture changes need P1's approval. Nobody pushes
   to `main`.
5. **Spec Kit for every lane (the examiner asked for it):** `/speckit-specify` → `/speckit-plan` → `/speckit-tasks`
   in the folder Spec Kit creates under `specs/` before an agent writes code; one page per document. Plans follow the
   contracts in this file (link, never copy them). The constitution (`.specify/`) is written from `CLAUDE.md`'s
   principles and repeats "edit only your lane's paths", so `/speckit-implement` stays in the lane. Work stays on the
   lane branch: if Spec Kit creates a feature branch, merge the spec back into the lane branch and delete it.
   **Exempt** (a short PR description is enough): bug fixes, changes under ~30 min that stay inside an existing spec,
   and everything after the H20 freeze. A change that adds a route, a contract field or a new module is never exempt.
6. **Integration before the checkpoint.** Pieces due at H8 are merged by **H7**; H7–H8 is the first end-to-end run.
7. **Feature freeze at H20** (moved from H18 by the lead on 2026-11-07, for integration and bug fixes only). After that, only bug fixes, rehearsal and the backup video.

## Handoff board (P1 → everyone; read your row, tick it off, reply in PR #1 or to P1)
Status of P1's work: [PR #1](https://github.com/thienandinh29/SenaEmpire36/pull/1) (`p1/ml-core`): contracts, engine,
retrieval, migrations `0003`–`0004`. Details and open contract decisions: `specs/contracts/review.md` (19 items).
**Contracts are still a draft until the H3 freeze: reply "OK" or list concrete problems (silence is not agreement).**

| Lane | What P1 needs from you | Read |
|---|---|---|
| **P2** | [ ] Review and merge migration `0003` **before bulk indexing (~H5)**, then `0004`, in number order. [ ] Add `EMBEDDING_BACKEND` (`tei`\|`local`), `TEI_URL`, optional `TEI_API_KEY` to `config.py` and `.env.example` (P1's agent cannot read or edit those files), then build the client with `make_embedder(...)`. [ ] Re-check `uv.lock`: `httpx` is now a runtime dependency. [ ] **Hosting** (see Hosting decision): pick the machine and OS, run the compose stack and the named tunnel on it, plan a standby, keep it awake. [ ] Bulk indexing runs on the host with the **TEI CPU image** (TEI's GPU images do not support the GTX 1060): `python -m app.rag.library <library> --tei-url <TEI> --build-index` (validates every book first; `app.rag.ingest` is only for the Think Python notebooks). Build the index once, after the last book. [ ] Store traces in `decision_traces` (`trace.model_dump(mode="json")` in, `DecisionTrace.model_validate` out). [ ] H3 check: query embedding < ~1 s on the host. [ ] Langfuse cost and latency per model exportable by H6 (model test). [ ] A service that returns a learner's earlier misconception keys on a concept (from `attempts.misconception_id`). [ ] Services for `next_step`: a learner's `p_known` per concept, `{concept: due_at}` from `review_cards`, and the open remediation's origin (from the stored traces). [ ] **From P1's `ptest2` review** (`specs/contracts/p1-ptest2-review.md`): [x] **Merged main + p4 into ptest2, preserving latest gateway; PR #17 to main.** Integration trunk is **`ptest2`** (**P1 confirmed 2026-11-07**): P2 merges `main` (now ahead of it) and `p4` into it with each owner resolving their own files (9 conflicts), then one PR to `main` (#1). [x] **`/next-item` fixed in both adapters: unseen first, oldest fallback, skip empty concepts; acceptance regression passes (#2).** [x] Idempotent `POST /attempts` with `client_attempt_id`, complete response replay and concurrent-retry regression (#5). **Indexing time:** your own measure is 1.09 chunks/s on the CPU, about 4.4 h for the 17,390-chunk export; **Index subset (P1 decided 2026-11-07, golden topic = learning Python):** make a library folder holding only these book folders and index it with the same command, in this order: (1) `think-python-2e` (244 pages; the Python source, about 1 h at 1.09 chunks/s by page count, an estimate), (2) `logic-critical-thinking` (48 pages) and (3) `introductory-statistics` (71 pages) so the H8 check has non-Python topics, about 25 min together (estimate). Build the vector index once after the last of these (`--build-index`). Index the remaining five books afterwards in the background, or skip them; do not block H7 on them. Also index P4's golden chunks (`data/golden/*/chunks.jsonl` on `p4`, tiny) so retrieval evaluation can run. Note: P4's Python golden topic cites Think Python 3e (web), the library holds Think Python 2e (LibreTexts, CC BY-NC 3.0, non-commercial demo only); both are fine, but the citation URLs differ. [x] Phase = placement only until a `placement.done.*` trace exists, no remediation during placement (#6). [x] Refuse to start without an API key unless a local-dev flag is set (#4). [x] P4 unique `external_id` in migration 0009 (#7). [x] Web job in CI (#8). [x] **Demo-only upload notice + persisted consent + worker/tutor/reuse guards** (`SPEC.md`). [x] Purge uploaded file, chunks and derived topic/audit/cache data via `uv run python -m app.uploads.purge --all-demo` after stopping the worker. [x] Exact live DeepSeek smoke passes; [ ] paired Gemini verification (HTTP 503). [x] Clean Think Python 2e (391) and Logic (331) indexed. [x] Statistics (597) indexed; SQL confirms all three books embedded. [x] P4 shared-title fix reimported twice: 15 stable chunks, no duplicates; golden embeddings and final vector build complete (`data/sources/p2-index-progress.json`, 2026-11-07 22:58 Vietnam). [x] `ptest3` P2 factory `app.main:create_content_app` joins P4 learning/tutor to P2 private uploads/queue; nine factory tests pass, including real SQL. Docker/DB/TEI restored. Latest local ptest2/P4 3c3a8e0: API 1,419 pass/0 fail/0 skip; web 46 pass/build pass; CI green. **NO-GO live**: zero verified items, missing durable map confirmation, web next-item and upload/retrieval integration. New Gemini key model-list HTTP200; generation untested during preserved cooldown. Current P2 backend evidence: `specs/p2-graph-confirmation/validation.json`. Current startup: `docker/LOCAL.md`. [x] P2 durable confirmation migration0012/service + integrated private-upload factory implemented on local ptest2; 1,436 API tests pass, including real SQL coverage; no auto-confirmation. HTTP DTO/authenticated action and UI remain P1/P3/P5 handoff: `specs/p2-graph-confirmation/handoff.md`. **Overcheck at 5ee95cd: local Python 1,389 + web 46 pass, lint/format/mypy pass; full demo remains NO-GO.** ? waiting on P5 practice client/proxy and P2/P3/P4 runtime/upload embedding/placement coverage; see `specs/contracts/p2-ptest2-overcheck.md`. | `review.md` #11, #16, #18, #19, #23, #27; `specs/retrieval/`, `specs/library/`; `specs/contracts/p1-ptest2-review.md` |
| **P3** | [x] Build one `Retriever(pool, embedder)` at startup; `search` is **async**: `await retriever.search(query, subject, k)`. [ ] Placement is stateless: load the learner's placement answers, call `placement.next_question(graph, answers)`, persist `placement.seed_mastery(...)`; `gap` can be `None`. [ ] **Readers and `build_library` emit one folder per book**: `source.json` + `document.json` (blocks in reading order; do not split text; `page` for PDFs; ND licences are rejected). Copy `specs/contracts/library-example/`; at H5 index one real HTML book and one real PDF with P1. [ ] H5–H6: list the models the gateway can reach (exact IDs) and smoke-call each, then run P1's model test (`specs/model-test/`) at H6–H7. [ ] Return `traces` from `/attempts` and `/placement/next`. [ ] `GET /next-item` calls `path.next_step(...)` (`specs/next-item/`): serve an unserved verified item of the returned concept near its `target_difficulty`; `kind == "done"` means show reviews or the exam plan. [ ] After a wrong answer call `remediation.remediate(...)` (not `root_cause`): pass the wrong option's misconception and the learner's earlier ones on that concept; `plan.to_contract()` is the `remediation` field (`None` → omit) and its trace goes in `traces`; use `remediation.resume` for the step after. [ ] `answer` is the 0-based option index; map the API item id to the DB uuid (needs `items.external_id`, see P4). [ ] `Citation.publisher` is always `None` until `sources` gets a publisher column (your `0007`?). [x] **Model decision** (LLM bullet in Stack; `routing.yaml` already matches it): set `DEEPSEEK_PRO_MODEL` apart from the free one; check DeepSeek's input limit for graph extraction. [ ] **From P1's `ptest2` review** (`specs/contracts/p1-ptest2-review.md`): `SafeReader` also rejects `64:ff9b::/96` and `::/96` (#10); (#9, the model family type, is resolved on `main`: DeepSeek is supported; live acceptance still needs credentials); after the trunk merge, replace the duplicate data shapes in `learn.py` with imports from `app/schemas.py`. **Always build the research pipeline with a retriever and an explicit subject** (without one the citation checks are skipped), and check graph quality at the default `k = 12` on the Python topic. [x] **H7 pre-index checks (P3, 2026-11-07):** all 8 manifest books have explicit Vietnamese/English subject labels, keeping existing slugs; cached exports rebuilt without LibreTexts chrome. Think Python audit passes: 244 source pages, 391 chunks, median 1,404/max 1,800 characters; see `data/sources/p3-python-library-audit.json`. [x] P3 confirmed all 10 P1 label snippets in the intended numbered sections; exact URLs are in `data/sources/p3-python-query-label-audit.json`. [ ] P1 semantic review and real ranked retrieval remain pending. [x] **H7 runtime wiring:** worker `--pipeline` creates one cached Retriever, validates explicit `RESEARCH_SUBJECT` before claiming jobs and passes it with k=12. No constructor bypass remains. Real SQL tests check page/root provenance and selected-context bounds with fake embeddings/models. [x] `learn.py` responses now import P1 schemas after the trunk merge; strict request validation retained. [ ] k=12 semantic graph quality and live model receipts remain pending rotated keys and actual indexed TEI retrieval. [x] **H7 model setup:** local/template Free `deepseek-flash` vs Pro `deepseek-v4-pro`; long-input byte/output budget guard tested before HTTP. Default gateway live smoke now runs the agreed pair and records successful-attempt latency; see `specs/p3-integration/h7-results.md`. [ ] Live graph/items and semantic k=12 review are not accepted: user last reported unrotated keys; P1 query label existence is checked but not ranked retrieval; local TEI/base/P4 schemas unavailable (`data/sources/p3-h7-readiness.json`). [x] **Final code checks at `b7b6619`:** API Ruff/mypy pass, 1,394 API tests and 46 web tests pass. P1 label audit confirms 10/10 snippets in the intended sections. Latest P2 Python index receipt confirms the clean 391 chunks; old 2,764-count snapshot is superseded. Live/semantic acceptance remains unticked. [x] **P3 graph confirmation HTTP boundary (2026-11-07):** on P2 `657c09f`, GET `/graph/review` pairs public graph + revision; explicit POST `/graph/confirm` uses hashed opaque learner session (migration0013), never a browser UUID. Proxy forwards only that cookie. Real SQL tests cover reload, stale graphs, scope, retry and expiry; API 1,443 tests/web 50 tests + build pass. P2/P5 rollout/UI handoff: `specs/graph-confirmation/handoff.md`. [x] **Verifier readiness audit:** 15 live-artifact items, **0 currently verified** against current chunks; **0 live calls this run**. [ ] Live probe/batch remains blocked by saved checkpoint until **2026-11-08 07:59:46 UTC** (14:59:46 Vietnam); do not reset it. Six verified items / three concepts / prerequisite chain and full E2E remain unaccepted. Receipt: `specs/graph-confirmation/verifier-readiness.json`. | `review.md` #1, #2, #12–#15, #17, #20, #22–#27; `specs/engine/`, `specs/remediation/`, `specs/library/`; `specs/contracts/p1-ptest2-review.md` |
| **P4** | **Status 2026-11-07: blocked b?i quota/API; 0/15 verified persisted, 0 concepts; 20 cases prepared, 20 unfinished. See apps/api/app/content/P2-BATCH-HANDOFF.md.**  [ ] **Golden topic #1 by H3** (chunks, `graph.yaml`, items): retrieval evaluation waits on it. [ ] Graph and item files must load through `KnowledgeGraph` / `ItemSet` in `app/schemas.py` (cycles, one correct option, a misconception per wrong option are rejected; items without `status` count as `needs_review`). [ ] **By H6** for the model test: chunks for the held-out topic #3, and 20 verification cases (10 planted-wrong items made by flipping the key of verified golden items, 10 untouched). [ ] `metrics.py` stays thin: `evalkit.labels.load_records` → run the gate on each record → `evalkit.guardrail.score` (method, planted items and the labelling hour: `specs/guardrails/`); ≥ 36 planted items by H14. [ ] Label **≥ 20 Vietnamese questions** for retrieval evaluation, in the format in `data/eval/README.md`. [ ] Migration `0005`: add `misconceptions.slug` (unique per concept; the table has none) and a unique `items.external_id` (the fixture id such as `plr-001`) or agree another mapping with P3. [ ] **From P1's `ptest2` review** (`specs/contracts/p1-ptest2-review.md`): your `p4` and P2's `ptest2` conflict in 9 files and neither contains the other (#1); the trunk is `ptest2` (P1 confirmed 2026-11-07): merge it into your work (or `p4` into it, with P2) and resolve P4's files. Item ids must be unique across subjects, or `0005` adds an external id (#7). | `review.md` #2, #6, #7, #14, #21; `data/eval/README.md`; `specs/contracts/p1-ptest2-review.md` |
| **P5** | [ ] Build screens on `specs/contracts/mocks/` (generated from the models and real engine output; **do not edit by hand**, ask P1 for a change). [ ] "Vì sao?" renders `DecisionTrace` (`rule_vi` is ready to show; `prior`, `posterior` and `evidence` fields can be `null`). [ ] Items never contain the answer; graph edges use the key `from`. [ ] SSE sends `state` and `heartbeat` events. [ ] H7–H8: ~35 min as a blind Vietnamese rater for the model test (P1 picks two raters). [ ] **H15–H16: the labelling hour, nobody sleeps** (`specs/guardrails/labelling-protocol.md`). [ ] **From P1's `ptest2` review** (`specs/contracts/p1-ptest2-review.md`): add `nextItem` to `lib/data-client.ts` and `next-item` to the proxy allowlist in `app/api/backend/[...path]/route.ts`, then wire the practice screen after placement to it (#3, **still open at `68b2371`; blocks the H7 run**); polling `GET /topics/{id}` instead of SSE is fine. [ ] **Upload notice** (P1 decision, `SPEC.md` Non-functional): show the Vietnamese notice from `SPEC.md` before the upload and require a tick; the text goes in the `vi` (and `en`) i18n file, not in the component. | `specs/contracts/mocks/README.md`; `review.md` #4, #10; `specs/contracts/p1-ptest2-review.md` |

**H7 go/no-go (P1, checked at about H7 against `origin/ptest2` `68b2371`, read-only; checklist in `specs/contracts/h7-run-sheet.md`): NO-GO.**
`ptest2` has not moved since about 10:47 UTC; CI is green on that head. Not merged: `main` (25 behind) and `p4`. Pushed work only; unpushed work on your own machine is not visible.
Met or partly met: migration files `0001`–`0004`, `0006`–`0008` exist (`0005` arrives with `p4`); the live DeepSeek→Gemini smoke is on `main` (not on `ptest2`).
Not met: (1) trunk merge; (2) `/next-item` still repeats answered items (`backend.py:227`); (3) web has no `nextItem` and the proxy lacks `next-item`; (7) `api_key` defaults to empty (auth off); (8) no app code passes a retriever and subject to the research pipeline; (9) the only Python golden topic is on `p4` and all 15 items are `needs_review` (none would be served). Unknown: (4) migrations applied on the host, (5) any library indexed, (6) keys rotated.
**Order of work (parallel where marked):** P2 + P4 merge `main` and `p4` into `ptest2` first, because `0005` and P4's content arrive with it. Then in parallel: P2 fixes `/next-item` (+ API-key startup check, idempotent attempts) and starts indexing `think-python-2e` (subset order is in P2's row); P5 adds `nextItem` and the allowlist entry; P4 runs the verification gate on the Python golden items so some become `verified`, and ships the 20 verification cases; P3 builds the pipeline with a retriever and subject, and checks graph quality at `k = 12`. Fallback if the checklist is still unmet at the start of H8: whole team on Nhanh with the golden or pre-generated topic. P1 re-runs the go/no-go when a lane ticks its row.

**Full-suite run on `ptest2` `ee5bc3f` (P1, about H7.5, scratch checkout; GitHub CI run 111 on this head also failed): not green.** ruff, format, mypy (153 files) pass; web lint and typecheck pass; Python 1,330 passed, **1 failed, 10 errors**; vitest 40 passed, **1 failed**. `ptest2` has since moved to `4ac891c` (P3, library subject labels), not re-tested. Fix in this order, each owner reruns their own test:
1. **P4 + P2 (10 errors, blocks green CI on PR #17):** `app/content/sql/0008_p4_runtime.sql` re-adds `topic_jobs.mode` and `upload_id`, which `supabase/migrations/0008_topic_inputs.sql` already adds, so `tests/content/test_runtime_database.py` fails with `DuplicateColumn` when it installs P4's schema over the migrated database. Remove or guard the duplicate lines; `supabase/migrations/` stays the only schema source (P4's file must not number-clash with a migration either).
2. **P4 + P3 (1 failure):** `tests/guardrails/test_answerability.py::test_plain_team_gateway_response_has_unknown_identity`: the gate raised a `ValueError` (fails closed, so the item is `needs_review`) instead of returning an unknown verifier identity. Likely, not confirmed: the merged gateway's `verification_scope` accepts only gemini, claude or deepseek as generator family, the fixtures use "gpt", and P4's content gateway never calls `verification_scope`. Check that P4's verifier reaches the real gateway before the H7 run; this is the gate the Python items depend on.
3. **P2 or P5 (1 vitest failure):** `lib/integration-contracts.test.ts:56` expects `evidence.correct` to be `undefined` but the decoder returns `null`; the engine's real output is `null`, so fix the test or map `null` to `undefined` in the decoder.
4. **P2, P3, P4 (warning):** `/ask` is registered twice (`Duplicate Operation ID ask_route_ask_post`, `app/api/tutor.py`); pick one router so the answer does not depend on mount order.
Earlier findings 2, 3, 4, 5, 7, 8 were still open at `ee5bc3f` (P2 says the `/next-item`, auth and retry work is in progress on PR #17).

**Update from P2's local run and P4's diagnostic (P1, about H8.2):** (a) **The golden-indexing `UniqueViolation` and P2's finding 2 are the same bug (P4):** in `app/content/repository.py::save_material`, sources with the same book title are merged into one database source but each keeps its own `chunk_index` counter, so two Biology parts both start at 0 and break `chunks_source_index_key` (unique `(source_id, chunk_index)`, from migration `0001`). Number chunks by the real database source id, keep each chunk's UUID and provenance, add a regression test with two same-title sources, then P2 re-imports the golden chunks and builds the vector index. (b) **Gemini (P3, P4):** the failures so far are 429, 503 and, in P4's diagnostic, a 30.58 s timeout with DNS, TCP and TLS fine; on `main` the gateway's transport timeout is 30 s. Not a proven quota or key problem. Send the **identical minimal request from P2's host and from P4's**: success on P2's and a timeout on P4's means P4's machine or network; both failing means key or model. Also list the models with the key to confirm `gemini-3.8-flash` exists, and try a longer verify timeout (about 90 s) once to see whether the real request is simply slow. (c) **P4's machine has no Postgres or Docker** (connection refused on 54322 and 5432): that is setup, not a code bug. P4 should rely on CI for database tests and have the verification gate run on P2's host, where `/health` returns `db: ok`. (d) **New gate to cover (P2, P3, P5):** the backend now returns 409 for practice, attempts and hints until the learner confirms the knowledge map. The run sheet has a new condition 10 and step 2a for it; P2, P3 and P5 name the route and the UI control. P4's tests supply the confirmation in the test fixture only, never by weakening the production check. (e) Still needed from P4: at least 6 verified items across 3 or more concepts with a prerequisite chain and a current audit; do not change a status by hand.

**Status at about H17.5 (P1, 22:50 UTC 2026-11-07; read-only checks in scratch copies, nothing run on the host):**
- **`ptest2` `34383cc` is green:** CI run 167 passes, and P1's local run gave 1,552 API tests and 50 web tests with lint and mypy clean. It includes P3's `POST /graph/confirm` route (`app/api/graph_confirmation.py`). PR #17 is still a draft; P2's own verdict there is "complete live demo remains NO-GO".
- **First live evidence (P4, branch `mtri`, `outputs/live-lesson-acceptance.md`):** an uploaded PDF went through real bge-m3 embeddings, a graph confirmed in the UI, 7 verified questions, graded answers and 3 verified hints with citations in 162.7 s including one retry (DeepSeek generates, Gemini verifies). **Deep Research for "tôi muốn học Python" failed live** (no 3 sources from 2 publishers). **No live run of the Quick-mode Python path is recorded**, and the PDF record does not mention placement, remediation, mastery or review. Gemini works with the new key but is flaky (503s and timeouts; 1 of 15 Python items verified).
- **Branches:** `p5`, `p5-ui-test` and `p3-research-gateway` merge cleanly into `ptest2` (trial merge). **`mtri` conflicts with `ptest2` in 23 files** (gateway, `main.py`, pipeline, research agent, tutor hints, graph-confirmation service, the web proxy route and tests). Its acceptance note says the fixes were not committed or pushed, so it is unclear whether `mtri` carries that code. `p5-curriculum-class` adds multi-lesson curricula and class dashboards (the spec lists the class view as post-contest).
- **Next, in order:** (1) P2 merges `p5`, `p5-ui-test`, `p3-research-gateway` into `ptest2`; (2) P4, P2 and P3 resolve the `mtri` conflicts together, keeping `ptest2`'s version of services P2 and P3 own and P4's evidence and fixes, with P5 reviewing web changes; (3) P1 leads a live run of path A (Quick, Python, library) from `specs/contracts/h7-run-sheet.md` section 0, then path B steps 3 to 9; (4) record a screen capture of the working PDF path as the minimum backup video; (5) pre-generate and pre-verify the Python topic before the demo, because live verification is slow; (6) once Gemini has a stable tier, run the planted-error test (all 20 cases are still unfinished).
- **Correction by P1 (the lead, 2026-11-07):** Deep Research is the team's signature and the demo's opening in `SPEC.md`, so it is **not** a bonus. The fallback chain in `SPEC.md` stays (Deep Research over 8 min, then Nhanh for the same topic, then a pre-generated topic said openly, then the backup video). The failed live run recorded above ran on P4's `mtri` branch, which lacks 7 `ptest2` commits (including the overnight research-discovery fixes), so Deep Research's status on the `ptest2` head is **unknown until it is run live there**; run it right after path A.
- **Decided by the lead (2026-11-07):** the feature freeze moves from H18 to **H20** (about 01:25 UTC, 08:25 Vietnam time, if kickoff was 05:25 UTC), for integration and bug fixes only, no new features; the rehearsals and backup video that were planned from H18 start at H20. **Still proposed, not agreed by the team:** park `p5-curriculum-class` until after the contest.

**Uploaded documents (P1, 2026-11-07, agreed with the team):** one uploaded PDF that teaches enough for a small lesson is the source and no external search runs; gaps are filled from the library (Quick) or the web (Deep); the 3-source rule is for external research only. This is what P4's `mtri` branch does (`outputs/live-lesson-acceptance.md`); it is not on `ptest2` yet, so it lands with the `mtri` merge. Now written in `SPEC.md`. To verify live: a PDF that is thin on one topic must show the outline naming the gap and the supplement being cited, which no run has shown yet.

**How to use the board (every lane, and every lane's agent):**
1. **Read it first.** At the start of a session, and before you wait on anyone, read your row and any `⏳` line that
   names you. Your agent checks the board to confirm the thing you are waiting for is not already done.
2. **Waiting on another lane?** Name the gap and the tag that will end it, in one line in **your own row**:
   `⏳ waiting on P_: <what> (ready/<tag>, since H_)`. Pick the tag from the table under Git workflow, or propose one.
   Keep working on fixtures, golden topics, stubs or mock JSON meanwhile (rule 3); do not stop.
3. **Finished something others wait on?** Merge it (CI green), then **tag it `ready/<what>`** (see Git workflow) and tick
   your row (`[x]`). That tag is the signal (or, if tags cannot be pushed from your environment, your ticked row on
   `main`): the waiting lane's agent sees it, deletes its `⏳` line, rebases and continues, with nobody asking anybody.
4. **Update it yourself, no approval needed.** Each lane edits only its own row (the one exception to lane-owned paths,
   like the reserved migrations) on its lane branch and opens a small PR titled `[P_] board: ...` that touches **only
   that row**. Nobody reviews it: merge your own once CI is green. Never edit another lane's row or any contract text:
   ask the owner.

**The contact: P1 (P2 while P1 sleeps).** Their one job is that **nobody waits on another lane's work.** They read the
board at every checkpoint and whenever a `⏳` line appears, and they tag the scheduled `checkpoint-h*` tags. For each
`⏳` they find who owns the work and make it happen, or remove the wait: reorder the work, give the waiting lane a fixture, stub or mock to build on, or take the
task over. A `⏳` older than ~1 hour is treated as a problem to fix now, not a note to leave.

Known gap, not a blocker: placement finds the exact gap in ~56–64% of runs with noisy (slip/guess) answers, against a
90% target; it is exact with clean answers and always finishes in ≤ 6 questions (`specs/engine/spec.md`). P1 decides
whether to relax the target.

## Lanes

| Person | Lane | Owns (only edits these) | Delivers |
|---|---|---|---|
| **P1** (lead, ML/AI engineer; 2 agents: retrieval + engine) | Lead + ML core | `app/schemas.py` (contracts), `app/engine/` (`bkt.py`, `srs.py`, `graph.py`, `placement.py`, `trace.py`), `app/rag/` (`embed.py`, `retrieve.py`, `rerank.py`, `notebook.py`, `store.py`, `ingest.py`), `app/evalkit/`, `data/eval/`, `tests/engine/`, `tests/rag/`, `tests/evalkit/`, `CLAUDE.md`, `TEAM.md`, `SPEC.md`, `PLAN.md`, `MAP.md`, `team/` | Contracts (draft H1, frozen H3); **retrieval**: `embed.py` (TEI client + managed-API fallback), cited retrieval, optional reranker, retrieval evaluation (golden topic #1 before H8, the rest after), library indexing code (`ingest.py`; P2 runs it), `source_uri` per chunk; **learner model**: BKT/FSRS (traced), root-cause tracing, graph-walk placement, `DecisionTrace`; **evaluation design** for guardrail metrics and the H8 model test; H8/H12 decisions; the algorithm part of the pitch. **No server or Docker work.** |
| **P2** (backend/DevOps; 2 agents: infra + services) | Platform | `apps/api/app/main.py`, `app/api/__init__.py`, `app/config.py`, `app/db.py`, `app/services/` (database layer), `app/jobs/`, `app/observability/`, `supabase/migrations/`, `apps/api/tests/conftest.py`, `scripts/seed.py`, `scripts/pregenerate.py`, `docker/`, `.github/`, `pyproject.toml`/`uv.lock`, `.specify/` | Repo, CI, Spec Kit setup (CLI, `specify init`, constitution); API stubs from P1's contracts by H3; **GPU VM + AWS backup VM**, Docker, named Cloudflare Tunnel, GHCR/Watchtower deploy, budget alerts; **TEI container serving bge-m3** (and the reranker if used) on the VM (H0–H2) and the temporary indexing GPU VM; **runs the library indexing** with P1's code (H5–H7, size check per book, HNSW after load); `topic_jobs` queue + worker + SSE; structlog + Langfuse; database layer (attempts, mastery, traces, review cards); tests on a throwaway schema per run; merging green PRs; pre-generated topics |
| **P3** (backend) | Agents & integration | `app/research/`, `app/uploads/`, `app/llm/`, `app/graders/`, `app/api/learn.py`, `app/api/tutor.py`, `app/api/topics.py`, `data/sources/`, `scripts/build_library.*`, `tests/research/`, `tests/uploads/`, `tests/llm/`, `tests/graders/`, `tests/api/` | Allowlist + textbook downloader/HTML reader; **full library download H1–H5** (P2 runs the indexing); **Deep Research agent**; uploaded-file reader (PDF/DOCX/link); **LLM gateway** (Vertex AI → Bedrock → OpenRouter, Vertex by H3 and Bedrock by H5, per-tier routing, model roles incl. the cross-family verifier rule); MCQ grading; the **API routes** that connect P1's engine and retrieval, P2's database layer and P4's content/tutor to the web |
| **P4** (careful, detail-oriented) | Content & tutor | `app/content/`, `app/guardrails/`, `app/tutor/`, `data/golden/`, `data/kg/`, `data/items/`, `data/guardrails/`, `tests/content/`, `tests/guardrails/`, `tests/tutor/` | **Golden topics first (H0–H3):** 2–3 hand-checked topics (source chunks, graph, ~15 items each) used as test data, labelled sample and demo fallback; content pipeline (sources → Knowledge Graph via **long-context extraction with chunk-ID markers** → MCQs with a misconception per wrong option); **verification gate**; `guardrails/metrics.py`; **Socratic tutor** prompts and hint ladder (Vietnamese, cited, never the final answer) |
| **P5** (frontend/design) | Web app | `apps/web/`, `assets/sena/` | Next.js app on Vercel, built on **mock JSON from H1**: topic input + file upload, research-trail screen, knowledge map (React Flow + `dagre`), learning + tutor screens, **"Vì sao?" panel** rendering `DecisionTrace`, "open source page" on citations (`source_uri` + page), Free/Pro switch, Vietnamese i18n, **backup video**; the agent reads designs through **MCP** (Figma MCP for the screens, shadcn MCP for components, a browser MCP to check the running app) |

## Stack (decided; changes go through P1)
- **Web:** Next.js (App Router, TypeScript strict), Tailwind + shadcn/ui, React Flow with **`dagre` auto-layout
  from H0** (never hand-computed x/y; every topic produces a differently shaped graph); deployed on **Vercel**.
- **Hosting decision (team, 2026-11-07): the API, worker and TEI container run on P2's personal machine (32 GB RAM,
  NVIDIA GTX 1060 with 6 GB), not on a cloud VM.** Supabase (database, storage) and the LLM APIs (Vertex AI, Bedrock,
  OpenRouter) stay in the cloud, so organizer credits still pay for models. *Replaced:* the cloud GPU VM, the backup VM
  on the second cloud, the temporary indexing GPU VM, GPU-quota requests. *Unchanged:* Docker compose (API, worker,
  TEI), the named Cloudflare Tunnel (outbound only, so a home or venue network is fine), GHCR + Watchtower or a manual
  `docker compose pull`, the Supabase size budget.
  **TEI runs its CPU image on this machine:** TEI's GPU images need CUDA compute capability 7.5 or newer (Turing, RTX 20xx
  and later) and do not support the GTX 1000 series. The API code is the same either way (`TEI_URL`). Bulk indexing runs
  on that CPU: `uv run python -m app.rag.library <library> --tei-url http://localhost:8080 --build-index`. **P2 measured one chapter** (`docker/p2-readiness.json`, 16 chunks): 1.09 chunks/s on the CPU, so the 17,390-chunk export would take about 4.4 h and 30k chunks about 7.7 h, which does not fit H5–H7; query embedding took 0.16 s (target ~1 s). So index the books the golden topics need first, or run the bulk on a GPU machine (Colab, same model, no re-index), or try the local model on the GTX 1060 (`--embedder local`, PyTorch with CUDA; unverified for this card, check
  `pick_device()`). Either path uses the same bge-m3 model, so no re-index. **Open for P2**, replacing the VM tasks: the
  OS setup (Windows: Docker Desktop with WSL2), the tunnel from it, a standby plan, and keeping it awake. "API VM spec"
  below is now that machine's minimum spec; the VM rows in Risks are marked.
- **Cloud (organizer credits, both open at H0):** **Google Cloud is primary, AWS is backup**; swap the roles if AWS
  gets a GPU first. Google credits cover Cloud Run, Vertex AI and other GCP services (amount and GPU access not yet
  confirmed), on each member's **own Google account**. **P2 owns the product project** on P2's credit; P1 and P3 join it
  with their own logins, passwords are never shared, and other members' credits stay in reserve. The VM and worker use a
  service account, never a personal login; its key goes only in `.env` or the password manager. Do not sign the product
  project in to Antigravity (it spends the same credit). Avoid a personal card on the billing account: budget alerts
  warn but do not stop spending. AWS gives each
  member's new root account up to $200 ($100 at signup + $100 from tasks); credits do not pool, so **P2's account** runs
  Bedrock and the backup VM, **P1 keeps a backup account**, **P3 gets a Bedrock-only IAM user** in P2's account at H0,
  and P3–P5 can create accounts later as reserve. Region: Singapore (`asia-southeast1` / `ap-southeast-1`),
  next to Supabase. Budget alerts on every account in use; root accounts get MFA and no access keys (use IAM users).
- **API host (P2)** *(host superseded: see Hosting decision)*: Python 3.12, FastAPI, Pydantic v2, `uv`, in Docker on a **GPU VM** on the primary cloud (spec below).
  The backup cloud keeps a **stopped VM with the same image and compose file**, started only if the primary fails.
  Exposed with a **named Cloudflare Tunnel on the team's own domain** (never `trycloudflare.com`: its URL changes on
  every restart and the web app would point at a dead address); `cloudflared` runs with `--protocol http2`. **The VM
  opens no ports to the internet**; all traffic goes through the tunnel. All containers use `restart: unless-stopped`.
  CORS: the Vercel domain and `http://localhost:3000` from H0; shared API key between web and API.
- **Deploy (P2):** Vercel deploys the web app on merge to `main`. For the API, GitHub Actions builds the image and pushes
  it to GHCR; **Watchtower** on the VM pulls new images automatically. Manual fallback on the VM:
  `docker compose pull && docker compose up -d`. P2 keeps a VM setup script (Docker, NVIDIA Container Toolkit,
  GHCR login, cloudflared, Watchtower) so the backup VM can be rebuilt in minutes.
- **Image (P2):** multi-stage build with `uv`: dependencies in a stable layer, `src/` copied last, so a normal merge pulls
  only a few MB. The API image has **no ML runtime** (no PyTorch/ONNX): bge-m3 runs in the separate **TEI container**
  (Hugging Face Text Embeddings Inference), whose weights live on the VM disk and are bind-mounted
  (`/models/bge-m3:/data`). TEI has GPU and CPU images; a CPU-only VM uses the CPU image.
- **Jobs (24 h, P2):** a `topic_jobs` table in Postgres is the queue. The worker is a **separate compose service** from
  the same image (`command: python -m app.worker`), never inside uvicorn; it claims jobs with
  `SELECT … FOR UPDATE SKIP LOCKED`. Deep Research runs 3–8 min, never inside a request. Redis + `arq` after the contest.
- **Progress (SSE, P2):** `GET /topics/{id}/events` sends a heartbeat every 15–20 s (Cloudflare drops idle connections
  after ~100 s), with `Cache-Control: no-cache`. The web app reconnects automatically and reloads state from
  `GET /topics/{id}` (backed by `topic_jobs`).
- **Data:** Supabase cloud — Postgres + pgvector (`halfvec`), Storage (uploads). Auth after the contest.
  Free tier is 500 MB: **chunk budget ~30,000 (8–10 textbooks)**, chosen to match the pre-generated topics; check
  the database size after each book and stop at ~350 MB; build the HNSW index after loading, not row by row.
  **Migration `0003` (`halfvec`) must be merged before bulk indexing**, or the whole library is indexed twice. It
  changes `chunks.embedding` to `halfvec(1024)`, drops the HNSW index (rebuilt with `halfvec_cosine_ops` once loading
  finishes) and renames `chunks.url` (from `0002`) to `source_uri`; the same PR updates `store.py` and `retrieve.py`
  (`::halfvec(1024)` casts, `source_uri`).
  Fallback if the library must be bigger: Supabase Pro for one month. Every chunk stores `source_uri` (web URL, or the
  Supabase Storage path of an uploaded file) plus `page`, so the web app can open the original page of a citation.
- **Embeddings:** BAAI/bge-m3 (1024 dims) served by a **TEI container** on the API VM (P2 deploys it in H0–H2; the
  reranker `bge-reranker-v2-m3` can run in a second TEI container if P1 decides at H8). **Only TEI holds the model**;
  the API and the worker both call it over HTTP on the VM (`TEI_URL`), with an async client so the event loop is never
  blocked. **P1 writes `embed.py` and `retrieve.py`** against TEI. Bulk indexing runs the same TEI image on a
  short-lived GPU VM (deleted right after; Colab as fallback). Fallbacks: Hugging Face hosted bge-m3, or a managed
  multilingual embedding API on Bedrock/Vertex (e.g. a 1024-dim multilingual model) selected by `EMBEDDING_BACKEND` —
  **a different model means incompatible vectors, so switching requires re-indexing the library.**
- **LLM (P3):** one gateway, `app/llm/`, with provider adapters: **Vertex AI (primary, on credits)**, **Bedrock**, and
  **OpenRouter** (last fallback). `app/llm/routing.yaml` maps (tier, task) → an ordered list of `provider:model`; the
  gateway tries them in order on errors or rate limits. **free** = cheap models (e.g. Gemini Flash on Vertex), Nhanh mode
  only, no web search; **pro** = strong models (e.g. Claude on Vertex or Bedrock) + Deep Research. Exact model IDs chosen
  after the H8 Vietnamese quality test (designed by P1). On OpenRouter avoid `:free` model variants (rate limits).
  **Model roles:**
  - *Graph extraction / Deep Research reading* (generation now by DeepSeek, see **Model decision** below): a long-context
    model reads a whole textbook or chapter set in one call; the text is sent **with chunk-ID markers** and every concept must cite them.
  - *Verifier (verification gate):* **always a different model family from the generator** (now: DeepSeek generates,
    Gemini verifies), so a model never grades its own output (self-preference bias). Enforced in
    `routing.yaml`.
  **Model decision (team, including P1, 2026-11-07), implemented in `routing.yaml`:** generation (graph extraction, items,
  tutor hints, `/ask`) = **DeepSeek API with no fallback to another family**; verification = **Gemini** (Developer API:
  `GEMINI_API_KEY` + `GEMINI_VERIFY_MODEL`; Vertex only when configured explicitly with `VERTEX_VERIFY_MODEL`); embedding =
  **BAAI/bge-m3 on TEI**. The gateway excludes the generator's actual family, so the cross-family rule holds by
  construction. P2's live smoke (`docker/llm-live-smoke.json`, one synthetic MCQ, not an acceptance): DeepSeek generated in
  about 1 s, Gemini verified blind in about 4.6 s, the answers matched, no keys were logged. What follows from it:
  1. **A DeepSeek outage or rate limit stops generation** (it fails explicitly): the fallback is the pre-generated and golden
     topics, so keep them current.
  2. **Developer API billing and credits are separate from Vertex:** both DeepSeek and Gemini cost real money, so set a
     spending limit on each.
  3. **Free and Pro are the same model today** (`DEEPSEEK_FREE_MODEL` and `DEEPSEEK_PRO_MODEL` default alike): set the Pro
     one on purpose or the tiers do not differ.
  4. **Long inputs:** graph extraction was designed around a long-context model; check DeepSeek's input limit, else extract
     chapter by chapter with the same chunk-ID markers.
  The H8 test is now a **validation** of this stack against the gates (`specs/model-test/`), not a selection. **Open for
  P1:** whether uploaded files may be sent to DeepSeek (SPEC: learner data is private by default).
- **Observability (24 h, P2):** `structlog` JSON logs (`request_id`, `topic_id`, `tier`) + Langfuse for every LLM call
  (model, latency, cost); the Langfuse dashboard is shown at the end of the demo. After the contest:
  OpenTelemetry → Grafana Cloud, Sentry.
- **Engine (P1):** BKT (mastery), `fsrs` (reviews), graph rules (placement, remediation). Pure functions, tested.
- **Tests without Docker (P2, before H0 if allowed, otherwise the first task of H0–H1):** `tests/conftest.py` creates a **throwaway schema per run** (create → migrate →
  drop) instead of a throwaway database, so every member runs the full suite against **their own free Supabase dev
  project**. No Docker and no bge-m3 on laptops (tests use the fake embedder). CI keeps its own Postgres service.
- **CI:** pytest + ruff required; mypy runs but only warns. Playwright end-to-end tests after the contest;
  during the contest P5 keeps a manual end-to-end checklist.
- **Typed web client:** P5 generates TypeScript types from FastAPI's OpenAPI with `openapi-typescript`, so a contract
  change breaks the web build instead of the demo. Until the stubs exist (H3), P5 uses mock JSON matching P1's H1 draft.

### API VM spec (P2): now the minimum spec of the personal host (see Hosting decision)
| | With GPU (recommended) | CPU only (no GPU quota yet) |
|---|---|---|
| Machine | Google Cloud `g2-standard-4` (1× L4) or `n1-standard-4` + 1× T4; AWS `g4dn.xlarge` (1× T4) | 8 vCPU, 32 GB RAM |
| RAM | 16 GB | 32 GB |
| Disk | 50 GB SSD (images + bge-m3 weights) | 50 GB SSD |
| OS | Ubuntu 22.04/24.04 + NVIDIA driver + NVIDIA Container Toolkit | Ubuntu 22.04/24.04 |
| bge-m3 | TEI GPU image | TEI CPU image |
| Region | Singapore | Singapore |

For P2's GTX 1060, TEI follows the **CPU-only** column (its GPU images need compute capability 7.5+).
Acceptance at H3: query embedding < ~1 s per Vietnamese question on the host. Bulk-indexing GPU VM is deleted after use;
the backup VM stays stopped until needed.

### Before H0 checklist
- P1, **ask the organizers now** (cloud opens only at H0; own Google accounts confirmed): **How much credit per member**
  (the guide mentions $5; about $5 means the VM moves to AWS and Google keeps Vertex only)? Can it use GPUs on Compute
  Engine, and with what quota? **When does the credit expire or access close** (the final demo must still run)? Does the
  AWS credit need a card, and does the free account plan allow GPU instances and Bedrock?
- P2: Cloudflare account + a cheap domain + a named tunnel on it; Vercel account linked to the repo; Supabase demo
  project; VM setup script written and ready to run at H0 (first real test on the VM).
- P3: test the gateway through OpenRouter if pre-contest code is allowed; only the Vertex and Bedrock adapters wait for H0.
- P1: members added as GitHub collaborators; OpenRouter key with a spending limit (fallback only); cloud
  service-account credentials shared only through a password manager; first draft of `app/schemas.py`.
- P4: pick the 2–3 golden topics (match the pre-generated list) and gather their source pages.
- P1, **contract review**: share the Contracts section; each lane checks only the contracts it produces or consumes and
  replies "OK" or lists concrete problems by a set deadline (silence is not agreement); P1 answers every objection and
  decides. This is the draft; the H3 freeze is still the final check.
- P2, **Spec Kit**: `uv tool install specify-cli`, `specify init` with the Claude Code integration (confirm the flag with
  `specify init --help`), check the command names (`/speckit-…`), write the constitution from `CLAUDE.md`, and check
  how it handles feature branches. Ask the organizers whether this setup may be committed before H0.
- P5, **MCP**: add the Figma MCP (if designing in Figma) and shadcn MCP to Claude Code in local scope
  (`claude mcp add --scope local …`) and test that the agent can read a frame. Tokens (e.g. the Figma personal access
  token) stay in local config or `.env`, never in a commit or in chat.
- P1: name **P2 as deputy lead** (decides while P1 sleeps); agree the sleep slots below with everyone.
- **Only if pre-contest code is allowed (3):** P1 drafts `app/schemas.py` (H1 becomes a review) and migration `0003`; P2
  switches `conftest.py` to a throwaway schema and merges `0003`; **if (2) is also "yes"**, P3 downloads the library
  and P2 indexes it, so H3–H7 only checks size and retrieval quality.
- Everyone: Git, Python 3.12, `uv`, their AI coding agent; own Supabase dev project (for running tests) and keys in
  `.env`. Laptops need no GPU and no Docker; 8 GB RAM is enough, 16 GB is comfortable; keep a few GB of disk free.
- P5: Node.js 20 + pnpm.

## Contracts (draft by H1, frozen at H3; only P1 changes them, announced at a checkpoint)

### Knowledge Graph (P4 writes, P1 + P5 read) — stored in the DB; YAML for fixtures and golden topics
```yaml
concepts:
  - slug: photosynthesis-light-reactions   # kebab-case, unique per subject
    name_vi: Pha sáng của quang hợp
    name_en: Light reactions
    description_vi: ...
    sources: ["https://openstax.org/books/biology-2e/pages/..."]
edges:                                      # prerequisite -> concept; loader rejects cycles
  - {from: cell-structure, to: photosynthesis-light-reactions}
```

### Items (P4 writes, P1 + P3 read) — MCQ only
```yaml
concept: photosynthesis-light-reactions
misconceptions:
  - {slug: oxygen-from-co2, description_vi: "Nghĩ rằng O2 sinh ra từ CO2"}
items:
  - id: plr-001
    kind: mcq
    prompt_vi: "Oxy sinh ra trong quang hợp có nguồn gốc từ đâu?"
    difficulty: 0.4
    source: "https://openstax.org/..."
    chunk_ids: ["7f3c…", "a91e…"]   # the generator's citations; the verifier sees only these chunks
    status: verified                  # verified | needs_review (needs_review items are never served)
    options:
      - {label: "Từ nước (H2O)", correct: true}
      - {label: "Từ CO2", correct: false, misconception: oxygen-from-co2}
```
Every wrong option has a `misconception`; every item has a `source` and `chunk_ids`. **Verification gate** (`SPEC.md`):
the verifier answers the item blind from its cited chunks only; a mismatch or no answer sets `needs_review`, and only
`verified` items are served.

### Golden topics (P4, `data/golden/<slug>/`)
Each holds the source chunks, a hand-checked `graph.yaml`, ~15 hand-checked items and their expected answers. Uses:
real test data for P1, P3 and P5 from H3; the labelled sample for `guardrails/metrics.py`; safe fallback demo topics.

### API (FastAPI, JSON; Pydantic models in `app/schemas.py`). P2 ships all routes as **stubs with fixture data** by H3.
Route owner = who writes the endpoint; logic comes from the lanes in brackets.
| Method & path | Route owner | Request → Response |
|---|---|---|
| `POST /learners` | P2 | `{display_name}` → `{learner_id}` |
| `POST /topics` | P3 (pipeline P3 + P4, retrieval P1) | `{goal_vi?, upload_id?, mode: "quick"\|"deep", tier: "free"\|"pro"}` → `{topic_id, cached}` |
| `GET /topics/{id}` | P2 | → `{status: queued\|researching\|indexing\|graph\|items\|ready\|failed, step_vi, progress, subject_slug?, graph_ready, items_ready, sources: [{title, publisher, url, license}], trail: [{at, kind: search\|read\|select, text_vi, url?}]}` (current state from `topic_jobs`; used to recover after a dropped stream) |
| `GET /topics/{id}/events` | P2 | SSE stream of the same fields as they change, plus a `heartbeat` event every 15–20 s |
| `GET /topics/cached` | P2 | → `{topics: [{subject_slug, name_vi}]}` |
| `POST /uploads` | P3 | multipart PDF/DOCX or `{url}` → `{upload_id, pages, text_ok}` |
| `GET /graph?learner_id=&subject=` | P3 (engine P1) | → `{nodes: [{slug, name_vi, p_known, mastered}], edges: [{from, to}]}` |
| `GET /graph/review?subject=` | P3 (service P2, contract P1) | learner from the session cookie `nodetrail_learner` (401 without one) → `{learner_id, subject, graph_revision, graph: {concepts, edges}, confirmed}`; `graph_revision` is a 64-hex sha256 of the generated map; `confirmed` is true only for this exact revision. 503 if the graph is not ready. |
| `POST /graph/confirm` | P3 (service P2, contract P1) | `{subject, graph_revision}` (no learner id: identity is the cookie) → `{learner_id, subject, graph_revision, confirmed: true}`; 409 if the revision is stale, 404 unknown learner or topic, 422 invalid, 401 no session. Until confirmed, practice, attempts and hints return 409. Specs: `specs/graph-confirmation-contract/` (contract) and `specs/graph-confirmation/` (P3's routes, on `ptest2`). |
| `GET /topics/{topic_id}/metrics` | P2 (contract P1) | → `{topic_id, elapsed_seconds \| null, cost_usd \| null, items_generated, items_verified, items_dropped}`; the demo dashboard. `null` means unknown, never estimated. The web proxy needs `topics/{id}/metrics` in its allowlist. Spec: `specs/topic-metrics/`. |
| `POST /placement/next` | P3 (engine P1) | `{learner_id, subject}` → `{item \| null, done, gap_slug?, trace: DecisionTrace}` |
| `GET /next-item?learner_id=&subject=` | P3 (engine P1) | → `{item, reason_vi}` |
| `POST /attempts` | P3 (grading P3, engine P1) | `{learner_id, item_id, answer, hints_used}` → `{correct, misconception_vi?, p_known, mastered, remediation?: {concept_slug, reason_vi}, traces: [DecisionTrace]}` |
| `POST /tutor/hint` | P3 (tutor P4) | `{learner_id, item_id, level, last_answer?, tier}` → `{hint_vi, citations: [{title, section, url}]}` |
| `POST /ask` | P3 (retrieval P1) | `{question, subject, tier}` → `{answer_vi, citations}` |
| `GET /reviews/due?learner_id=` | P3 (engine P1) | → `{cards: [{concept_slug, due_at}]}` |
| `POST /exam-plan` | P3 (engine P1) | `{learner_id, subject, exam_date}` → `{days: [{date, concept_slugs, minutes}]}` |

`item` sent to the web never contains the answer: `{id, kind, prompt_vi, options: [{label}]}`.

### Python interfaces
- `app/rag/embed.py::Embedder.embed(texts) -> list[list[float]]` (P1; exists; add TEI, managed-API and HF-hosted
  implementations; the managed API needs a re-index).
- `app/rag/retrieve.py::search(query, subject, k=5) -> list[Citation]` (P1).
- `app/rag/rerank.py` (P1, optional): rerank retrieved chunks (e.g. `bge-reranker-v2-m3`); only if H8 retrieval is weak.
- `app/llm/gateway.py::complete(task, tier, system, messages, schema=None) -> str | BaseModel` (P3) — reads
  `routing.yaml`, validates JSON with Pydantic, retries, falls back to the next model. Nothing else imports an LLM SDK.
- `app/research/agent.py::research(goal, on_event) -> list[ChosenSource]` (P3) — allowlisted domains only,
  ≤ 15 searches, ≤ 12 page reads, 8-minute cap.
- `app/engine/bkt.py`, `app/engine/srs.py` (P1; exist): pure, no DB.
- `app/engine/graph.py` (P1): prerequisite DAG helpers + `root_cause(graph, mastery, failed_slug) -> (concept_slug, trace)`
  (walk prerequisites to the weakest one). Pure, no DB.
- `app/engine/placement.py` (P1): `next_question(graph, answers) -> (slug | None, trace)` and `gap(graph, answers) -> slug`,
  the graph-walk placement below. Pure, no DB.
- `app/services/` (P2): load/save attempts, mastery, traces and review cards; the engine never touches the DB.
- `app/guardrails/answerability.py` (P4): `check(text, cited_chunks) -> Verdict{supported, reason}`, used on every
  generated item before it is stored and on every tutor hint before it is shown.
- `app/guardrails/metrics.py` (P4, evaluation design P1): runs the checks over the labelled set in `data/guardrails/`
  (built from the golden topics) and reports error rate, catch rate and false alarms; the numbers go on the dashboard.
- `app/tutor/hints.py::hint(item, level, last_answer, chunks, tier) -> Hint` (P4): Socratic hint ladder via the gateway,
  checked by `answerability` before it is returned.

### Placement (graph walk, P1)
Start at an advanced concept. Correct → mark its prerequisites as known (raise `p_known`) and move to the next
unknown branch. Wrong → ask about one of its prerequisites. Stop after ~6 questions or when the gap is located;
return `gap_slug`. BKT keeps updating mastery after every later attempt.

### DecisionTrace (P1 defines in `app/engine/trace.py`; P5 renders)
`{kind, concept_slug, at, prior, evidence: {item_id?, correct?, misconception?, slip?, guess?}, posterior, rule, rule_vi,
alternatives: [{concept_slug, p_known, why_not_vi}]}` — pure data from the engine, stored per learner (migration `0004`,
via P2's services), returned by `/placement/next` and `/attempts`, shown in the web app's "Vì sao?" panel. `bkt.update`
and `srs.review` stay unchanged; traced wrappers (`update_traced`, `review_traced`) and `graph.root_cause` /
`placement.next_question` return `(result, trace)`.

## Two modes
| | Nhanh (NotebookLM-style) | Nghiên cứu sâu (Deep Research) |
|---|---|---|
| Sources | Curated library + learner's upload | Agent searches and reads the allowlist live |
| Time | < 60 s to the graph + first ~6 placement questions; remaining items generated in the background (measured at H8) | target 3–5 min, cap 8 min |
| Tier | Free (cheap models) | Pro (strong models) |

Allowlist (`data/sources/allowlist.yaml`, P3 writes, P1 approves): OpenStax, LibreTexts, MIT OpenCourseWare, Saylor
Academy, Open Textbook Library, Wikibooks; Wikipedia last resort, labelled. No "ND" licences; licence recorded per source.
Deep Research quality bar: ≥ 3 sources from ≥ 2 publishers; prerequisites from the sources' chapter order and
objectives; everything cited; answerability-checked items.

## Timeline (H0 = kickoff)
| Window | P1 Lead + ML core | P2 Platform | P3 Agents & integration | P4 Content & tutor | P5 Web |
|---|---|---|---|---|---|
| **H0–H1** | **Draft contracts** (`schemas.py`, YAML formats, `DecisionTrace`); migration `0003` (`halfvec`, `url` → `source_uri`); one-page engine spec in `specs/engine/` | **Throwaway-schema `conftest.py` first** (everyone runs tests from H1); repo, CI, FastAPI skeleton, schema on Supabase, **review and merge P1's migration `0003`**, Spec Kit setup (if not done before H0); **minute 0: check GPU quota on both clouds, request it if missing, enable Vertex AI and Bedrock, set budget alerts; decide GPU or CPU VM by H1**; start the VM | Allowlist + downloader/HTML reader; gateway skeleton (own folders) | **Golden topic #1** (chunks, graph, ~15 items) | Next.js skeleton, Sena assets |
| **H1–H3** | BKT/FSRS traced wrappers, `graph.py`; retrieval on golden topic #1 | API stubs from the contracts; **TEI container serving bge-m3** (H2); tunnel, Watchtower, backup VM image | **Library download starts** (priority order, H1–H5); first Vertex AI call through the gateway; file reader | **Golden topics #2–3**; graph-generation prompt on a sample chapter | Map + "Vì sao?" panel on **mock JSON** |
| **H3** checkpoint | Contracts frozen; golden topics 1–2 ready; engine and UI tested on real data; bge-m3 measured on the VM; migration `0003` merged; first books downloaded | | | | |
| **H3–H7** | `placement.py`, `DecisionTrace` everywhere; retrieval evaluation on golden topic #1 only | **Library indexing** on the indexing GPU VM with P1's code (H5–H7), size check, HNSW after load; `topic_jobs` queue + worker + SSE with heartbeat; database layer; structlog + Langfuse | **Bedrock call through the gateway (by H5)**; library download done (H5); grading; real routes for topics, graph, placement, attempts, uploads; Nhanh mode wiring | Pipeline graph → items; verification gate (Bedrock verifier; OpenRouter fallback of another family) | Topic input + upload, map, learning screen; switch to real routes as they land |
| **H7** integration | P1, P3, P4, P5 pieces due at H8 are merged (P1: `placement.py`, `retrieve.py`). **H7–H8: first end-to-end run of Nhanh** (P1 leads, everyone fixes) | | | | |
| **H8** checkpoint | Nhanh end to end on **3 unfamiliar topics** (if the library is not indexed yet, use 3 uploaded files instead). Library indexed, DB < 350 MB; migrations `0003`–`0007` merged; Bedrock reachable; Nhanh time measured. Not solid → whole team on Nhanh + pre-generated topics; Deep Research becomes a bonus. Pick Free/Pro models from the Vietnamese test. P1 decides on the reranker. | | | | |
| **H8–H11** | Root-cause remediation rules; reranker if needed; engine tests on varied graph shapes; retrieval evaluation on the other golden topics | Integration, dashboard, deploy hardening | Deep Research agent; routes for tutor, ask, reviews, exam-plan, next-item | Tutor prompts + hint ladder; quality across subject types | Research-trail + tutor screens, Free/Pro switch |
| **H11–H12** | Everyone plays judge with an unfamiliar topic; measure time + cost per mode (nobody sleeps) | | | | |
| **H12** | P1 decides: Deep Research live on stage, or shown as a recording | | | | |
| **H12–H18** | Metrics review with P4; tutor evaluation ≥ 18/20 with P4; algorithm part of the pitch. Sleep H12:00–H13:30 | Pre-generate topics, monitoring; deputy lead while P1 sleeps. Sleep H16:00–H17:30 | Fixes. Sleep H13:30–H15:00 | Label 50 items + 20 hints in **H15–H16** (whole team, nobody sleeps), run `guardrails/metrics.py`. Sleep H13:30–H15:00 | Polish, manual E2E checklist. Sleep H12:00–H13:30 |
| **H20** freeze (moved from H18) | Tag `demo-v1` (P2) | | | | |
| **H18–H23** | Demo script + pitch; 3 clean runs with unseen topics, timed to the research | | | | **Backup video** |
| **H23–H24** | Buffer | | | | |

**Real routes at H8** (no stubs): `POST /topics`, `GET /topics/{id}` + `/events`, `POST /uploads`, `GET /graph`,
`POST /placement/next`, `POST /attempts`. **Stubs allowed until H11:** `/tutor/hint`, `/ask`, `/next-item`,
`/reviews/due`, `/exam-plan`.

**Sleep:** about 90 min each inside H12–H18, in three back-to-back blocks so no more than two people are ever asleep:
P1 + P5 H12:00–H13:30 (right after the H12 decision), P3 + P4 H13:30–H15:00, P2 H16:00–H17:30. Never two who are
waiting on each other; nobody sleeps during H11–H12, the labelling hour (H15–H16) or H17:30–H18. While P1 sleeps,
**P2 decides**; while P3 sleeps, P2 handles route bugs; while P4 sleeps, P1 covers content questions; while P2 sleeps,
P3 watches the VM and merges green PRs.

## Git workflow
- Branch per lane: `p1/ml-core`, `p2/platform`, `p3/integration`, `p4/content`, `p5/web`; one worktree per extra agent.
- **Rebase at every checkpoint**: `git fetch --tags && git rebase checkpoint-h3` (or the latest `checkpoint-h*` tag),
  then run tests.
- **Checkpoint tags (the shared baseline).** When everything due at H3, H8 and H12 is merged and CI on `main` is green,
  P1 (P2 while P1 sleeps) tags that commit `checkpoint-h3`, `checkpoint-h8`, `checkpoint-h12`, with the list of what is
  in it as the tag message (`git tag -a checkpoint-h3 -m "..." && git push origin checkpoint-h3`). Tagging before
  everything due is merged gives a baseline nobody is really on, so wait. `demo-v1` at H18 stays P2's. **A tag never
  moves**: a mistake gets a new tag. `checkpoint-h3` is the contract freeze: `git diff checkpoint-h3 --
  apps/api/app/schemas.py` shows any later contract change. Pushing a tag is not pushing to `main`.
- **Ready tags (the unblock signal).** When you finish something another lane waits on, merge it (CI green), then tag
  `main` `ready/<what>` and push the tag (`git tag -a ready/<what> -m "..." && git push origin ready/<what>`), and tick your
  board row. A waiting agent runs `git fetch --tags` and `git tag -l "ready/*"`; when its tag exists it deletes its `⏳`
  line, rebases onto it and continues. Whoever merged the work (or its owner) tags it; a wrong tag is replaced by
  `ready/<what>-2`, never moved.
  **If a tag push is refused** (an agent sandbox or proxy can answer HTTP 403; a refusal is policy, so do not retry or
  work around it), the signal is the board instead: once your tick of the row is merged to `main`, a waiting agent treats
  it as equal to the tag, so it continues when **either** the tag exists **or** the owner's matching item is `[x]` on
  `main`. Tell the contact, who creates the tag from a terminal or on GitHub (Releases → new tag). The same goes for
  `checkpoint-h*`. Expected tags (add rows as needs appear):

| Tag | Tagged by | Waiting on it | When |
|---|---|---|---|
| `ready/p1-core` (PR #1: contracts, engine, retrieval, migrations `0003`–`0004` on `main`) | whoever merges it | P3, P5, P2 (indexing) | H3 |
| `ready/tei-host` (TEI serves bge-m3, reachable from the API machine) | P2 | P1 (speed check, retrieval eval), P3 | H2–H3 |
| `ready/api-stubs` (every route serves fixture data) | P2 | P5, P3 | H3 |
| `ready/golden-topic-1`, `ready/golden-topics-2-3` | P4 | P1 (retrieval eval), P3, P5 | H3 |
| `ready/gateway-vertex`, `ready/gateway-bedrock` | P3 | P4, P1 (model test) | H3, H5 |
| `ready/model-test-cases` (held-out chunks + planted-wrong items) | P4 | P3, P1 | H6 |
| `ready/library-readers` (HTML/PDF/DOCX readers + `build_library` emit book folders) | P3 | P1, P2 (indexing) | H5 |
| `ready/library-indexed` (library in the database, index built, size checked) | P2 | P1, P3, P4 (Nhanh, retrieval eval) | H7 |

- PR title `[P3] ...`; CI green; P2 merges routine PRs, P1 approves contract changes. Stacked PRs: **retarget to `main`
  before deleting the base branch**.
- Migrations reserved, numbered in merge order: `0003` P1 (`halfvec`, `chunks.url` → `source_uri`, HNSW rebuilt),
  `0004` P1 (`decision_traces`), `0005` P4 (`items.chunk_ids`, `items.status`), `0006` P2 (`topic_jobs`, `llm_calls`),
  `0007` P3 (uploads). `supabase/migrations/` belongs to P2, but **each reserved file is written by its lane and reviewed
  and merged by P2** (the one exception to lane-owned paths). Additive only, except `0003` (type change, rename, index
  rebuild). P2 merges them in number order, so every database (demo, CI, dev) applies them in the same order.
- Dependencies via `uv add` / `pnpm add` in your own PR; on lockfile conflicts take `main`'s and re-lock.
- **Secrets:** each person has their own Supabase dev project and keys in `.env`. Demo keys only via a password manager.

## Working with your AI agent
`CLAUDE.md` does not auto-load this file. Each person has a short start guide in `team/` (`P1.md`–`P5.md`): setup, first
task, first prompt. Before H0, copy `CLAUDE.local.md.example` to `CLAUDE.local.md` (git-ignored) and set your number, so
every session knows its lane. Other coding agents may not load these files: tell them to read `CLAUDE.md` and your guide.
Check it works by asking the agent "Which lane are you, which paths do you own, and what is your first task at H0?"
First prompt (copy and fill in):
> You are working on lane **P_ (name)** in `TEAM.md`. Only edit the paths that lane owns.
> Task: **(your row in the timeline for the current window)**. First run `/speckit-specify`, `/speckit-plan` and
> `/speckit-tasks` for it (one page each). Follow the contracts in `TEAM.md` exactly; if one seems wrong, stop and tell me.
> Use fixtures or golden topics for anything another lane owns. When done: run tests, update `MAP.md`, write a PR
> description.

Agent rules: never push to `main`, never edit another lane's files, never change a contract, never read `.env`.

## Definition of done (every PR)
pytest + ruff green; new logic has tests; no real LLM/network calls in tests; user-facing text in Vietnamese;
explanations cited; contract shapes exact; `MAP.md` updated.

## Risks and fallbacks
| Risk | Fallback | Owner |
|---|---|---|
| Contracts late past H1 / foundation late past H3 | Lanes keep working on golden topics, mock JSON and their own folders; P1 does nothing but contracts in H0–H1 | P1, P2 |
| Tunnel URL changes or SSE stream drops mid-research | Named tunnel on own domain; heartbeat every 15–20 s; web reconnects and reloads `GET /topics/{id}` | P2, P5 |
| *(VM part superseded: see Hosting decision)* Primary VM down | Start the backup VM on the other cloud (same image + compose + tunnel token); `/health` check; Render/Railway last resort | P2 |
| *(VM part superseded: see Hosting decision)* No GPU quota by H1 (cloud opens only at H0) | CPU VM (8 vCPU / 32 GB) with the TEI CPU image; swap primary cloud if the other approves first; bulk indexing on Colab writing to Supabase (same bge-m3 model, no re-index) | P2, P1 |
| *(VM part superseded: see Hosting decision)* Google Cloud unavailable (VM by H1, Vertex by H3; decide each separately) | **VM:** AWS `g4dn.xlarge` → AWS CPU VM; same Docker setup, keep bge-m3 (no re-index). **Models:** reorder `routing.yaml`: cheap model on Bedrock, Gemini through OpenRouter for graph extraction (or Claude on Bedrock with smaller inputs). **Verifier stays another family than the generator.** Raise the OpenRouter spending limit on purpose (real money, not credits). AWS also blocked: personal Google account if allowed (Vertex + CPU VM), last resort a laptop with Docker and the tunnel + OpenRouter | P2 (VM), P3 (models), P1 decides |
| Cloud access closes before the final demo | Confirm the closing time with the organizers; if it closes first, keep a recording and move the API to a surviving account before H23 | P1, P2 |
| *(VM part superseded: see Hosting decision)* Cloud credits burn (GPU VM left running) | Budget alerts on both clouds; delete the indexing VM right after use; backup VM stays stopped | P2 |
| Vertex model access missing or rate-limited | Gateway falls through to Bedrock, then OpenRouter (`routing.yaml` order) | P3 |
| bge-m3 too slow, or TEI / GPU driver fails | TEI CPU image → HF hosted bge-m3 → managed multilingual embedding API on Bedrock/Vertex (**requires re-indexing**) | P1, P2 |
| Long-context graph extraction too slow or costly | Fall back to chapter-by-chapter extraction with the same chunk-ID markers | P4, P3 |
| Docker image too heavy (10–20 min per update) | API image has no ML runtime; bge-m3 weights mounted into the TEI container; multi-stage `uv` build | P2 |
| Network blocks QUIC/UDP, tunnel won't connect | `cloudflared --protocol http2`; `restart: unless-stopped` | P2 |
| VM runs out of RAM or GPU memory | Only TEI holds the model (API and worker call it over HTTP); measure memory at H3 | P2, P1 |
| Database exceeds Supabase free tier | `halfvec`, ~30k-chunk budget, size check per book, HNSW after load; Supabase Pro for a month | P1 |
| Knowledge-map nodes overlap | `dagre`/`elkjs` auto-layout from H0; test shallow/deep and small/large graphs | P5 |
| Deep Research slow, wrong or off-allowlist | 8-min cap → Nhanh → pre-generated topic; domain filter in code | P3, P4, P2 |
| Judge picks a topic with no open textbook | Wikibooks/Wikipedia labelled as encyclopedia; state the limit openly | P3 |
| Generated question wrong in front of judges | Verification gate on every item and hint (verifier from a different model family), measured error rate from `metrics.py`, "Bản nháp tự động" label, rehearse many subject types | P4 |
| Cheap model returns bad JSON or weak Vietnamese | Pydantic validation + retry, fallback model list, H8 Vietnamese test | P3, P1 |
| Engine/UI only works for one graph shape | Test shallow/deep, small/large graphs (golden topics differ on purpose); vary topics at every checkpoint | P1, P5 |
| Uploaded file is scanned, table-heavy or has broken fonts | Check text on upload, ask for another file or link, page cap, rehearse with 5–10 real files | P3 |
| Deep Research not ready, team has no data to test with | Golden topics from H3 cover the engine, retrieval and UI without Deep Research | P4 |
| LLM cost too high | Measure at H11; lower effort, fewer sources (P1 decides); budget alerts on both clouds, spending limit on OpenRouter | P1, P2 |
| Web not ready at H18 | Scripted happy path only; backup video | P5 |
| Library not downloaded or indexed by H8 | Download from H1, index H5–H7 (pre-H0 if allowed); H8 test runs on uploaded files instead | P3, P2 |
| P1 overloaded (contracts, engine, retrieval, decisions) | P2 runs indexing; retrieval evaluation on one golden topic before H8; P2 tracks the critical path at checkpoints | P1, P2 |
| Bedrock unreachable (no cross-family verifier) | Verifier falls back to an OpenRouter model of another family than the generator; stated in `routing.yaml` | P3, P4 |
| Team exhausted after H14 (mistakes during labelling and freeze) | Staggered 90-min sleep slots in H12–H18; deputy lead (P2) | P1 |
| Host machine sleeps, updates itself, loses power, overheats or leaves the network | Dedicated demo machine: sleep and automatic updates off, plugged in, wired network if possible; `restart: unless-stopped`; an outside `/health` check; run the whole demo on it at H18–H23 | P2 |
| Host machine dies or is unavailable on demo day | A second teammate's machine kept ready with the same compose file and tunnel token (the TEI CPU image works without a GPU); pre-generated topics and the backup video | P2, P1 |
| *(only if bge-m3 runs on the GPU through PyTorch)* The GPU is shared with its owner's other work (VRAM taken, driver update) | Only the demo stack uses the GPU from H12; measure VRAM at H3; the owner closes other GPU apps for rehearsals and the demo | P2 |
| Network blocks inbound connections (home router, CGNAT, venue) | Not a problem for a named tunnel (outbound only); `--protocol http2`; test from a phone on mobile data | P2 |
| Venue wifi fails | Pre-generated topics + golden topics + backup video | P2, P1 |

## Demo acceptance (run at every checkpoint after H8)
1. A teammate plays judge with an unseen topic, or uploads a file → research trail shows allowlisted sources. *(P3, P5)*
2. Path ready (Nhanh: graph + first placement questions < 60 s; Deep Research < 8 min) with a cited knowledge map. *(P3, P4, P5)*
3. Graph-walk placement in ~6 questions locates a gap; the map lights up; "Vì sao?" explains the choice. *(P1, P5)*
4. Wrong answer → remediation to the weak prerequisite; hint asked → Socratic hint in Vietnamese with citations, no final answer. *(P1, P4)*
5. Correct answer → mastery rises, Sena praises understanding, a review is scheduled. *(P1, P5)*
6. Dashboard shows time, cost and dropped questions for that topic, plus the measured guardrail error rate. *(P2, P4)*
