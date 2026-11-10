# Tasks: H8 Vietnamese model test

| # | Task | Owner | When |
|---|---|---|---|
| T1 | Freeze spec, gates, thresholds and the cost cap (written, committed) | P1 | by H6 |
| T2 | Candidate list with exact reachable model IDs; smoke call each | P3 | H5–H6 |
| T3 | Case files: chunks for topic #3 (+ held-out chunks), planted-wrong items (10 flipped + 10 untouched) | P4 | by H6 |
| T4 | Runner: same prompt to a list of models, logs tokens, latency, cost, raw output; deterministic checks G1–G4 | P3 (checks: P1 specifies) | H6–H7 |
| T5 | Run gates on all candidates, then verifier pairs; re-run single failures once | P3 + P1 | H7 |
| T6 | Blind rating of finalists by two Vietnamese speakers | two team members | H7–H8 |
| T7 | Decision memo + `results-<date>.json`; P3 writes `routing.yaml` | P1, P3 | H8 |
| T8 | Re-check the tutor choice with P4's real tutor prompts | P1 + P4 | H12–H18 |

P1 implementation for T4: `app/evalkit/model_checks.py` provides offline G1–G4
checks; usage and automation limits are in `offline-checks.md`. P3 still owns the
runner and receipts. G2 language quality and G4 semantic leaks need review; G3
graph/hint chunk attribution remains unresolved because those contracts cite URIs.
T1 is not frozen: the numeric cost cap requires actual remaining-credit data.

P1 receipt scorer for T5/T7: `app/evalkit/model_metrics.py` implements G5–G7
reporting, generator/verifier family checks and combined topic cost screening.
See `receipts.md`; synthetic examples are not live results. Runner execution,
held-out cases, a frozen real cap, human ratings and the final model decision
remain outstanding.

Review regressions covered: decimal cost boundaries (including strictly over-cap
values), complete 10+10 verifier labels and rejection of duplicate fixture IDs.

Final verification record: `validation.md` — full P1 API suite passes with a
temporary Postgres/pgvector service; live H7/model acceptance remains outstanding.
