# Plan: the English pack (from 14 Nov 2026)

The current plan. It implements the owner's proposal, `docs/v2/english-pack-proposal.vi.md` (read that for the why),
and replaces `plan-to-tet-2027.md` (kept for history). NodeTrail is the engine; English is the first subject pack:
content, small scoring models and prompts. The engine decides what to learn next; tools and small models measure
right and wrong; the LLM explains.

- **Budget:** 30–40 hours a week (owner, 14 Nov); the phases below are sized at 30. About 6 months in total.
- **First learner:** the owner (IELTS in summer 2027, target 6.5), then friends and family, free.
- **A phase ends only when its gate is measured.** A missed target is recorded with the number and the reason, never
  hidden; the owner then decides to fix it or move on.

**Where am I?** The *Status* column. Update it in the same PR that finishes the work.
Status values: `done`, `in progress`, `next`, `planned`, `cut`.

| Phase | Dates | Goal | Gate (measured) | Status |
|---|---|---|---|---|
| 0 | 11–14 Nov | Foundations | Code sandbox with escape tests; code practice through the API; one-command start confirmed on the owner's laptop; CI runs the whole stack | done |
| 1 | 14 Nov–13 Dec | **MVP: roadmap, level test, vocabulary, grammar** | Placement accuracy curve by number of questions (target ≥ 90% with ≤ 20); verifier catch rate on 50 planted-error items; the owner studies with it daily for 2 weeks | in progress |
| 2 | 14 Dec–24 Jan | **Writing** (Task 2, then Task 1) | Error → node mapping ≥ 90% on 100 hand-checked errors; QWK ≥ 0.7 against examiner bands on 50–100 private essays; same essay scored 5 times differs by ≤ 0.5 band | planned |
| 3 | 25 Jan–14 Mar | **Pronunciation** (one week off for Tết) | False alarms ≤ 10% on 50–100 own recordings before any red highlighting; correlation (PCC) with human scores on speechocean762 recorded, then improved by fine-tuning | planned |
| 4 | 15 Mar–11 Apr | **Listening and Reading** | Every question verified blind and reviewed before it enters the bank; owner's labels vs the verifier on 50 items (agreement, kappa) | planned |
| 5 | 12 Apr–9 May | **Speaking Part 1–3, and opening to testers** | Per-user limits and a daily cost cap working; ≥ 5 of 10 testers still using it after 2 weeks; old errors falling in later essays over 4 weeks | planned |
| — | 10–31 May | Buffer before the exam | | planned |

## Phase 1 in steps (each about a week)

| Step | Work | Owner by hand | Status |
|---|---|---|---|
| 1.1 | Two-layer roadmap: milestones and hidden nodes with CEFR levels (`specs/english-course/`), starter graph, course checker; candidate sources listed | Extend the graph to the milestones A2–C1 need; read each source's licence on its own page | in progress |
| 1.2 | Vocabulary: word list with CEFR levels, FSRS cards (no prerequisite edges), objective item types (meaning, gap-fill, collocation, word form) (`specs/vocabulary/`) | The gap-fill answer normaliser and its unit tests; review the 30-word seed list | built 14 Nov; owner's normaliser and review pending |
| 1.3a | Milestone tests, quick checks, pass → assumed known, fail → open and remediate; level test over milestones plus a short vocabulary part; authored items (`specs/level-test/`) | Review the items; explain one real decision trace; the accuracy curve | built 14 Nov: engine, items, gate, level test, roadmap, milestone tests, checks, practice through the API; owner's review and analysis pending |
| 1.3b | Items from cited sources: embeddings on a GPU notebook (export → embed → import), generation and blind verification, review queue (`specs/cited-items/`) | The embedding notebook; 50 planted-error items | spec written; needs a verified source and model keys |
| 1.4 | Web flow on real data: level test → roadmap showing milestones → daily review and practice | Use it daily; note what feels wrong | planned |
| Gate | Placement accuracy curve from the simulation; verifier catch rate on planted errors | Write the planted errors; compute both results with intervals | planned |

Testers can try vocabulary and grammar from the end of phase 1: nothing there calls an LLM per user. Per-user limits
and the cost cap arrive with phase 2, because Writing is the first feature that does.

## Later phases (specified when they start; outline from the proposal)

- **Phase 2, Writing.** NLP analysis (grammar checker, sentence complexity, CEFR word levels, linking words);
  ERRANT groups errors into about 25 types, a hand-written table maps them to 15–20 nodes, unmapped errors are shown
  but do not update mastery; a small scoring model for Task 2 chosen on the private evaluation set, then fine-tuned;
  LLM feedback with quoted evidence, score shown as a range; correction loop (hint first, then a target-band rewrite
  checked by the grammar checker and the scorer); good phrases become FSRS cards; Task 1 facts checked against the
  chart's data (`curriculum/facts.py` exists). Runs through the job queue.
