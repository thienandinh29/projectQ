# Spec: Writing (phase 2 of `docs/v2/plan-english-pack.md`)

The learner writes an IELTS Task 2 essay (Task 1 later in the phase); NodeTrail measures it with tools and small models,
explains it with an LLM, feeds the mistakes into the roadmap, and runs a correction loop. The principle of the pack holds:
**tools and small models measure, the LLM explains**, and no score is shown as more certain than it is.

## Writing tasks
1. Prompts are **authored by the project** (Task 2 questions, and in 2.5 Task 1 charts built from data with
   `curriculum/figures.py`). No Cambridge or past-paper prompts. A prompt has a type (opinion, discussion, problem and
   solution, advantages and disadvantages, two-part) and a CEFR target.
2. The learner writes in the browser (word count shown; Task 2 asks for 250+ words; no time pressure unless chosen),
   submits, and gets the result **asynchronously** through the job queue: analysis takes seconds to a minute.
3. **Before the first submission** the learner accepts a notice in Vietnamese: the essay is sent to third-party AI
   services (DeepSeek, Gemini) for feedback. Essays and results can be deleted by the learner.

## Analysis (deterministic, no LLM)
4. Grammar and spelling issues from LanguageTool; sentence length and complexity from spaCy; vocabulary profile by CEFR
   level from the word list; linking words and paragraphing; word count against the task.
5. **Error types.** ERRANT classifies the edits between the essay and a **minimal correction** into about 25 types
   (articles, prepositions, verb tense, subject–verb agreement, …). The correction comes from LanguageTool's
   suggestions where it has one, else from the LLM, instructed to change as little as possible; a correction that
   changes more than the error (checked by edit distance per sentence) is discarded, not used.
6. **Errors into the roadmap.** A hand-written table maps error types to 15–20 hidden nodes. A mapped error is evidence
   against that node (a BKT update with the writing observation model) and may reopen a milestone ("cần ôn").
   **An error that does not map updates nothing**: it is shown, but a wrong mapping would move mastery wrongly.
   Only the 2–3 most important errors per essay are fed in, so one long essay cannot sink a node.

## Score
7. A **small scoring model** predicts the Task 2 band from the text: candidates from Hugging Face (DeBERTa-v3 based
   IELTS scorers) are evaluated on the private set (point 12), the best is kept, then fine-tuned if open data with a
   usable licence allows. The LLM never produces the number.
8. The band is shown as a **range** (e.g. "ước lượng 5.5–6.0") from the scorer's measured error, labelled as an estimate.
   When the scorer and the LLM's criterion judgements disagree by more than 1 band, the result says "không chắc"
   (uncertain) instead of a range.

## Feedback and the correction loop
9. The LLM explains the four criteria (Task Response, Coherence and Cohesion, Lexical Resource, Grammatical Range and
   Accuracy) in Vietnamese. **Every point quotes the essay**; a quote that is not an exact substring of the essay is
   removed by code before display.
10. **Hint first, answer later**: for the 2–3 chosen errors the learner first gets a hint and corrects the sentence
    themselves; the correction is checked (LanguageTool clean and closer to the minimal correction); only then is the
    answer shown.
11. **A target-band rewrite** of one paragraph keeps the learner's ideas, highlights each change and says why. It is
    accepted only if LanguageTool finds no errors, its words stay within the learner's target CEFR level, and the scorer
    rates it higher than the original; otherwise it is regenerated once, then dropped. Good phrases become FSRS cards.

## Limits and cost (first per-learner LLM use)
12. Per-learner daily limit on essays and LLM calls; tokens and cost counted per day (`llm_calls` exists); a daily cost
    cap after which the app offers review only. The limits are settings, not code constants.

## Gate (from the plan)
13. Error → node mapping **≥ 90% correct** on 100 errors checked by hand; scorer **QWK ≥ 0.7** against examiner bands on
    50–100 private essays; **stability**: the same essay scored 5 times differs by ≤ 0.5 band. Results are committed
    whatever they are; the private essays never are (`data/private/`, git-ignored; only metrics).

## Not in scope
Speaking, handwriting, plagiarism checks, an official band, essays from other people without their consent.
