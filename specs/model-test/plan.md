# Plan: H8 Vietnamese model test

Spec: `specs/model-test/spec.md`. Runs in H6–H8 of `TEAM.md`'s timeline, so P3 can fill `routing.yaml` at H8.

Offline implementation: `app/evalkit/model_checks.py` uses existing P1 contracts
for G1, format screening for G2, input-reference membership for G3, and literal
hint leakage screening for G4. See `offline-checks.md` for input, output and
mandatory semantic review. Tests cover retries, hallucinated citations, cycles,
missing misconceptions, Unicode and leaks. No gateway or shared contract changes.

Receipt scoring: `app/evalkit/model_metrics.py` computes G5 counts with exact
intervals, nearest-rank sample p95 for G6, and declared-volume USD projections
for G7. `receipts.md` defines the input and missing-evidence rules. Counts come
from the existing protocol: graph 3, items 15, hint 12, verification 10+10.
No model calls or automatic model selection; P3 owns measured receipts.

## Candidates
**Decided stack (2026-11-07):** generator DeepSeek (the free model; the Pro tier's model once set), verifier Gemini
(Developer API). Test only those; add a model only if a gate fails. The slots
below are the original plan.

Slots, not names: exact IDs are whatever P3's gateway can reach at H6 and are recorded in the results file.
- **Free:** a cheap Gemini Flash-class model (Vertex), a cheap Claude-class model (Bedrock), one cheap OpenRouter model
  of a third family (no `:free` variants).
- **Pro:** a strong Claude-class model (Bedrock and/or Vertex), a strong Gemini-class model (Vertex).
- Keep ≤ 8 candidates. A model the gateway cannot reach by H6 is dropped, not waited for.

## Test cases (P4 supplies chunks; held-out topic)
Three subject types, matching the golden topics on purpose: programming, a science with formulas, and one more
(humanities or another). **Prompts are tuned on golden topics #1–2; the test uses topic #3 and chunks never used as
prompt examples.**

| Task | Cases | Input | Output checked |
|---|---|---|---|
| Graph extraction | 3 (one per subject, chapter-sized, chunk-ID markers) | chunks | `KnowledgeGraph` JSON |
| Item generation | 15 (5 per subject) | 2–3 chunks | `ItemSet` JSON, 1 item each |
| Tutor hint | 12 (4 items × levels 1–3) | item + chunks + wrong answer | hint text + citations |
| Verification | 20: 10 **planted wrong**, 10 untouched | item + its chunks only | answer vs key |

Planted-wrong items are made by P4 from verified golden items: flip the key or replace the correct option's text.
They are known wrong by construction, so no labelling is needed.

## Run protocol
- Same prompt, same chunks, same settings for every model; only the provider adapter differs. Temperature is fixed per
  task (low for graph and verification, moderate for items and hints) and logged. One sample per case.
- A failed parse gets one retry with the validation error appended (the gateway's normal behaviour). Record
  first-try and after-retry results separately.
- Log per call: model ID, tokens in/out, latency, cost (Langfuse), raw output.
- Automatic checks (G1–G4) are deterministic code, no LLM judge. Where a judge is unavoidable, it is a different
  family from the model being judged.
- Order: **smoke** (one call per model: reachable, JSON mode works) → **gates** on every candidate → **verifier
  pairs** → **blind human rating** of finalists → **decision**.

## Blind human rating
Two Vietnamese speakers, outputs shuffled, model names hidden, per-output sheet: fluency, terminology, register
(addresses the learner as «bạn», not stiff or archaic), pedagogical correctness, each 1–5. Raters score alone; a gap of
more than 1 point on any output is discussed and re-scored. Finalists ≤ 4 models × 3 tasks × 8 outputs ≈ 100 outputs,
about 35 minutes each. **If time runs out, rate Pro tutor and item outputs first and decide Free on gates and cost.**

## What the numbers can and cannot say
Samples are small, so a gate cannot certify a model; it only screens out clearly bad ones. With 95% confidence:
15/15 means the true pass rate is at least ~78%, 14/15 at least ~68%, 20/20 at least ~83%, 10/10 at least ~69%. So the
gates are written as allowed failures per sample size, and any single failure is re-run once to tell flakiness from a
systematic fault. Production safety does not rest on this test: the verification gate runs on every item and Langfuse
tracks dropped questions.

## Thresholds
Initial guesses, adjustable by P1 until H6 and not after: G1 ≤ 1 failure of 15 items (Free), 0 (Pro); G2 0 failures on
all learner-facing strings; G3 0; G4 0 of 12; G5 catches ≥ 9 of 10 planted, ≤ 2 false alarms of 10; G6 graph ≤ 25 s,
items ≤ 15 s, verification ≤ 10 s at p95; G7 cap from the credits left, set by P1 before the run. Human rating bar:
mean ≥ 4.0 for Pro, ≥ 3.5 for Free, no correctness score below 3.

## Results (committed)
`data/eval/model-test/results-<date>.json`: candidates with exact IDs, per model × task gate counts, latency, cost,
human scores, the decision and the rule that produced it. P3 turns the decision into `routing.yaml`.

## Risks
- **Tutor prompts do not exist at H8** (P4 writes them in H8–H11): the tutor is tested with one fixed minimal Socratic
  prompt written for the test, so its result is provisional until the H12–H18 tutor evaluation (≥ 18/20 with P4).
- A model looks worse because the shared prompt suits another family: allow one prompt tweak per model family, logged,
  applied to the whole family.
- Rate limits or quotas on Vertex/Bedrock during the run: spread calls, fall back to OpenRouter, note it in the results.
- Cost: set the cap first, stop the run when it is hit, and report what was not tested.
