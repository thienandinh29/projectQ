# Step 2.3: the band scorer and the writing gate

Part of `specs/writing/` (spec points 7, 8 and 13). A **small scoring model** estimates the Task 2 band; the LLM never
produces the number. The band is shown as a **range**, never as a point, and only once it has been measured against
examiner bands: before the gate is met, only the owner sees it, labelled as unvalidated.

## What the owner decides first (new dependencies; `tasks.md`)
1. **The candidates**, after reading each model card and its **training data's** licence. This session cannot reach
   Hugging Face, so the agent has not read them. Rules: no NoDerivatives licence (it forbids fine-tuning); NonCommercial is
   flagged and recorded (fine while NodeTrail is free, a blocker for any paid tier); training data scraped from IELTS
   preparation sites or with unclear rights is recorded as a risk. Candidates named in the spec:
   - `KevSun/IELTS_essay_scoring` (an IELTS-band model; its outputs, base model and data to be read on its card);
   - a DeBERTa-v3 model fine-tuned on **ELLIPSE** (English-learner essays scored 1–5 on six analytic measures, not IELTS
     bands: needs calibration to bands, below);
   - others the owner finds, under the same rules.
2. **PyTorch CPU + transformers** as a separate service (`scorer/`, compose profile `scoring`), about 1–1.5 GB of memory
   for a base-size model. Its memory is measured on the owner's laptop next to LanguageTool (about 0.7 GB) before both
   are assumed to fit in 8 GB.
3. **Whether the owner sees an unvalidated band** while the gate is not met (proposed: yes, for `DRAFT_ITEM_LEARNERS`
   only, labelled "chưa kiểm chứng").

## The private evaluation set (owner's hands-on work)
- 50–100 Task 2 essays **with examiner bands** (official sample essays with examiner comments, used only to measure),
  in `data/private/writing/essays.jsonl`: `{id, prompt, text, band, criteria?: {tr, cc, lr, gra}, source}`. Never
  committed; only metrics are.
- Before anything is tuned, **30% of essays are set aside as the final test**, chosen at random with a recorded seed;
  their ids (not their texts) are committed in `evals/writing/test-ids.txt`. Model choice, calibration and any
  fine-tuning use only the other 70% (with 5-fold cross-validation); the test set is scored **once**, at the end.
- The set's band distribution is recorded. With 50–100 essays some bands will have few or no essays; the report says
  which, and no claim is made about them.

## Scoring and calibration (`app/writing/scoring.py`, pure; the service only runs the model)
- The service returns the model's **raw output** (`POST /score {text}` → `{raw: [...], model, revision}`); the model is
  pinned by repository **and commit** in `data/writing/scorer.yaml`, never by a moving name.
- **Calibration** maps raw output to the IELTS scale (0.5 steps) with isotonic regression fitted on the 70% (an ELLIPSE
  model needs it; an IELTS model may still be biased). Fitted parameters live in `scorer.yaml` with the date and the
  essays' count.
- **The range** comes from the cross-validated residuals: the 10th and 90th percentiles of (examiner − predicted),
  added to the prediction and rounded outward to half bands, e.g. "ước lượng 5.5–6.5". A range wider than 1.5 bands is
  shown as "không chắc" instead. Step 2.4 adds the other uncertainty rule (scorer vs the LLM's criterion judgements
  more than 1 band apart).
- Task 1 essays and essays under 150 words get no band ("chưa đủ dài để ước lượng").

## Baselines (every report includes them; a scorer must beat them to be used)
- **Constant:** always the training mean band (QWK 0 by construction).
- **Features:** ridge regression on what 2.1 and 2.2 already measure (words, sentence length, clauses per sentence,
  linking-word groups, LanguageTool errors per 100 words), cross-validated on the same folds. If a neural scorer does not
  beat this clearly, the cheaper model is kept and the report says so.

## Metrics (`app/evalkit/writing_score.py`, run by the owner where the essays are)
- **QWK** over half-band classes with a bootstrap 95% interval (2,000 resamples); MAE in bands; share within 0.5 band;
  confusion by band; per-criterion QWK when the set has criteria.
- **Length bias:** correlation of predicted band with word count, next to the same correlation for examiner bands. A
  scorer that mostly counts words is reported as such.
- **Stability:** the spec's "same essay scored 5 times" is trivially met by a deterministic model on CPU, so it is
  checked as **robustness** instead: changing whitespace, merging two paragraphs and fixing one spelling error each
  move the band by at most 0.5, on every test essay.
- Output: JSON metrics only, written to `evals/writing/score-report.json` and summarised in `docs/v2/writing-eval.md`
  with what the sample can and cannot show.

## Gate (spec point 13)
QWK ≥ 0.7 on the held-out test set (the point estimate, with its interval reported) **and** the robustness check passes.
Until then `scorer.yaml` has `status: draft` and the band is shown only as the owner decided in point 3. A missed target
is recorded with the number, never hidden; the owner then decides to fix it or move on (plan rule).

## Fine-tuning (only if it helps, and only on data whose licence allows it)
A GPU notebook (`notebooks/writing-scorer-finetune.ipynb`, Kaggle or Colab) fine-tunes the chosen model on open data
with a usable licence, then calibrates on the 70%. With 50–100 private essays, fine-tuning on them directly is not
done (it would overfit and leave nothing to test on). Weights stay out of git; the notebook records the data, seed,
hyperparameters and the commit of the base model.

## Result contract (`essays.result`, additive)
`score`: `null` with `score_unavailable_vi` (no service, Task 1, too short, or not shown to this learner), or
`{band_low, band_high, uncertain, model, revision, status: "draft" | "validated"}`. **No point estimate is stored or
shown.** The worker calls the service over HTTP with a timeout (`SCORER_URL`); a failure leaves the rest of the result
intact.

## Web
The result page shows "Band ước lượng: 5.5–6.5" (or "không chắc") at the top of the measures, with: "ước lượng từ một
mô hình nhỏ, không phải điểm thi"; and, while `status: draft`, "chưa kiểm chứng với điểm giám khảo". A link explains how
the range is computed in plain Vietnamese.

## Acceptance
- Unit tests: calibration on synthetic data (monotone, clipped to the band scale), the range from residuals and its
  rounding, the 1.5-band rule, the Task 1 and length rules, QWK against a hand-computed example, bootstrap intervals with
  a fixed seed, the train/test split never leaking a test id into fitting.
- The service tested with a tiny random model in CI (no real weights in CI); the real model only on the owner's
  machine.
- The worker writes `score` when the service is up and explains its absence when not; the stack smoke test checks the
  absence message when `SCORER_URL` is empty.
- The owner's report: candidates' licences, baselines, QWK with intervals on the test set, length bias, robustness,
  memory on the laptop.

## Not in this step
Task 1 bands (2.5), the LLM's criterion feedback and the disagreement rule (2.4), per-criterion bands shown to learners
(only measured here), any band for speaking.
