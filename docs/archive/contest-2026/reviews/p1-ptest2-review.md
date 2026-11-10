# P1 review of `ptest2` (and a look at `p4`) — 2026-11-07

Reviewed read-only against `main` `3b3dba0`: `ptest2` `46045c5` (P2's integration of P2 + P3 + P5 + P1's `92d5592`)
and, for the overlap only, `p4` `bc7da3e` (P4's own integration). This is a source review plus the checks below. It
is **not** a runtime acceptance: nothing here ran against real TEI, real models or Supabase.
**`main` moved to `71b7b07` while this was written; see "Update after `main` moved" below.**

## Result

`ptest2` is mechanically healthy and its engine wiring is faithful, but it is not demo-ready, and the biggest problem is
that **two integrations exist that conflict** (finding 1). Findings are ranked; each names an owner and a check.

| Check | Result |
|---|---|
| `ptest2` merged into `main` | clean |
| ruff, ruff format, mypy (120 files) | pass |
| Python tests | 1,215 pass, 0 skipped (the P3-grader flow test now runs) |
| Web: frozen install, lint, typecheck | pass |
| Web: vitest | 38 pass (includes `canonical-contracts.test.ts`) |
| Secrets, risky file names | none found |
| `.claude/settings.json`, hooks, auto-run commands | not changed; none added |
| Lane boundaries | P3 and P5 inside their paths; P2 added `planv2.md` and `tests/test_platform.py` (minor) |

## Findings

| # | Sev | Owner | Finding | Evidence | Fix and check |
|---|---|---|---|---|---|
| 1 | High | P1 decides; P2, P4 merge | Two integrations, neither contains the other: `ptest2` lacks P4's content, verification, tutor and migration `0005`; `p4` lacks P2's latest wiring and the integrated web app. Merging them conflicts in 9 files (`learn.py`, `jobs/queue.py`, `jobs/worker.py`, `apps/web/lib/{api.generated,contracts,decode}.ts`, `apps/web/components/trace-panel.tsx`, `MAP.md`, `tests/api/test_learning.py`); 132 files are changed by both. | `git merge origin/p4` on `ptest2`; `git merge-base --is-ancestor` of each side's unique commits | **Confirmed by P1 (2026-11-07):** `ptest2` is the trunk (P2 is the integrator). P2 merges `p4` into it, each owner resolving their own files, then one PR to `main`. **After `71b7b07` each also conflicts with `main` (see Update).** Merge `main` into the trunk first. Check: one branch passes lint, mypy, pytest and the web checks. |
| 2 | High | P2 (`services/backend.py`) | `/next-item` never excludes items the learner already answered, so the same question repeats and mastery rises on memory. A concept with no verified items returns `None` forever and blocks the path. | `backend.py:224-227` (`min(items, key=...)`, no exclusion). Reproduced: two verified items, every answer wrong → served `A, A, A, A`, then `A`. P2's own test answers one item nine times. | Exclude answered item ids when choosing (fall back to the least recently served once all are seen); if a concept has no usable item, take the next candidate instead of `None`. Add the regression test below. |
| 3 | High | P5 | After placement the web app cannot ask for the next question: no `nextItem` in the client, and `next-item` is not in the proxy allowlist (`topics/{id}/events` is not either; polling `GET /topics/{id}` is fine). | `app/api/backend/[...path]/route.ts:5`; `lib/data-client.ts` has `placement, attempt, hint, reviews, graph, topic, upload, learner` only | Add `nextItem` to the client and `next-item` to the allowlist; wire the practice screen to it. |
| 4 | Med | P2 | API authentication is off by default: `api_key = ""` skips the check, and nothing refuses to start. | `config.py` `api_key: str = ""`; `main.py:73-79` | Refuse to start without a key unless an explicit local-dev flag is set (or warn loudly when the host is not loopback). |
| 5 | Med | P2 | `POST /attempts` is not safe to retry or double-click: a duplicate counts twice in BKT and in the review schedule. | no idempotency key; H7 review step 6 | Accept a client attempt id and dedupe on `(learner, item, attempt id)`; one transaction already makes the write atomic. |
| 6 | Med | P2 | Phase is inferred from the order of the last trace rows, and a wrong answer during placement also runs `remediate` and opens a resume origin. | `backend.py:262-273`, `:207-218` | `phase = placement` only until a `placement.done.*` trace exists; no remediation during placement; `resume_origin` only from practice-phase wrong answers. |
| 7 | Med | P2 + P4 | Items are found by `payload->>'id'`; two subjects reusing an id returns 503 on every attempt. | `backend.py:137-145`; no unique index | Unique expression index now, or P4's `0005` external id (`review.md` #2, #21). |
| 8 | Med | P2 | CI has no web job, so P5's lint, typecheck and tests never run there. | `.github/workflows/ci.yml` | Add `pnpm install --frozen-lockfile`, `lint`, `typecheck`, `test` for `apps/web`. |
| 9 | Resolved | P3 | The model family was `Literal["gemini", "claude"]`. On `main` `71b7b07` it now includes `deepseek`, and the verifier still excludes the actual generator's family. | `llm/gateway.py:28`, `:94` on `main` | None. Live acceptance of the DeepSeek route is still pending (no credentials configured). |
| 10 | Low | P3 | `SafeReader` treats `64:ff9b::7f00:1` (NAT64) and `::127.0.0.1` as global. Not exploitable without attacker DNS and a NAT64 network. | `ipaddress.is_global` check on this Python | Also reject `64:ff9b::/96` and `::/96`. |
| 11 | Low | P2 | SSE polls the database once a second per client against a pool of 5. | `main.py:146-175`, `db.py` | Fine for one demo; revisit before more than a few viewers. |
| 12 | Low | P2 | `/learners` uses its own model (`max_length=200`; the contract says 80); `GET /topics/{id}` returns a raw `JSONResponse`, so the contract model is not enforced there. | `main.py:30,141-144` | Use the contract models. |
| 13 | Info | P2, P4 | `/exam-plan` returns 503 (not handed over) and `/tutor/*` returns 503 until P4's runtime is merged. | `backend.py:369`, `main.py:63` | Expected; part of finding 1. |

Withdrawn: my earlier concern that progress is stored 0–100 against the contract's 0–1 is handled (`jobs/queue.py:52`
divides by 100).

