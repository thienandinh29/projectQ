# H8 measured receipts — P1 scorer / P3 runner handoff

Run from `apps/api`:

```powershell
.venv\Scripts\python.exe -m app.evalkit.model_metrics ../../data/eval/model-test/receipts-example.json
```

Input is a nonempty JSON list of receipts. Run one tier/scenario per file. Use
exact provider model IDs and canonical family names (e.g. `gemini`, `claude`);
the scorer compares family strings and cannot independently identify a provider's
model. Do not mix alternative model candidates into a claimed topic cost total.

## P3 gateway translation (checked against ptest 9887d32)

| P3 gateway task | Evaluator task |
|---|---|
| `graph` | `graph` |
| `items` | `items` |
| `tutor` | `hint` |
| `verify` | `verification` |

Use the actual `Completion.route` metadata, not the requested provider/model.
For candidate benchmarking isolate exactly one candidate route, with bounded
parse repair, so a fallback model cannot earn another candidate's score.
If provider fallback is being measured as a separate system experiment, keep
every attempt's actual route in its receipt and report that experiment separately.
Convert gateway `latency_ms` to seconds, but measure outer case elapsed wall time
to include retries/failures. `Completion` and `Attempt` supply token counts, not
USD cost; obtain cost from measured billing/telemetry or a documented pinned
price calculation. Missing cost stays null. Never infer it from token count alone.

P3 keeps raw outputs and request-scoped telemetry in its run record. Supply the
original and at most one contract-repair output to the offline checker. Gateway
reachability probes alone are not held-out benchmark cases. P4 supplies actual
verified/known-wrong labels; unavailable or unparseable verdicts stay incomplete.

Each receipt contains:

- `model_id`, `model_family`, `task` (`graph`, `items`, `hint`, `verification`).
- `expected_case_ids`: predeclared unique cases; no fewer than 3/15/12/20 for
  graph/items/hint/verification respectively. Do not remove failed cases.
- `observations`: one row per case with `case_id`, `elapsed_s`, `cost_usd`,
  `completed`. Null measurements mean missing evidence; zero cost is permitted.
  Sum billed attempts, including failed calls and parse retries, into case cost.
  Latency is elapsed case wall time including retries, not summed concurrent time.
- Verification: `generator_family`; each observation has `expected_bad` and
  `rejected` booleans. Require exactly 10 planted-wrong and 10 untouched cases.
  A transport/parse failure is `completed=false`, not a successful rejection.
- Optional `offline_cases`: original G1–G4 EvaluationCase inputs. IDs must be in
  the manifest and tasks must match. Missing offline IDs are reported explicitly.
- `planned_cases_per_topic`: positive integer volume used to project task cost.
  `topic_cost_cap_usd`: positive USD cap fixed by P1 before the run. Preserve
  frozen policy, timestamp, dataset version and prompts in P3's run receipt;
  the scorer cannot prove they were fixed before results were seen.
- Costs/caps accept decimal JSON numbers or decimal strings; monetary comparisons
  use exact decimal/rational arithmetic, without a tolerance that could admit
  an over-budget result. Numeric report values are converted only for display.
- `latency_budget_s`: required for hints, whose budget is unspecified in the
  existing plan. Other tasks use the plan's fixed 25/15/10-second budgets.

Output has `models` and `topic_cost`. Each metric reports `pass`, `fail`,
`missing`, or `not_applicable`, with its sample count and notes.

- G5: at least 9/10 catches, at most 2/10 false alarms. Reports exact 95%
  intervals using the existing P1 statistics helper; this tiny test is a screen,
  not a population-level quality guarantee.
  Every one of the exactly 20 observations needs explicit ground truth and a
  completed verdict; extra or unlabelled rows prevent a pass.
- G6: nearest-rank p95 (`ceil(.95*n)`), including all measured cases. With three
  graph cases this is the maximum, not a robust estimate of production p95.
  Failed cases cannot produce a latency pass.
- G7 per task: mean measured case cost times declared volume. This is only that
  task's contribution; a task pass does not establish an affordable whole topic.
- G7-topic: sums contributions only when one graph, one items and one verification
  receipt (optional hint) share a cap. Alternative candidates, missing tasks or
  incomplete costs produce `missing`. The total covers only declared volumes:
  retrieval/search/storage or other fees are not implicitly included. Reserve
  those costs when P1 sets the model-call cap.

Exit 1 means a detected failure or malformed input; exit 2 means human/P1 review
is still required. No report automatically selects a model. G1–G4 reviews, blind
ratings, measured source quality and P1's model decision remain mandatory.
`receipts-example.json` uses invented IDs, times and prices for plumbing tests;
it is not a benchmark or an estimate of any real provider's price.
