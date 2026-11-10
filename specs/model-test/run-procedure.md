# H8 model test: run procedure and cost cap

For P3 (runs it) and P4 (supplies cases); P1 decides. Gates, thresholds and decision rules stay as in `spec.md` and
`plan.md`; this file adds the order of work, the settings, the evidence to keep and the **cost cap**. The stack is
decided (DeepSeek generates, Gemini verifies), so this validates it; it does not pick among candidates.

**Freeze:** P1 commits this file before P3's first test call; the commit time is the freeze time, and P3 copies the policy
below into the run receipt. A change after results are seen must be written down with the reason (`spec.md`).

## 1. Cost cap (proposal; P1 may change it before the freeze, never after)

Prices are **not** quoted here: P3 pins each model's list price from the provider's price page on the day, in the run
receipt (`receipts.md`: cost comes from billing or a documented pinned price, never guessed). Token counts below are my
estimate, not measured.

| What | Cap | Rule |
|---|---|---|
| The whole test run (all calls, retries included) | **US$2.00** | Stop at **US$1.60** (80%) and report what was not tested. |
| Model calls for one topic (G7, `topic_cost_cap_usd`) | **US$0.50** | Excludes search, storage and retrieval, which are reserved separately. |

Why these numbers (estimates): the run is about 190k input and 37k output tokens in one pass (3 graph cases of about 30k
input and 4k output; 15 item cases of about 2k and 0.7k; 12 hints of about 2.5k and 0.4k; 20 verifications of about 2k
and 0.5k including Gemini's thinking). With every call retried once, double that. Illustrative prices of US$3 per million
input and US$15 per million output give about US$1.13 for one pass and US$2.26 with retries, which is why the 80% stop
exists; flash-class prices about ten times lower give about US$0.11. One topic is about 150k input and 40k output (1 graph,
30 items, 30 verifications): about US$1.05 at the pessimistic prices (fails the US$0.50 cap) and about US$0.10 at the low
ones (passes), so the cap separates cheap models from expensive ones. Declared volumes for the scorer
(`planned_cases_per_topic`): graph 1, items 30, verification 30, hint 6.

## 2. Before the first call (all must be true)

1. Gateway reaches both providers: `uv run python -m app.llm.smoke --live` passes (new, rotated keys in the host `.env`).
2. P4 has delivered, from the **held-out topic** (not used to tune prompts; P4 names it): chunk sets for 3 graph cases,
   inputs for 15 item cases, 4 items for 12 hint cases (levels 1-3), and 20 verification cases: 10 planted-wrong (key
   flipped or correct text replaced, from verified golden items) and 10 untouched. Case ids are fixed in a manifest.
3. Candidates are listed with **exact model IDs**: the DeepSeek Free model, the DeepSeek Pro model (the same ID is
   allowed; then it is one candidate), and the Gemini verifier. Add a model only if a gate fails.
4. One minimal Socratic tutor prompt written for the test (the real tutor prompts do not exist yet; the tutor result is
   provisional until the H12-H18 evaluation).
5. A running spend counter: tokens from the gateway's per-attempt telemetry times the pinned prices.
6. Two Vietnamese raters booked for about 35 minutes each (blind rating, after the gates).

## 3. Settings, identical for every model

- One route per task, **no fallback**, so a fallback cannot earn another candidate's score. Verification runs inside
  `verification_scope(generator_family="deepseek")`.
- Same prompt, same chunks, one sample per case. The gateway's single repair retry is allowed; record first-try and
  after-retry results apart.
- Temperature: low for graph and verification, moderate for items and hints, logged per task. **Check first:** the
  DeepSeek and Gemini adapters I read set no temperature (only `max_tokens` / `maxOutputTokens`), so unless P3 has added it
  the run uses provider defaults; log that instead of claiming a setting.
- Output cap: raise the graph task's cap above 4096 if the first graph case ends with a length finish (retrying it is
  disabled, see review G1).

## 4. Order (cheapest and most informative first)

1. **Smoke:** one call per candidate (done once on 2026-11-07 10:17 UTC, receipt `docker/llm-live-smoke.json`; repeat after
   the keys are rotated).
2. **Items (15)**, then **hints (12)**, then **graph (3)**, then **verification (20)**.
3. Check the spend counter after each task; at US$1.60 stop.
4. Gates G1-G4 offline: `app/evalkit/model_checks.py` on the raw outputs (`offline-checks.md`). Semantic review stays human.
5. Build one receipts file per tier and scenario (`receipts.md`), then
   `uv run python -m app.evalkit.model_metrics <receipts.json>` from `apps/api`. Exit 0 pass, 1 failure or malformed
   input, 2 human review still needed. No report selects a model by itself.
6. Blind rating of finalists, then P1's decision with the rule that produced it.

## 5. Keep for every case

Model ID, family, task, case id, tokens in and out, successful-attempt latency and total elapsed time (retries and
back-off included), billed cost (sum of all attempts), raw output, whether a retry happened. For verification also
`expected_bad` and `rejected`; a transport or parse failure is `completed=false`, never a rejection. Do not drop failed
cases from the manifest.

## 6. Stop rules

- Spend reaches US$1.60: stop, write down which tasks and cases were not run.
- Three provider errors in a row on one route: stop that route, note it, do not fall back to another family.
- The tutor leaks the correct option once (G4): stop the hint task, report it, continue with the other tasks.
- Any single gate failure: re-run that case once to tell flakiness from a systematic fault (`plan.md`); record both.

## 7. Outputs

`data/eval/model-test/results-<date>.json`: exact model IDs, gate counts per model and task, latency, cost, human scores,
the decision and the rule that produced it, plus the spend total and what was not tested. P3 turns the decision into
`routing.yaml`. Small samples screen models; they do not certify them (15/15 means at least about 78%; 10/10 at least about 69%).

## 8. Decisions this run feeds (P1)

Whether one DeepSeek model serves Free and Pro or Pro needs a stronger one; whether graph extraction fits DeepSeek's input
limit or goes chapter by chapter; whether the verifier's catch rate (at least 9 of 10 planted, at most 2 false alarms of 10)
is good enough to keep Gemini as the only verifier. The reranker decision comes from retrieval evaluation, not from this test.
