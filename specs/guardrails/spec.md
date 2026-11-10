# Feature: Guardrail evaluation

Lane P1 designs the method and the scoring (`app/evalkit/`); P4 owns the gate, `app/guardrails/metrics.py` and
`data/guardrails/`; the whole team labels at H15–H16. Contracts: `SPEC.md` ("Verification gate"), `TEAM.md`
(`answerability.check`, `metrics.py`). Nothing here changes a contract.

## Why
The demo claims "every question passes a verification gate". Judges will see a number for how often the gate is
wrong. That number must be one we can defend: measured on content nobody tuned for, with the interval it really
supports, and honest about what 50 items cannot show.

## What is measured (positive = a bad item or hint)
| Rate | Meaning |
|---|---|
| **Served error rate** (headline) | bad among what learners were shown |
| Raw bad rate | how often the generator is wrong, before the gate |
| False alarm rate | good content the gate withheld (cost, not safety) |
| Catch rate | gate-scope bad content the gate withheld |

*Gate-scope defects* are the ones answerability is built to catch: item `key_wrong`, `not_supported`, `ambiguous`; hint
`not_supported`, `wrong`. Others (`misconception_mismatch`, `vietnamese_error`, a hint that `leaks_answer`, `not_socratic`,
`other`) are **counted and reported, never charged to the gate**; a served hint that leaks the answer is a tutor failure
and is always shown.

## What 50 items and 20 hints can and cannot show
At 95% confidence, exact intervals:
- Natural bad items are rare (if the generator errs ~10%, a 50-item sample holds ~5), so **catch rate is measured on
  planted errors**, known by construction and needing no human label: all caught shows ≥ 90% only from **36** planted items.
- A served error rate under 5% needs about **73 served items with none bad**; with 50 the interval is wide. The dashboard
  shows the count and the interval, never a bare percentage.

## Decisions (frozen before labelling begins, H15)
- The sample is a **random draw of everything the pipeline generated**, including what the gate withheld, from ≥ 3 topics,
  with the seed written down; never hand-picked.
- Labelers see the item (or hint) and its cited chunks, **not** the gate's verdict or the generator model, in shuffled order.
- Two independent labelers per record where time allows (at least 15 double-labelled); a disagreement on good / in scope /
  out of scope is resolved by P4 and P1 together. Agreement (kappa) is reported; below 0.6, stop and re-align.
- **Items used to tune the verifier are burned.** The H15 numbers describe the pipeline as frozen at H15; after any change,
  measure again on new items or say the number is from before the change.

## Success criteria
- `metrics.py` prints the report in one command and a dashboard JSON; every number has its n and interval.
- The pre-demo claim reads like: "On N items sampled from the live pipeline, X were wrong; the gate let Y through
  (95%: a–b); it caught Z/36 planted errors."

## Out of scope
Fitting the gate to the labelled set, measuring learners' outcomes, labelling the whole library.
