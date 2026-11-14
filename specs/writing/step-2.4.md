# Step 2.4: LLM feedback with verified quotes, the correction loop, rewrites, phrases to review

Part of `specs/writing/` (spec points 5, 8–12). The first step where an essay goes to a model provider. The principle
holds: **tools and small models measure, the LLM explains**, and nothing it writes reaches the learner until code has
checked it. Every model call goes through `app/llm/gateway.py` and is counted against the daily budget.

## What the owner decides first (`tasks.md`)
1. **The DeepSeek key and model** (`DEEPSEEK_API_KEY`, `DEEPSEEK_FREE_MODEL`). Generation only: there are no generated
   facts to verify blind, so Gemini is not called in this step (the checks are mechanical, below).
2. **Who gets model features** (proposed: `DRAFT_ITEM_LEARNERS` only, until the owner has read DeepSeek's data terms
   and the measurements below; SPEC.md requires a privacy review before real learners' text goes to a provider).
3. **The rewrite's target band** (proposed: half a band above the top of the estimated range, at most 9.0; 6.5 when
   there is no band).
4. **The daily limits** (now `LLM_DAILY_COST_CAP_USD=1.0`, `LLM_DAILY_CALLS_PER_LEARNER=30`), after the first week's
   measured cost per essay.

## 1. Feedback on the four criteria (one call per essay, in the worker)
- Task `writing_feedback` in `routing.yaml` (DeepSeek). Input: the prompt, the essay, and the tool measures (counts,
  LanguageTool issues with their types, complexity). **Not the band:** the LLM's own criterion judgements feed the
  disagreement rule below, which only works if the LLM has not seen our estimate.
- Output (JSON, validated with Pydantic): per criterion (Task Response, Coherence and Cohesion, Lexical Resource,
  Grammatical Range and Accuracy), 1–3 points in Vietnamese, each `{point_vi, quotes: [..], kind: strength | issue}`,
  plus a band judgement per criterion (never shown).
- **Quotes are checked by code:** after NFC and whitespace normalisation each quote must be an exact substring of the
  essay, at least 3 words long. A point whose quotes all fail is removed; dropped points are counted per essay
  (`feedback.dropped`) and logged, never shown. No point without a surviving quote reaches the page.
- **Disagreement rule (spec point 8):** the LLM's overall (mean of its four criteria, rounded to half bands as IELTS
  does) is compared with the middle of the scorer's range; more than 1 band apart shows "không chắc" instead of the
  range, with the reason. The LLM's number is stored for this check and for measurement only.

## 2. Corrections the tools missed (one call per essay; raises recall, spec point 5)
- Task `writing_correct`: for sentences LanguageTool flagged nothing in, the model returns a **minimal** correction or
  "no change". Code then: discards a correction whose token edit distance exceeds 3 (it rewrote, not corrected);
  types the rest with ERRANT; maps types with the error map as in 2.2.
- These issues are marked **"gợi ý từ AI"** and **never move mastery** until the owner has checked 50 of them (precision
  with an exact interval); only then may the owner let them count, with the same draft rule as the error map.

## 3. Hint first, then the answer (no model call)
- For each error that moved the roadmap (2.2's chosen 2–3), the result page offers "Tự sửa câu này": the hint is the
  error's Vietnamese explanation and the marked span from 2.2. The learner types the corrected sentence.
- `POST /essays/{id}/corrections {learner_id, issue_id, sentence}` → `{accepted, tries, answer?, feedback_vi}`. Accepted
  when LanguageTool finds no error of the same kind in the new sentence **and** its token distance to the minimal
  correction is smaller than the original's. After 2 tries, or on "Xem đáp án", the minimal correction is shown.
  LanguageTool checks one sentence (well under a second), so this stays in the request, with a 5-second timeout.
- An accepted correction is **aided** evidence: a BKT update with `bkt.params_with_help(writing params, 1)`, traced, and it
  never counts towards the mastery gate's unaided answers. Showing the answer moves nothing.

## 4. A target-band rewrite of one paragraph (on request, in the worker)
- "Viết lại đoạn này ở band {target}" queues a rewrite job (task `writing_rewrite`): the model rewrites one paragraph,
  keeping the learner's ideas, and gives a reason per change.
- **Code computes the changes** (a word-level diff of the paragraph); a reason is shown only next to a change that
  exists in that diff. Accepted only if: LanguageTool finds no grammar or spelling error in the rewrite; the scorer
  (when calibrated) rates the essay with the rewritten paragraph higher than the original; and, once a licensed CEFR
  word list exists, no word is above the learner's target level (not checkable yet: the page lists the checks that
  ran). Otherwise it is regenerated once, then dropped with the reason.

## 5. Good phrases become review cards
- From an accepted rewrite, the learner saves a changed phrase ("Lưu cụm từ"). Migration `0017`: `learner_phrases`
  `(id, learner_id, essay_id, phrase, sentence, created_at)`; its cards live in `vocab_cards` under the list
  `my-phrases`, asked as a gap-fill of the saved sentence, scheduled by FSRS with the vocabulary session.
  Deleting the essay keeps saved phrases (the learner chose them); deleting a phrase deletes its card.

## Budget and limits (spec point 12)
- Before every call: `services/budget.py` `spent_today(...).allows(...)`; over the cap, the step is skipped and the page
  says "Hôm nay đã dùng hết lượt nhận xét bằng AI; các phần đo bằng công cụ vẫn đầy đủ." Every call is recorded in
  `llm_calls` with `learner_id`, tokens and cost. An essay costs 2 calls; a rewrite 1–2.
- A provider error leaves the tool results intact and says the feedback failed; the job does not retry silently more
  than once.

## Result contract (`essays.result`, additive)
`feedback`: `null` with `feedback_unavailable_vi`, or `{criteria: {tr|cc|lr|gra: [{kind, point_vi, quotes}]},
dropped, model}`; LLM corrections join `grammar.issues` with `source: "llm"`; `score` gains `uncertain_reason` when
the disagreement rule fires. Rewrites and corrections have their own tables (`essay_rewrites`, `essay_corrections`
in `0017`), so the essay's result stays the analysis.

## Measured before the owner opens it to anyone else
- Quote validity: the share of quotes that were exact, per essay and overall.
- Feedback faithfulness: the owner rates 20 essays' points as supported by their quotes or not (with an interval).
- LLM correction precision: 50 corrections checked by the owner (point 2).
- Rewrite acceptance rate, and why rejected rewrites failed.
- Cost and latency per essay (median and 95th percentile) from `llm_calls`.
Recorded in `docs/v2/writing-eval.md`.

## Acceptance
Tests with a fake gateway adapter (no key in CI): quotes kept, normalised and dropped; the disagreement rule; schema
failures; correction minimality and the "gợi ý từ AI" rule; the correction route (accepted, tries, answer, aided BKT
update and trace); rewrite diff, reasons only on real changes, every acceptance check and the single regeneration;
phrase cards through FSRS; the budget stopping calls; a provider error. One live smoke test with the owner's key,
skipped without it. Web unit tests and one Playwright test (self-correction accepted after a hint) on a fake result.

## Not in this step
Task 1 (2.5), speaking, an LLM-written hint (the deterministic hint comes first), showing the LLM's band.