## Update after `main` moved (`71b7b07`, same day)

`71b7b07` ("Add DeepSeek generation gateway and verified local TEI setup"; authored by P2, pushed by the GitHub user
`fromdevtocwithlove1`) went **directly to `main`**: there is no PR, and CI passed on it (run 52). It brings P3's gateway (with a DeepSeek provider), settings, TEI notes and
`docker/p2-readiness.json` onto `main`. I did not review that code (the provider and the gateway changes); I only checked
the commit for credentials (none; I may not read `.env.example`, so that file is not covered).

- **Routing note on `main`.** `TEAM.md` there carries "Approved routing update (P1/P3/P2)": DeepSeek is now an optional first
  generation candidate in both tiers, with Vertex, Bedrock and OpenRouter as fallbacks (as of `71b7b07`; `f4cd74f` then
  removed the generation fallbacks and made Gemini the verifier), and verifiers still gemini or claude. It says it does not replace the H8 quality gates. **Confirmed by P1 (2026-11-07):** generation DeepSeek, verification
  Gemini, embedding bge-m3; see the Model decision in `TEAM.md`.
- **Finding 1 is bigger.** `ptest2` now conflicts with `main` in 12 files and `p4` in 10, mostly the gateway files each
  carries its own copy of (`llm/*`), plus `config.py`, `pyproject.toml` and `.env.example`. Whoever merges first, the next
  one resolves against `main`, so `main` should be merged into the trunk before anything else.
