# Evaluation gates

Seeded evaluations that CI runs on every push and compares with a committed baseline
(`apps/api/app/evalkit/gates.py`). A cell fails when its score drops more than 0.02 below the baseline;
improvements are reported and pass. Raise a baseline on purpose, in a reviewed commit:

```bash
cd apps/api && uv run python -m app.evalkit.gates run --out ../../evals/baselines/placement-gate.json
```

| Gate | What it measures | Baseline |
|---|---|---|
| `placement` | Exact gap located by placement, simulated learners (slip 0.10, guess 0.25), 3 graph shapes, budgets 6 and 10, the graph walk with verify and the Bayesian placer, 1,000 learners per cell | `baselines/placement-gate.json` |

Planned gates, each needing what CI does not have yet: retrieval hit rate and MRR (needs the embedding server and an
indexed library), verifier catch rate on planted errors and LLM-judge agreement with human grades (need model API
keys and a labelled set). Until they run on a schedule with those resources they are measured by hand and reported
in `docs/v2/`.
