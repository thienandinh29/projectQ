# Human evaluation protocol

Positive means faulty content that must be blocked. Fixtures contain 50 questions
(44 golden originals, 6 deliberately corrupted variants) and 20 hint candidates
(10 expected acceptable, 10 deliberately faulty). These are agent expectations,
not human labels or real-model predictions. Generic acceptable hints still need
review for the exact question, level and previous answer.

Resolve base_item_id against data/golden/<topic>/items.jsonl; load source and chunks
from that same topic. Evaluation-only corrupt variants must NEVER be seeded as demo
content. Changes of hint level and last_answer are material to verification.

## H15-H16 labelling checklist (not yet performed)

1. Copy human_labels.template.jsonl to a separate human_labels.jsonl file.
2. Two people independently read sources and solve the item WITHOUT its key.
3. Each records a separate annotation with their real name and timezone-aware UTC
   reviewed_at. Do not examine expected_labels.jsonl until independent review ends.
4. Determine whether any factual, support, citation, ambiguity, misconception or
   answer-disclosure defect warrants blocking; has_error=true means block.
5. For hints fill ALL six tutor_rubric booleans: correct, supported, citations_valid,
   relevant_to_history, clear_vietnamese, no_answer_leak. Consider the full history;
   eliminating all but one choice is disclosure. Also check the intended hint level.
6. If reviewers disagree, preserve both annotations, mark disputed, and ask a third
   real reviewer to adjudicate. Record the rationale in notes. Only the adjudicated
   single record per case becomes confirmed. Never count disputed/pending records.

Keep raw annotations in separate files; metrics input has one adjudicated row per ID.
reviewer, reviewed_at, notes and has_error must be entered by actual reviewers.
Do not fill signatures with agent identities. There has been no human review here.

## Predictions and dashboard

predictions.example.jsonl is empty intentionally. Actual prediction rows:
{"id":"item-001","blocked":true,"run_id":"your-run-id","method":"real_model"}
method can be structural or real_model; mock is rejected for quality reports.
Record model-call identities/audits with the run, outside learner payloads.
No predictions have been fabricated from expected labels.

From apps/api:

```powershell
python -m app.content metrics --labels ../../data/guardrails/human_labels.template.jsonl --predictions ../../data/guardrails/predictions.example.jsonl --output ../../data/guardrails/report.json
```

Metric JSON includes numerator/denominator for every rate. A zero denominator
produces null, never 0%/100% success. Definitions:
- content_error_rate: faulty / all confirmed human-labelled content.
- item_error_rate: faulty questions / confirmed questions.
- error_precision: TP / (TP + FP).
- error_recall: TP / (TP + FN).
- false_alarm_rate: FP / (FP + TN).
- faulty_item_escape_rate: faulty questions allowed / paired faulty questions.
- served_item_error_rate: faulty questions allowed / paired allowed questions.
- tutor_rubric_pass_rate: error-free hints passing all six rubric criteria / hints
  with complete confirmed human rubric. Missing rubrics are excluded explicitly.
- tutor_target.met is null unless exactly 20 confirmed hint rubrics are present;
  the acceptance goal is at least 18/20, not a measured result yet.

P1 reviews evaluation design. P2 can consume evaluate() JSON directly; no dashboard
exists in the current checkout. Rebuild samples with python data/guardrails/build_cases.py.