- **Live evidence from P2** (`docker/p2-readiness.json`, P2's own measurement, not re-run by me): migrations `0003` and
  `0004` applied to a local database; Think Python chapter 1 ingested with the TEI CPU image (16 chunks, 14.7 s, **1.09
  chunks/s**, TEI memory about 4 GiB, sampled); a Vietnamese query returned the right section first in **0.16 s** (target
  about 1 s); the identical text ranked first. This is the first live check of retrieval and ingestion.
- **What that means for indexing.** At 1.09 chunks/s, P3's 17,390-chunk export would take about **4.4 hours** and 30,000
  chunks about 7.7 hours. The sample is small (16 chunks, includes warm-up), so treat it as an order of magnitude, but it does
  not fit the H5–H7 window. Options: index only the books the golden topics need first (4,000 chunks is about 1 hour), and/or
  run the bulk on a GPU machine (Colab, per the risk table; same model, so no re-index). P1 decides the subset; P2 proposes.

## Gateway review (`app/llm/`, `71b7b07` and `f4cd74f`) — P1, 2026-11-07

Source review of `gateway.py`, `providers.py` and `routing.yaml`, plus the receipt `docker/llm-live-smoke.json`.
`pytest tests/llm tests/test_config.py`: 39 pass. Not reviewed: `smoke.py`, `config.py`, the tests' content. Not run:
anything against a live model (the receipt is P2's own run: one synthetic Vietnamese MCQ, DeepSeek then Gemini,
blind answer matched, generator answer excluded from the verifier input; it is a route check, **not** acceptance).

**Sound (keep):**
- Keys travel only in headers (`x-goog-api-key`, `Authorization`), never in URLs; provider errors are reduced to codes
  (`from None`), and failure strings hold only `provider:ExceptionType`. `trust_env=False` ignores proxy variables.
- A route whose model is unset (`$` left), ends in `:free`, or does not contain its declared family name is skipped, so a
  mislabelled family cannot defeat the verifier rule. `verify` without `verification_scope(...)` is refused.
- DeepSeek failure ends in `GatewayError` with no silent switch to another family; non-retryable errors (missing key,
  4xx) stop at once, retryable ones (408, 429, 5xx, incomplete) back off 0.2 s, 0.4 s.
- Per-attempt telemetry (`Attempt`) includes paid responses that failed validation.

**Findings:**

| # | Sev | Owner | Finding | Fix and check |
|---|---|---|---|---|
| G1 | Med | P3 | Every adapter caps output at 4096 tokens. A graph extraction larger than that ends with `finish_reason=length`, which is treated as retryable, so the **same paid call is repeated and fails the same way**. | Per-task `max_tokens` (graph larger); treat `length` as non-retryable or retry with a higher cap. Check: a test where the stub returns `length` twice makes one extra call at most. |
| G2 | Med | P3 | Gemini counts thinking tokens against `maxOutputTokens`; a verifier that thinks long can be cut off (`MAX_TOKENS`) and be retried into the same result. | Set a thinking budget (or larger cap) on `verify` and log `thoughtsTokenCount`. |
| G3 | Med | P3 | `Completion.latency_ms` runs from the start of the whole request, so it includes failed attempts and back-off; p95 per model would be inflated by retries. | The H8 test should read `Attempt.latency_ms` of the successful attempt (and report retries separately). |
| G4 | Med | P1 + P2 | Free and Pro use the same model by default (`DEEPSEEK_PRO_MODEL=deepseek-flash`), so the tier switch changes nothing in the demo. Already on the board. | Set a distinct Pro model, or say openly that tiers differ only in web search and sources. |
| G5 | Med | P1 decides | **Uploads and privacy.** Uploaded text would go to DeepSeek's API and Gemini's Developer API. SPEC says learner data is private by default; the Developer API's terms differ between free and paid keys, which I have not checked. | Decision pending (uploads policy); until then uploads must not reach either API. |
| G6 | Low | P3 | A new `httpx.AsyncClient` per call (no connection reuse), a fixed 30 s transport timeout under the 35 s request timeout, no concurrency limit. | Fine for one demo; share one client and add a semaphore before more than a few jobs run at once. |
| G7 | Low | P2 | The 100 s total deadline is short for Deep Research graph tasks. | `gateway_scope` already allows a per-job gateway; set it for research jobs. |
| G8 | Info | P2 | **Credentials were pasted into a chat** (both the DeepSeek and the Gemini key). No commit contains them (checked by prefix on the last 50 revisions), but they must be treated as exposed. | Rotate both; keep them only in the host's `.env`. |

**Status on `ptest2` (`16c2be7`, `633e2e8`; source-read by P1, not re-run live):** G1 fixed (a `length`/`max_tokens`
finish is not retried; the cap comes from `generation_limits()`), G2 addressed (thinking budget/level set per route),
G3 addressed (attempt telemetry reworked; confirm the H8 test reads the successful attempt's latency), and finding 10
fixed (`64:ff9b::/96` and `::/96` rejected in `SafeReader`). G4–G8 stand.

**Status updates to this review:** finding 9 is resolved; the generation fallbacks were removed by `f4cd74f`
(Gemini is the verifier, DeepSeek the only generator). The live receipt above is the first real call of both routes.
The H8 model test (catch rate, false alarms, Vietnamese quality, cost) is still required.

## Re-review of `ptest2` `68b2371` — P1, 2026-11-07 (about H5.5)

Read-only, in a scratch checkout. Nothing ran against real TEI, models or Supabase.

| Check | Result |
|---|---|
| ruff, ruff format, mypy (122 files) | pass |
| Python tests (database up) | 1,260 pass, 0 skipped, 0 errors |
| Web: frozen install, lint, typecheck, vitest | pass; 38 tests |
| Secrets (key-shaped strings) | none found |
| Lane boundaries | P3 inside its paths; P2's `planv2.md` and the Spec Kit skills are harmless |

**Status of the findings above, checked in the source:**

| # | Status | Evidence |
|---|---|---|
| 1 | Open (merge not started) | `ptest2` is 21 ahead of and 17 behind `main`; `main` into `ptest2` conflicts in the gateway/config/lock files only; `ptest2` into `p4` conflicts in 10 files, none in P4's own paths |
| 2 | **Open** | `backend.py:227` still `min(items, ...)` with no exclusion of answered items |
| 3 | **Open** | no `nextItem` in `lib/data-client.ts`; `next-item` not in the proxy allowlist |
| 4 | **Open** | empty `api_key` skips the check (`main.py`) |
| 5 | **Open** | no attempt idempotency key (`attempt_id` is only stored on traces) |
| 6 | Addressed (partly checked) | phase stays `placement` until a `placement.done.*` trace exists; "no remediation during placement" not confirmed |
| 7 | **Open** | items still looked up by `payload->>'id'` |
| 8 | **Open** | `ci.yml` has only the `api` job |
| 10 | Fixed | `64:ff9b::/96` and `::/96` rejected in `SafeReader` |

Findings 2 and 3 block the first end-to-end run (H7-H8): without them it cannot get past placement.

**P3 retrieval wiring (`47f8eb1`, `50104b8`, `68b2371`), source-read:** good: `retrieve_chunks` rejects a citation whose text,
source URI or page differs from the indexed chunk, and the pipeline fails when a graph concept or an item cites a source
outside the retrieved chunks. Two concerns: (a) retrieval is **optional** (`retriever=None` skips it and every citation check
that depends on it), so the demo path must always pass a retriever and an explicit subject; (b) the default `k` is 12, which
may be too little context to extract a whole graph; test graph quality on the Python topic and raise `k` if needed.

## Full-suite run on `ptest2` `ee5bc3f` — P1, 2026-11-07 (about H7.5)

Scratch checkout; GitHub CI run 111 on the same head also concluded "failure". ruff, format, mypy (153 files): pass. Web
lint and typecheck: pass. Python: 1,330 passed, 1 failed, 10 errors. Vitest: 40 passed, 1 failed. Findings and owners are on the
board (`TEAM.md`): (1) a duplicated `topic_jobs.mode`/`upload_id` migration between P4's `app/content/sql/0008_p4_runtime.sql`
and `supabase/migrations/0008_topic_inputs.sql` (10 errors); (2) a verification-gate test where a `ValueError` precedes the
verifier identity, likely from the generator-family check in `verification_scope` (not confirmed); (3) a web test expecting
`undefined` where the decoder returns `null`; (4) `/ask` registered twice. Findings 2, 3, 4, 5, 7, 8 above were unchanged at this
head. Not re-tested: `4ac891c`.

## What is good (keep it)

- **Engine wiring:** `placement`, `next_step`, `remediate`, FSRS and BKT are called as designed; each learner's state
  change is one transaction under a `for update` row lock; earlier misconceptions are read *before* the new attempt is
  saved; placement seeds mastery once; every decision's trace is stored with its attempt.
- **Link fetching (SSRF):** HTTPS and port 443 only, no embedded credentials, every resolved address must be global, the
  connection is pinned to the checked IP (no rebinding), each redirect is re-validated, size and time are capped,
  proxy variables are ignored.
- **Web proxy:** exact-path allowlist, traversal guard, same-origin check on writes, key kept server-side, streamed size
  limits, `redirect: "error"`.
- **Contracts:** both lanes' request and response shapes match `app/schemas.py`; P3's duplicate data shapes are the only
  maintenance risk (replace with imports once merged).

## Not reviewed

P3's research agent, pipeline and prompts; the gateway's provider adapters and error redaction; P5's UI components
(`workspace.tsx` is 1,294 lines) and accessibility; the row-level security in `0007`; P4's 209 files; behaviour with real
TEI, models, Supabase or the worker under failure.

## Regression test for finding 2 (acceptance)

With one concept and two verified items (difficulty 0.3 and 0.6), a learner who answers each served item wrong must be
served both items before either repeats, and a learner who has answered every item must still be served something
(least recently served) instead of a dead end. A concept with no verified items must not stop `next-item` from returning
another concept. Reproduction used: seed as in `tests/test_learning_backend.py::learning_data`, then
`GET /next-item` → `POST /attempts` four times.

## Re-review

When finding 1 has a trunk, P1 re-runs: lint, mypy, full pytest, the web checks, the finding-2 test, and a placement →
wrong answer → remediation → resume → correct answer → review pass through the HTTP routes.
