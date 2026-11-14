# Step 2.2: grammar check, minimal correction, error types, errors into the roadmap

Part of `specs/writing/` (spec points 4–6). The worker checks each essay with **LanguageTool**, builds a **minimal
correction** from its suggestions, types every edit with **ERRANT**, and feeds the 2–3 most important mapped errors into
the roadmap as BKT evidence. Still **no model call and no score** (the LLM correction fallback is 2.4, the scorer 2.3), and
the essay **never leaves our machines**: LanguageTool runs as our own container.

## Dependencies (approved by the owner on 14 Nov 2026)
- **LanguageTool 6.8** (LGPL-2.1, used unmodified as a separate service): our own image (`languagetool/`) on a Java 17
  runtime, `-Xmx1g`, without the n-gram data (8 GB+). Built from LanguageTool's own `languagetool-server` and
  `language-en` artifacts on Maven Central instead of the release zip (the same code; Maven Central is reachable where
  the zip's host was not), with **every one of the 172 jars pinned by SHA-256** (`languagetool/jars.sha256`). Compose
  profile `writing`, opt-in like TEI.
- **spaCy 3.8** (MIT) with `en_core_web_sm` 3.8.0 (MIT, pinned by URL and hash in `uv.lock`) and **ERRANT 3.0.2** (MIT,
  supports spaCy 3.2 to 3.x) in the API/worker image.

## Pipeline (worker, per essay; `app/writing/`)
1. **Sentences.** spaCy splits sentences; from 2.2 on, every sentence measure uses spaCy (the word count keeps the 2.1
   rule so the editor's live count still matches).
2. **Check.** LanguageTool checks the text twice, `en-GB` and `en-US`. Kept categories: `GRAMMAR`, `TYPOS`, `CASING`,
   `CONFUSED_WORDS`, `PUNCTUATION` (shown, never mapped). Style categories (`STYLE`, `REDUNDANCY`, `TYPOGRAPHY`,
   `COLLOQUIALISMS`, `MISC`) are dropped in this step. A **spelling** match is kept only if both variants flag the same
   span, so British and American spellings both pass (IELTS accepts either, consistently used). Other matches come from
   `en-GB`.
3. **Minimal correction.** For each sentence, apply the first suggestion of each kept match (non-overlapping, left to
   right). A match without a suggestion is shown but has no correction and no type. **Minimality check:** the token-level
   edit distance between the sentence and its correction must not exceed the tokens the matches cover plus 2; otherwise
   that sentence's correction is discarded (its matches are shown, untyped).
4. **Error types.** ERRANT compares each original sentence with its correction and classifies the edits (`M:`, `R:`,
   `U:` operations × about 25 types: `DET`, `PREP`, `NOUN:NUM`, `VERB:SVA`, `VERB:TENSE`, `VERB:FORM`, `ADJ:FORM`,
   `SPELL`, `ORTH`, `WO`, …). Each edit is joined back to the LanguageTool match whose span it overlaps.
5. **Mapping** (`data/writing/error-map.yaml`, hand-written, `status: draft` until the owner's check). A row maps an
   ERRANT type, optionally narrowed by the corrected token (lemma or fine POS tag), to one **hidden node**; anything
   without a row is **unmapped**. Starting rows (the current roadmap supports few):

   | ERRANT type | Condition | Hidden node |
   |---|---|---|
   | `DET` | — | `articles-basic` |
   | `NOUN:NUM` | — | `plural-nouns` |
   | `VERB:SVA` | corrected lemma `be` | `be-present` |
   | `VERB:SVA` | otherwise | `present-simple` |
   | `ADJ:FORM` | corrected tag `JJR` / `JJS` | `comparatives` / `superlatives` |
   | `VERB:TENSE` | correction is `have/has + VBN` | `present-perfect-form` |
   | `VERB:TENSE` | `VBN`/`have` ↔ `VBD` | `present-perfect-vs-past` |
   | `ADV` | original lemma `more` / `most` ("more bigger") | `comparatives` / `superlatives` |
   | `PREP`, `VERB:FORM`, `WO`, `SPELL`, `ORTH`, `PUNCT`, other | — | none yet (needs new nodes; owner's roadmap work) |

   Each row has a Vietnamese explanation (`explain_vi`), shown with the error whether or not it maps. The course checker
   refuses a row whose node is not a hidden node of the course.
6. **Evidence.** From the mapped errors, choose at most **3 per essay, at most 1 per node**: the node with the most
   errors first, then the earliest. Each is a BKT update with the new **writing observation model**
   (`observation` in `error-map.yaml`: `p_slip` 0.3, a learner who knows the structure still slips in free writing;
   `p_guess` 0.4; `p_transit` 0, making an error is not practice; the engine's own parameters are unchanged). One error moves a node from 0.95 to 0.90, so one
   essay does not reopen a mastered milestone; the same error in a second essay (0.83) does, and the milestone shows
   "cần ôn". Each update stores a `DecisionTrace` (`bkt_update`, rule `writing.error`, item `essay:{id}:{issue}`) with
   the node and the type, **never the essay's text**.
   **Draft rule:** while `error-map.yaml` is `draft`, evidence is applied only for `DRAFT_ITEM_LEARNERS`; for everyone
   else the errors are shown and nothing moves. It becomes `reviewed` when the owner's 100-error check reaches 90%.
7. Evidence is applied in the same transaction that marks the essay `done`, so a retried job never counts it twice.

## Result contract (`essays.result`, additive: `version` 2; 2.1 results stay as they are)
- `grammar`: `null` with `grammar_unavailable_vi` when `LANGUAGETOOL_URL` is not set or the service fails (the essay
  still gets the 2.1 measures; "no errors" is **never** shown when nothing was checked). Otherwise
  `{checker, issues: [{id, sentence, sentence_start, start, end, text, suggestion|null, category, rule_id, message_en,
  errant_type|null, node|null, node_vi|null, explain_vi|null, evidence: bool}], counts: {by_type}}`.
- `complexity`: `{sentences, clauses_per_sentence, complex_sentence_share}` from spaCy dependency labels (`advcl`,
  `ccomp`, `relcl`, `acl`, `xcomp`).
- `evidence`: `[{node, errant_type, issue_id, p_before, p_after}]` (empty when the draft rule applies).
- Deleting an essay deletes its text and result; mastery changes and their traces remain (they contain no text). The
  consent wording (owner's decision) should say so.

## Settings
`LANGUAGETOOL_URL` (empty: grammar not checked, said so on the page). The observation parameters live in
`error-map.yaml`, not in code, so the owner can change them with a reason in the decision log.

## Web
The result page gets **"Lỗi ngữ pháp và chính tả"**: each issue with its sentence, the span marked, the suggestion, the
Vietnamese explanation and, when it moved the roadmap, a link "Đã ghi vào lộ trình: {node}" to the node; then the
complexity measures. Unmapped errors are labelled as not counted in the roadmap. No red highlighting of the whole text.

## For the gate (owner's hands-on work)
- `python -m app.writing.export_errors` writes the mapped errors of chosen essays as a sheet in `data/private/writing/`
  (sentence, edit, type, node, an empty `correct_node` column).
- `app/evalkit/writing_map.py` scores the filled sheet: mapping accuracy with an exact (Clopper–Pearson) interval, per-type accuracy, and
  **coverage** (the share of errors that map at all, expected to be low until new nodes exist). Committed as metrics only.

## Acceptance
- Unit tests on recorded LanguageTool responses (no service needed): category filter, the two-variant spelling rule,
  minimal correction and its check, ERRANT typing on fixed sentence pairs, every map row, evidence selection (cap,
  one per node, order), the draft rule, the observation model's numbers, idempotency.
- An integration test against a real LanguageTool when `LANGUAGETOOL_URL` is set; CI's `stack` job starts the `writing`
  profile and the smoke test checks that "She go to school every day." yields a `VERB:SVA` issue mapped to
  `present-simple`.
- The Playwright essay test also sees a mapped issue on the result page.
- Measured and recorded in `docs/v2/plan-english-pack.md`: LanguageTool's memory on the owner's laptop, and the time to
  analyse a 300-word essay.

## Measured (14 Nov 2026, the agent's sandbox, outside Docker)
- LanguageTool's memory: about 650–690 MB resident with `-Xmx1g`. The owner's laptop is still to be measured.
- A 328-word essay: LanguageTool's two calls 0.32–0.40 s, spaCy and ERRANT 0.04–0.06 s; loading spaCy and ERRANT
  once at worker start 0.7 s.
- **Recall is limited.** LanguageTool is rule-based: it catches "She go", "They is" and "The roads is" at the start of a
  sentence, but missed "others thinks", "roads is" in mid-sentence and "public transport bring" in the same test essay.
  A missed error moves nothing (the safe direction for mastery), but the learner's list is incomplete; the page says
  the tool can miss errors. The owner's check adds recall (errors the tool missed in their own essays), and the LLM
  correction fallback in 2.4 is the planned way to raise it.

## Not in this step
The LLM correction fallback and feedback (2.4), the band (2.3), style suggestions, a vocabulary profile by CEFR level
(needs a licensed CEFR word list, step 1.2's open decision), new hidden nodes for prepositions, word form and word order
(owner's roadmap work).
