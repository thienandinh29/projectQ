# Plan to Tết 2027 (12 Nov 2026 – 5 Feb 2027)

One owner, about 20 hours a week, about 11 working weeks before Tết (around 6 Feb 2027).

**Goal (changed 13 Nov, see Log):** the first real course is **English for IELTS, starting with vocabulary and
grammar**, for any learner from beginner upward; placement finds where each learner starts. The owner is the first
learner (now about band 5.5, aiming for 7.0 in summer 2027) and uses it daily from week 6. Then reading and Writing
Task 1, a small pilot, and measured results. Maths (GDPT 2018) moves after Tết; its plan is kept below. Python
(weeks 0–1) stays as a later course. Detailed reasoning: `docs/v2/proposal.md`.

**Where am I?** Look at the *Status* column. Update it in the same PR that finishes the work.
Status values: `done`, `in progress`, `next`, `planned`, `cut`.

| Week | Dates | Goal | Done when | Status |
|---|---|---|---|---|
| 0 | 11–12 Nov | Code sandbox foundations | Runner + sandbox with 15 escape tests in CI; grader with hidden tests; grader self-test in CI (PRs #9–#11) | done |
| 1 | 12–22 Nov | Code exercises in the learning flow | A code answer is graded in the sandbox through the API, BKT updated with the mastery gate, attempt saved and traced; code hint guard (PR #13) | done (12 Nov) |
| 2 | 13–29 Nov | **One-command start** | `docker compose up` runs database, API, worker, runner and web from a `.env`; library indexed with TEI on the owner's machine | in progress: stack built and checked in CI (13 Nov); owner's TEI run pending |
| 3 | 30 Nov–6 Dec | **English course spec and grammar graph** | Spec in `specs/english-course/`; grammar points from beginner to about band 7 with prerequisites (DAG checked), each with a level; open word lists added with their licences checked; open grammar sources in the catalogue | planned |
| 4 | 7–13 Dec | **Vocabulary loop** | Word cards scheduled with FSRS; objective item types (meaning, gap-fill, collocation, word form) graded by answer key with accepted variants; routes and tests | planned |
| 5 | 14–20 Dec | **Grammar practice and the level test** | Grammar items with a misconception per wrong option and error correction; a level test (adaptive placement over the grammar graph and vocabulary) that reports an overall level (CEFR A1–C1 with an indicative IELTS band range, labelled as an estimate) and the mastery of each grammar point; remediation to the weak prerequisite; items generated from cited sources and verified blind, plus an owner-checked seed set | planned |
| 6 | 21–27 Dec | **Web flow on real data** | Placement → map → daily vocabulary review + grammar practice in the browser, no sample data. **Milestone A:** the owner studies with it every day from here | planned |
| 7 | 28 Dec–3 Jan | **Light week: verifier measured** | Catch rate on 50 planted-error grammar items; README, screenshots, recorded demo; pilot invitations prepared | planned |
| 8 | 4–10 Jan | **Reading** | Passages from openly licensed texts; objective IELTS-style question types (true/false/not given, matching headings, sentence completion); items verified blind | planned |
| 9 | 11–17 Jan | **Writing Task 1 checker** | Charts as data rendered in the web app; facts in the answer checked against the chart's data; coverage of key features; language feedback labelled as feedback, not a band | planned |
| 10 | 18–24 Jan | **Small pilot** | 5–15 learners at different levels (consent text first; parental consent for anyone under 18) | planned |
| 11 | 25–31 Jan | **Report + v1.0** | Vocabulary retention vs FSRS predictions, BKT calibration on grammar, placement vs later results, drop-off; owner's own study data included; tag `v1.0` | planned |
| — | 1–5 Feb | Buffer before Tết | | planned |

## The English course
- **Levels:** from beginner (about CEFR A1) to about band 7 (C1), so anyone can start; placement decides the start.
- **Vocabulary:** a general list first, then an academic list. Proposal: NGSL and NAWL (licences to be confirmed
  from their own pages in week 3); definitions and examples from openly licensed sources (e.g. Wiktionary) or
  written for the course and labelled as such.
- **Grammar:** a graph of grammar points with prerequisites (e.g. past simple → present perfect → past perfect;
  relative clauses → reduced relative clauses). The point of the graph is remediation: a mistake is traced to the
  prerequisite that is actually weak.
- **Grading:** answer keys first (vocabulary and grammar are mostly objective). Free writing comes later and is
  labelled feedback until it is calibrated against human-scored essays.

## Sources and rights
- Cambridge IELTS books, real past papers and English Profile data are copyrighted and are not ingested. The public
  band descriptors are used as a reference only.
- Explanations come from open sources (e.g. Wikibooks, Wikipedia, open word lists), each licence read from the
  source itself; generated items are cited to chunks and pass the verification gate.

## Yours to do by hand
The owner is aiming for ML engineer, AI engineer, MLOps and data science roles, so the measurement and analysis work
is done by the owner, not the agent. The agent prepares the data, tools and plumbing; the owner writes the code
named below, runs the analysis, and writes the conclusions. Every week ends with an entry in
`docs/v2/decision-log.md` in the owner's own words.

| Week | By hand | Why it matters for the career goal |
|---|---|---|
| 2 | Run the TEI indexing on your machine; explain in the log what each compose service does and why the worker is separate | MLOps: you can describe the deployment you run |
| 3 | Draft the grammar points and their prerequisites from open references; check the word lists' licences on their own pages | Domain modelling; the graph is yours to defend |
| 4 | Write the answer normaliser for gap-fill (case, spacing, accepted variants) and its unit tests | Writing tested Python yourself |
| 5 | Read `engine/bkt.py` and explain one real grammar decision trace in the log (prior, evidence, posterior) | Understanding the model you will be asked about |
| 6 | Study with it daily and keep notes on what feels wrong; you are learner #1 | Product sense from real use |
| 7 | Write the planted errors; compute the verifier's catch rate with a confidence interval | AI engineer: measuring LLM reliability |
| 8 | Label 50 reading items yourself; compare with the verifier (agreement, kappa) | Human labels vs model judgement |
| 9 | Plant factual errors in 10 Task 1 answers; measure what the checker catches and misses | Precision and recall of a checker |
| 10 | Run the pilot: recruit learners, collect feedback | Working with real users |
| 11 | The report: retention vs FSRS predictions, BKT calibration, placement vs later results | Data science: the strongest piece for interviews |

Rule: if the owner cannot explain a piece of code the agent wrote, the agent explains it before the PR is merged.

## Checkpoints
End of weeks 6, 8 and 10: if behind, cut scope (week 9 first, then week 8), never tests or measurement honesty.

## What the owner provides
| When | What |
|---|---|
| Week 2 | A machine with Docker that can run TEI |
| Week 3 | About 3 hours: the grammar graph draft and licence checks |
| Week 5 | Model API keys (DeepSeek, Gemini); checking the seed items |
| Week 6 | Daily use (15–20 minutes) |
| Week 9 | Decision on the consent text and data retention |
| Week 10 | Pilot learners (start asking in week 8) |

## Risks
- **Few open grammar sources** of good quality: measure item quality, and label owner-written explanations as such.
- **One learner until week 10:** the owner's data is real but cannot support general claims; the report says so.
- **Writing scores:** no band score is shown as a measurement until calibrated against human-scored essays.
- January exams: drop week 9 first.

## After Tết
**First:** Pronunciation v0 (below). Then: Writing Task 2 feedback calibrated against human-scored essays; Listening
(text to speech) and the rest of Speaking; the maths course below; CRAG (retrieve → judge → rewrite → web → honest "no trusted source"); the Python course in the web app;
classroom layer (slides, whiteboard); Elo item difficulty; mastery hysteresis wired with stored state.

### Pronunciation v0 (first milestone after Tết, added 13 Nov)
Read-aloud pronunciation checking inside the learning loop. It scores **intelligibility and specific phoneme
errors, never "how native you sound"** (an accent is not an error; the IELTS criterion rewards intelligibility).

| Step | Done when | By hand (owner) |
|---|---|---|
| 1. Offline evaluation | A phoneme recognition model (e.g. a wav2vec2 model fine-tuned on phoneme labels) + alignment to the expected phonemes (Goodness of Pronunciation) scored against expert ratings on speechocean762, and against annotated mispronunciations of the Vietnamese speakers in L2-ARCTIC; correlation with human raters reported with intervals | The evaluation notebook and its conclusion |
| 2. Pronunciation service | Self-hosted service like TEI (audio never sent to a third party, deleted after scoring); read-aloud exercises recorded in the browser; phoneme-level feedback in Vietnamese | Measure latency on CPU and decide if a GPU is needed |
| 3. Into the engine | Phonemes and patterns are concepts with BKT mastery; typical Vietnamese errors are named misconceptions (dropped final consonants, /θ ð/, /ʃ/ vs /s/, clusters, -s/-ed endings, word stress); weak words go to FSRS review | Check the error list against your own recordings |

Notes:
- Whisper is not the judge (it corrects mispronunciations while transcribing); at most it checks whether the words
  were understood.
- Licences to confirm on the datasets' own pages before use (believed: speechocean762 CC BY 4.0, L2-ARCTIC
  CC BY-NC 4.0, non-commercial).
- Voice is sensitive personal data (Nghị định 13/2023): consent first (parents for minors), no cloud speech API for
  real learners.
- New dependencies (PyTorch, a speech model) need the owner's approval at step 1.
- Not in v0: prosody (stress, intonation, rhythm) beyond word stress, free speaking, band scores.

### Maths course (moved after Tết, plan kept)
Đại số → Hàm số strand, grades 6–10, from Chương trình GDPT 2018 môn Toán (Thông tư 32/2018): fractions and integers
→ algebraic expressions → identities and factoring → linear equations and functions → quadratic equations →
quadratic functions. Graders in the 2025 exam formats (multiple choice, *đúng/sai* with 4 statements, short numeric
answers). Vietnamese textbooks are copyrighted and not ingested; open maths books with each licence checked.
Students under 16 need parental consent (Nghị định 13/2023). Decisions then: SymPy and KaTeX.

## Log
| Date | Change |
|---|---|
| 2026-11-12 | Plan created; week 0 done |
| 2026-11-12 | Week 1 done ahead of schedule: `/code/exercise`, `/code/attempts`, code hint guard; checked end to end with the real sandbox |
| 2026-11-12 | First course changed to secondary/high-school maths (owner's decision) |
| 2026-11-12 | Added "Yours to do by hand" per week and `docs/v2/decision-log.md` |
| 2026-11-13 | **First course changed to English for IELTS, vocabulary and grammar first** (owner's decision: own exam in summer 2027, 5.5 → 7.0; the course serves learners from beginner upward). Maths moves after Tết with its plan kept |
| 2026-11-13 | Week 2 stack built: one command starts db, migrations, API, worker, runner and web; smoke test in CI. Week 5 names the level test (overall level + per-point mastery) |
| 2026-11-13 | Pronunciation v0 added as the first milestone after Tết |