- **Phase 3, Pronunciation.** wav2vec2 phoneme recognition → forced alignment → GOP, only 8–10 target sounds
  Vietnamese speakers often miss, lenient thresholds, a recording-quality gate, no red highlighting until false
  alarms are measured; each sound is a node whose slip and guess rates come from the measured error rates.
- **Phase 4, Listening and Reading.** Levelled texts from open sources, audio by TTS or open recordings, IELTS-style
  question types generated ahead, verified and reviewed.
- **Phase 5, Speaking.** Whisper transcript; grammar and vocabulary reuse the Writing pipeline, pronunciation from
  phase 3, fluency measures (speech rate, pauses); bands shown as estimated ranges. Voice data policy, deletion and
  consent before anyone else records.

## Agreed changes to the proposal (14 Nov)

- **Time:** sized at 30 hours a week, not "3–4 hours a day with 70% for exam prep", which did not add up.
- **Private evaluation data:** official sample essays with examiner bands are used only to measure the scorer. They
  stay in `data/private/` (git-ignored) on the owner's machine; only scores and metrics are committed.
- **References, not data:** English Vocabulary Profile and English Grammar Profile guide the owner's judgement;
  nothing is copied from them. CEFR-J and every Hugging Face model and dataset get a licence check before use
  (`data/sources/english-candidates.yaml`).
- **Rewrite wording:** "a target-band rewrite checked by the grammar checker and the scorer", not "exactly one band
  higher": the scorer is an estimate, so the rewrite's band is one too.
- **Levels:** A1 basics stay as hidden nodes under A2 milestones, so a learner below A2 still has a path.
- **Memory:** the owner's 8 GB laptop cannot run bge-m3 in Docker (measured 14 Nov). Heavy batch work (embedding,
  fine-tuning) runs on free GPU notebooks; each new service's memory is measured before the proposal's "8 GB server"
  is promised.

## Decisions the owner makes (new dependencies need approval when the phase starts)

| Phase | Decision |
|---|---|
| 1 | The CEFR word list to use (after its licence check); model keys (DeepSeek, Gemini); a Kaggle or Colab account |
| 2 | LanguageTool (a Java service), spaCy, ERRANT; the scoring model and PyTorch as a separate service |
| 3 | The wav2vec2 model; where it runs; the voice data policy |
| 4 | The TTS engine or open audio source |
| 5 | Whisper model size; accounts and rate limits; the daily cost cap |

## Yours by hand (the measurement work, for ML engineer, AI engineer, MLOps and data science roles)

| Phase | By hand |
|---|---|
| 1 | Grammar roadmap and licence checks; answer normaliser with tests; embedding notebook; placement curve and verifier catch rate |
| 2 | The error-mapping table and its 100 hand-checked errors; scorer selection, QWK and stability on the private set; the fine-tuning notebook |
| 3 | GOP evaluation on speechocean762; false-alarm measurement on your own recordings; fine-tuning on Vietnamese-accented speech |
| 4 | Label 50 items and compare with the verifier |
| 5 | Fluency measures; the tester report (retention, error trend, app estimate vs real exam result) |

Every week ends with an entry in `docs/v2/decision-log.md` in the owner's words. If the owner cannot explain a piece
of code the agent wrote, the agent explains it before the PR is merged.

## Parked (after the English pack)
Maths (GDPT 2018; outline in `plan-to-tet-2027.md`), the Python course in the web app, CRAG for Deep Research,
the classroom layer (slides, whiteboard), Elo item difficulty, mastery hysteresis wired with stored state.

## Risks
The proposal's risk table applies. Added here: the exam comes first (if the project eats exam preparation, stop at
the nearest gate); one learner's data cannot support general claims, and reports say so; every score shown to a
learner is an estimate with a range until measured against examiners.

## Log
| Date | Change |
|---|---|
| 2026-11-14 | 1.3a API: level test, roadmap, milestone tests, quick checks, practice (migration 0015). Fixed on the way: untested prerequisites were treated as weak |
| 2026-11-14 | 1.3a engine and gate: on the 10-milestone roadmap, 20 questions locate the gap exactly for 85% of single-gap learners (target 90%: not met) and 92% of learners with any state; the level shown is exact for 88% and 95%. Recorded as the baseline |
| 2026-11-14 | Step 1.3 specified and split: 1.3a milestones and level test (no LLM), 1.3b cited and verified items |
| 2026-11-14 | Step 1.2 built: vocabulary (word lists, items, FSRS cards, `/vocab/*` routes, migration 0014), checked in the stack smoke test. Real word lists wait for their licence checks |
| 2026-11-14 | Plan created from the owner's proposal; replaces the plan to Tết. Phase 0 done (weeks 0–2 of the old plan). Step 1.1: milestone and hidden-node model, starter roadmap (10 milestones, 19 hidden nodes), candidate sources |
