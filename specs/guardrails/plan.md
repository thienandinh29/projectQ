# Plan: Guardrail evaluation

Spec: `specs/guardrails/spec.md`. Code in `apps/api/app/evalkit/` (new, P1; pure, no dependency).

## Parts
| File | What |
|---|---|
| `stats.py` | exact (Clopper-Pearson) intervals, `Rate`, Cohen's kappa |
| `labels.py` | `Record` format for `data/guardrails/*.yaml`: defects by kind, in/out of the gate's scope, planted records, resolution of disagreements; fails loudly on anything unscorable |
| `guardrail.py` | `score(records, verdicts) -> GuardrailReport`: the rates above per kind, with notes on what the sample cannot show; `to_dict()` for the dashboard, `format()` for the terminal |

## Split of work
P4's `metrics.py` stays thin: `load_records(path)` → run the real gate on each record's snapshot to get `served` or
`rejected` → `score(...)` → print and write JSON. P1 owns the method and the maths; P4 owns the gate and its data.

## Record format (YAML, one list under `records:`)
`id`, `kind` (`item` | `hint`), `source` (`generated` | `planted`), `topic`, `payload` (a snapshot of what was labelled; P4
decides its shape), `chunk_ids`; generated records carry `labels: [{labeler, defects: [...]}]` and, only if labelers
disagree on the class, `resolved_defects`; planted records carry `planted_defect` and no labels (made by flipping the key,
replacing the correct option's text, or citing an unrelated chunk).

## Decisions
- **Class, not exact defect, decides agreement:** two labelers who both say "bad, in scope" agree even if they name
  different defects (the union is kept); only a split on good / in scope / out of scope needs a ruling.
- **Planted records are labelled by construction**, and spot-checked by hand (5 of them) in the labelling hour.
- **Intervals everywhere:** a bare percentage on 50 items would claim more than the data support.

## Risks
Labelers drift in what "ambiguous" means: a 10-minute calibration on 5 shared items opens the hour. The hour is short:
if it runs out, single-label and double-label only 15 (kappa), and say so. Hints are only 20, so their intervals are wide.
