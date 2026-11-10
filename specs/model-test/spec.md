# Feature: H8 Vietnamese model test

> **Status (2026-11-07): the stack is decided** (team, including P1): generation = DeepSeek (no fallback to another family),
> verification = Gemini (Developer API), embedding = BAAI/bge-m3. The test below is therefore a **validation of that stack against the same gates**, not a selection
> among candidates; the candidate list shrinks to the generator, the verifier and the fallbacks actually used. What it still
> decides: (1) whether one DeepSeek model suffices for Free and Pro or Pro needs a stronger one (compare on the gates and the
> blind rating; the list prices differ by about 12x); (2) whether having no generation fallback is acceptable for the
> demo (it fails explicitly; the pre-generated topics are the fallback); (3) whether graph extraction fits DeepSeek's input limit or must go chapter by chapter; (4) the tutor, at
> H12–H18. A gate that fails changes the stack for that task only, by P1's decision.

Lane P1 designs and decides; P3 runs it through the gateway; P4 supplies cases; two Vietnamese speakers rate.
Contracts: `TEAM.md` → "LLM (P3)" model roles, "Two modes", H8 checkpoint ("Pick Free/Pro models from the Vietnamese
test"). Nothing here changes a contract.

## Why
`routing.yaml` needs concrete models per tier and task. A wrong pick shows up in front of judges as bad Vietnamese, broken
JSON, a made-up citation, or a tutor that leaks the answer. The test picks models on evidence, not on reputation, and
fixes the rules **before** anyone sees a result.

## What it decides
| Decision | Fed to |
|---|---|
| Free-tier model for each task below (cheapest that passes) | `routing.yaml` (P3) |
| Pro-tier model for each task below (best that passes) | `routing.yaml` (P3) |
| Generator × verifier pairs, always different families | `routing.yaml` (P3), P4's gate |
| Long-context model for graph extraction | `routing.yaml` (P3) |
| Tutor model, **provisional** (see plan: tutor prompts do not exist yet at H8) | confirmed at the H12–H18 tutor evaluation |

Tasks under test: **graph extraction** (Vietnamese concept names and descriptions, prerequisite edges, chunk-ID
citations), **item generation** (MCQ with a misconception per wrong option), **tutor hint** (levels 1–3, `/ask` shares
its style), **verification** (blind answer from the cited chunks only).

## Gates (hard, per model × task; frozen at H6)
| # | Gate | Check |
|---|---|---|
| G1 | Valid structured output | parses and passes the Pydantic contract after at most one retry |
| G2 | Vietnamese output | every learner-facing string is Vietnamese, NFC, no foreign-script characters |
| G3 | Citations are real | every cited `chunk_id` was in the input |
| G4 | Tutor never leaks | the correct option never appears in a level 1–3 hint |
| G5 | Verifier catches planted errors | catches the planted-wrong items, few false alarms |
| G6 | Latency | p95 within the Nhanh budget share for that task (< 60 s to graph + first questions in total) |
| G7 | Cost | projected cost per topic under the cap P1 sets before the run |

Allowed failures are in counts, not percentages, because the samples are small (plan, "What the numbers can and cannot
say"). **Human rating** (blind, finalists only): Vietnamese fluency, terminology, register, pedagogical correctness, 1–5.

## Decision rules (frozen at H6)
- **Free:** the cheapest model that passes every gate; costs within 10% → higher human fluency.
- **Pro:** the highest mean human score among models that pass every gate and fit the latency budget; scores within
  0.2 → cheaper.
- **Verifier:** a different family from its generator; highest catch rate, then fewest false alarms.
- **No Free model passes a task:** do not relax the gate. P1 decides: that task uses a Pro model on Free, or the
  feature is cut from Free.
- A change to gates or rules after results are seen is allowed only if written down with the reason.

## Success criteria
- Every Free and Pro slot in `routing.yaml` for the four tasks is filled by a model that passed every gate, with the
  results file committed.
- The verifier of every generator is from another family.

## Offline evidence scorer

P1's `app/evalkit/model_metrics.py` consumes P3 receipts, never calls providers.
It requires a unique predeclared case manifest, reports missing observations,
and uses the counts and thresholds in the plan without silently relaxing them.
G5 reports catches/false alarms with exact intervals. G6 uses nearest-rank sample
p95 and includes failed/retried case time. G7 projects measured case cost at
declared topic volumes and checks the combined declared task cost separately.
Incomplete evidence cannot produce a pass or automatic model selection. Family
identity and frozen pre-run policy are supplied by the runner and reviewed by P1.
Input details and limitations: `receipts.md`.

## Out of scope
Scoring English quality, benchmarking beyond these four tasks, fine-tuning, the reranker decision (that comes from the
retrieval evaluation, `specs/retrieval/`).
