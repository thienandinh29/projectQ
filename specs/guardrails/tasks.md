# Tasks: Guardrail evaluation

| # | Task | Owner | When |
|---|---|---|---|
| T1 | `app/evalkit/` stats, label format, scoring + tests (done) | P1 | done |
| T2 | `metrics.py`: load records → run the real gate → `score` → print and write dashboard JSON | P4 | by H12 |
| T3 | Planted records: ≥ 36 items (flip key / replace correct option / unrelated chunk), plus hints; spot-check 5 | P4 | by H14 |
| T4 | Draw the random sample from the final pipeline's output (seed recorded, ≥ 3 topics, includes withheld items) | P4 + P1 | H14–H15 |
| T5 | Labelling hour: calibrate on 5, label 50 items + 20 hints (`labelling-protocol.md`) | whole team | H15–H16 |
| T6 | Resolve disagreements, run `metrics.py`, review the report together | P4 + P1 | H16–H17 |
| T7 | Dashboard shows the numbers with n and interval, dated, with the draft label | P2 + P5 | H17 |
