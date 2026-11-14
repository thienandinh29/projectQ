# Step 2.1: writing tasks, submission, results page, consent, limits

Part of `specs/writing/` (phase 2). No new dependency and no model call in this step: the analysis here is what plain
code can measure; LanguageTool, ERRANT and the scorer come in 2.2–2.3, LLM feedback in 2.4.

## Contracts
- `GET /writing/prompts` → `[{id, task, type, level, prompt, status}]` from `data/writing/prompts.yaml` (authored;
  `draft` until the owner reviews; draft prompts are listed for `DRAFT_ITEM_LEARNERS` only, like grammar items).
- `POST /essays` `{learner_id, prompt_id, text, consent}` → `202 {essay_id, status: "queued"}`.
  - `consent` must equal the current notice version (`"writing-v1"`): the Vietnamese notice says the essay will be sent
    to third-party AI services for feedback (from step 2.4 on) and can be deleted at any time. Otherwise 422.
  - Text: 1–12,000 characters (NFC); empty or longer is 422.
  - At most `WRITING_DAILY_ESSAYS` (default 3) essays per learner per day (midnight in Vietnam): 429 with a
    Vietnamese message.
- `GET /essays?learner_id=` → the learner's essays, newest first (`id, prompt_id, status, words, submitted_at`).
- `GET /essays/{id}?learner_id=` → `{id, prompt, text, status, submitted_at, result | null, failure_vi | null}`;
  another learner's essay is 404.
- `DELETE /essays/{id}?learner_id=` → 204; the text and the result are gone (the row is deleted).
- Status: `queued` → `analysing` → `done` or `failed`. The worker claims essays with `FOR UPDATE SKIP LOCKED` (as the
  topic queue does); a request never analyses.

## The 2.1 result (deterministic)
Words, sentences, paragraphs; whether Task 2 reaches 250 words; average and longest sentence length in words; linking
words found, grouped by function (from `data/writing/linking-words.yaml`); and a note that grammar errors, the band
and feedback come in later steps. Counting rules are unit-tested (contractions count as one word, numbers as words,
paragraphs split on blank lines).

## Budget (used from step 2.4)
`llm_calls` gains an optional `learner_id` (additive). `services/budget.py` answers "how much has this learner, and
everyone, spent today" and "may this learner call a model now" against `LLM_DAILY_COST_CAP_USD` (whole service) and
`LLM_DAILY_CALLS_PER_LEARNER`. Nothing calls it for a model yet; it is tested now so 2.4 only wires it in.

## Web (second PR of the step)
`/viet` lists prompts and the learner's essays; `/viet/{prompt}` is the editor with a live word count and the consent
notice before the first submission; `/bai-viet/{id}` follows the status and shows the result, with a delete button.
The proxy allows exactly these routes, and `DELETE` for `essays/{id}` (same-origin only).

## Acceptance
API tests (counting rules, limits, consent, ownership, deletion, the worker), web unit tests, one Playwright test (write
an essay, see the counts), the stack smoke test.
