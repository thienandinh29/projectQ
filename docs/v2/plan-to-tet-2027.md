# Plan to Tết 2027 (12 Nov 2026 – 5 Feb 2027)

One owner, about 20 hours a week, about 11 working weeks before Tết (around 6 Feb 2027).

**Goal (changed 12 Nov, see Log):** the first real course is **Vietnamese secondary and high-school mathematics**,
one strand first: **Đại số → Hàm số, grades 6 to 10**. Its knowledge graph follows Chương trình GDPT 2018 môn Toán;
answers are graded objectively in the 2025 exam formats; it starts with one command, is measured, and has been used
by real students. Python (weeks 0–1) stays as the second course. Detailed reasoning: `docs/v2/proposal.md`.

**Where am I?** Look at the *Status* column. Update it in the same PR that finishes the work.
Status values: `done`, `in progress`, `next`, `planned`, `cut`.

| Week | Dates | Goal | Done when | Status |
|---|---|---|---|---|
| 0 | 11–12 Nov | Code sandbox foundations | Runner + sandbox with 15 escape tests in CI; grader with hidden tests; grader self-test in CI (PRs #9–#11) | done |
| 1 | 12–22 Nov | Code exercises in the learning flow | A code answer is graded in the sandbox through the API, BKT updated with the mastery gate, attempt saved and traced; code hint guard (PR #13) | done (12 Nov) |
| 2 | 13–29 Nov | **One-command start** | `docker compose up` runs database, API, worker, runner and web from a `.env`; library indexed with TEI on the owner's machine | next |
| 3 | 30 Nov–6 Dec | **Maths knowledge graph from GDPT 2018** | Spec in `specs/math-course/`; the slice's 25–35 concepts with their *yêu cầu cần đạt* (grade and strand recorded), prerequisites across grades, DAG checked; reviewed by the owner; open maths sources added to the catalogue with each book's own licence checked | planned |
| 4 | 7–13 Dec | **Maths graders** | Short numeric answers (exact fractions and decimals, stated tolerance); *đúng/sai* questions with 4 statements and the 2025 partial scoring; MCQ with a misconception per wrong option; grader self-test in CI | planned |
| 5 | 14–20 Dec | **Web flow on real data + formulas** | Topic → map → placement → practice → remediation through the real API, formulas rendered, no sample data. **Milestone A:** a wrong grade-10 answer is traced back to a grade-8 gap in the browser | planned |
| 6 | 21–27 Dec | **Items and retrieval** | Vietnamese items generated from cited chunks and verified blind, plus owner-written seed items; retrieval hit rate and MRR on a maths question set, with and without a reranker | planned |
| 7 | 28 Dec–3 Jan | **Light week: verifier measured + pilot preparation** | Catch rate on 50 planted-error maths items; consent text for parents and students, privacy notice, anonymised logging; README, screenshots, recorded demo | planned |
| 8 | 4–10 Jan | **Pilot starts + CRAG spec** | 10–20 students (grades 9–10) with parental consent; CRAG state machine: retrieve → judge (reranker) → rewrite once → web → honest "no trusted source" | planned |
| 9 | 11–17 Jan | **CRAG complete** | Web fallback through the allowlist and licence gate; a trace per decision; tier usage, cost and time per topic measured | planned |
| 10 | 18–24 Jan | **Graphs of functions + exam practice** | Function plots (the existing `function_plot` figure kind) shown in the web app; a practice set in the 2025 exam format built from our own items | planned |
| 11 | 25–31 Jan | **Pilot report + v1.0** | BKT calibration, placement vs later performance, cross-grade remediation outcomes, BKT fit if data allows, drop-off; tag `v1.0` | planned |
| — | 1–5 Feb | Buffer before Tết | | planned |

## The slice: Đại số → Hàm số, grades 6–10
Indicative chain, to be fixed against the curriculum text in week 3: fractions and integers (6) → algebraic
expressions and polynomials (7) → identities and factoring (8) → linear equations, inequalities and systems (8–9) →
linear functions (8–9) → quadratic equations and Viète (9) → quadratic functions and their graphs (10). The point
of the slice is cross-grade remediation: an error in grade 10 is traced to the prerequisite that is actually weak.

## Sources and rights
- **Curriculum:** Chương trình GDPT 2018 môn Toán (Thông tư 32/2018/TT-BGDĐT), a legal document, used for concepts,
  objectives and order.
- **Explanations:** open books only, each licence read from the book itself (OpenStax maths books, Vietnamese
  Wikipedia). The Vietnamese textbooks (Kết nối tri thức, Chân trời sáng tạo, Cánh diều) are copyrighted and are not
  ingested. Past exam papers: rights unclear, so used only as a format reference; items are our own.
- Explanations generated in Vietnamese from English sources stay cited to those chunks and pass the verification
  gate; Vietnamese maths terms (e.g. *hằng đẳng thức đáng nhớ*, *biệt thức*) need a glossary checked by the owner.

## Checkpoints
End of weeks 5, 7 and 9: if behind, cut scope (week 10 first), never tests or measurement honesty.

## What the owner provides
| When | What |
|---|---|
| Week 2 | A machine with Docker that can run TEI |
| Week 3 | About 3 hours: review the graph and the glossary against the curriculum |
| Week 4 | Decision: add SymPy for equivalent algebraic answers, or numeric answers only at first |
| Week 5 | Decision: add KaTeX to the web app for formulas |
| Week 6 | Model API keys (DeepSeek, Gemini); about 5 hours of labelling and writing seed items |
| Week 7 | Decisions on consent wording (parents) and data retention |
| Weeks 7–8 | Pilot students (start asking in week 6: siblings, tutoring, former school) |
| Week 8 | A Tavily or Brave key for the web step |

## Risks
- **Minors:** students under 16 need parental consent (Nghị định 13/2023); no pilot before the consent text is done.
- **Sources:** few open maths texts in Vietnamese; quality of Vietnamese generated from English sources is measured,
  not assumed.
- **Scope:** grades 6–12 have hundreds of objectives; stay on one strand until it works end to end.
- **2025 exam format:** confirm against the Ministry's current sample paper before building the scoring.
- January exams: drop week 10 first.

## After Tết
Geometry and statistics strands, grades 11–12 (calculus), proofs with a rubric judge and human calibration,
the Python course in the web app, classroom layer (slides, whiteboard), Elo item difficulty, mastery hysteresis
wired with stored state.

## Log
| Date | Change |
|---|---|
| 2026-11-12 | Plan created; week 0 done |
| 2026-11-12 | Week 1 done ahead of schedule: `/code/exercise`, `/code/attempts`, code hint guard; checked end to end with the real sandbox |
| 2026-11-12 | **First course changed to secondary/high-school maths** (owner's decision): weeks 3–11 rewritten around the Đại số → Hàm số slice; the code editor week and Tin học mapping move after Tết; Python stays as the second course |
