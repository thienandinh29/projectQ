# Offline checks and runner handoff (P1)

Implementation: `app/evalkit/model_checks.py`, covered by this feature's existing spec.
P3 continues to own gateway calls and telemetry; no provider dependencies are added.

Run from `apps/api`:

```powershell
uv run python -m app.evalkit.model_checks ../../data/eval/model-test/example.json
```

Input is a nonempty JSON list. Each case has a unique `case_id`, `task`
(`graph`, `items`, `hint`), `attempts` (raw JSON output strings: original and
optionally one parse-repair retry), `chunk_ids` and `source_uris` from the exact
prompt. Hints also require `correct_option` text and `hint_level` (default 1).
Do not substitute an option letter for its text. Keep model ID, prompt/version,
tokens, timing, cost and raw provider errors in P3's run receipt.

Checks use the first contract-valid attempt. A valid but failing response cannot
be replaced by a better retry. First-try validity is reported separately.

| Gate | Automated evidence | Remaining review |
|---|---|---|
| G1 | Exact P1 KnowledgeGraph, ItemSet or HintResponse validation | None for schema validity |
| G2 | NFC and non-Latin-letter detection on learner-facing strings | Vietnamese identity, terminology and fluency; code/formula exceptions |
| G3 | Item chunk IDs and source URI membership; graph/hint source URI membership | Semantic support; graph/hint contracts lack chunk IDs |
| G4 | Casefolded NFC literal correct-option match at token boundaries, hint levels 1–3 | Paraphrased, option-letter and implied answer leakage |

Graph `name_en`, IDs and URIs are not learner-facing Vietnamese prose. Graph
sources are URIs, not chunk IDs: no public contract was changed to force them
into an incompatible format. For now P3 retains prompt chunk attribution in the
run receipt; P1/P4 review it alongside semantic support. This is an unresolved
limit on the original G3 requirement, not a claim that chunk attribution passed.

CLI exit codes: 1 = detected failure or malformed input; 2 = automatic checks
completed, mandatory review pending. `eligible_for_selection` always remains
false. No model is selected by this tool. G5 verifier counts, G6 measured latency,
G7 cost projections and the final human ratings remain required by the plan.
The example is synthetic plumbing data, never a held-out benchmark result.

Before a live run P1 must record an explicit cost cap and frozen thresholds;
P2/P3 supply exact reachable IDs, P4 supplies the held-out cases. No numeric
budget is invented from unknown remaining credits.
