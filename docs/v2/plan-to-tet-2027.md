# Plan to Tết 2027 (12 Nov 2026 – 5 Feb 2027)

One owner, about 20 hours a week, about 11 working weeks before Tết (around 6 Feb 2027). Goal: **the Python course
works end to end, starts with one command, is measured, and has been used by real learners**, plus Deep Research
with CRAG and the curriculum mapping that sets NodeTrail apart. Detailed reasoning: `docs/v2/proposal.md`.

**Where am I?** Look at the *Status* column. Update it in the same PR that finishes the work.
Status values: `done`, `in progress`, `next`, `planned`, `cut`.

| Week | Dates | Goal | Done when | Status |
|---|---|---|---|---|
| 0 | 11–12 Nov | Code sandbox foundations | Runner + sandbox with 15 escape tests in CI; grader with hidden tests; grader self-test in CI (PRs #9–#11) | done |
| 1 | 12–22 Nov | **Code exercises in the learning flow** | A code answer is graded in the sandbox through the API, BKT updated with the mastery gate, attempt saved and traced; a deterministic check refuses code hints that contain the solution | in progress |
| 2 | 23–29 Nov | **One-command start** | `docker compose up` runs database, API, worker, runner and web from a `.env`; library indexed with TEI on the owner's machine | next |
| 3 | 30 Nov–6 Dec | **Web flow on real data** | Topic → map → placement → MCQ practice through the real API, no sample data | planned |
| 4 | 7–13 Dec | **Code editor in the web app** | Write code in the browser, see test results and hints, map updates. **Milestone A done** | planned |
| 5 | 14–20 Dec | **Retrieval measured + reranker** | Hit rate and MRR on `data/eval/`, with and without a reranker; threshold calibrated (needed by CRAG) | planned |
| 6 | 21–27 Dec | **Verifier measured + pilot preparation** | Catch rate on 50 planted-error items; consent text, privacy notice, anonymised logging | planned |
| 7 | 28 Dec–3 Jan | **Light week: showcase** | README with diagram, screenshots, recorded demo; pilot invitations sent; buffer | planned |
| 8 | 4–10 Jan | **Pilot starts + CRAG spec** | 10–20 learners on the Python course; CRAG state machine: retrieve → judge (reranker) → rewrite once → web → honest "no trusted source" | planned |
| 9 | 11–17 Jan | **CRAG complete** | Web fallback through the allowlist and licence gate; a trace per decision; tier usage, cost and time per topic measured | planned |
| 10 | 18–24 Jan | **Curriculum mapping** | Python objectives mapped to GDPT 2018 Tin học outcomes (open sources only); stretch: figure renderer in the web app | planned |
| 11 | 25–31 Jan | **Pilot report + v1.0** | BKT calibration, placement vs later performance, BKT fit per course if data allows, drop-off; tag `v1.0` | planned |
| — | 1–5 Feb | Buffer before Tết | | planned |

## Checkpoints
End of weeks 4, 7 and 9: if behind, cut scope (stretch goals first, then week 10), never tests or measurement honesty.

## What the owner provides
| When | What |
|---|---|
| Week 2 | A machine with Docker that can run TEI |
| Weeks 5–6 | Model API keys (DeepSeek, Gemini); about 5 hours of labelling |
| Week 6 | Decisions on consent wording and data retention |
| Weeks 6–8 | Pilot participants (start asking in week 6) |
| Week 8 | A Tavily or Brave key for the web step |

## Risks
- January exams: drop the week-10 stretch first, then week 10.
- Pilot recruiting runs late: start in week 6.
- GDPT 2018 Tin học has not been read yet; its textbooks are copyrighted, so mapping points to open sources or own content.
- A front-end collaborator would take weeks 3–4 in parallel and let the pilot start in mid-December.

## After Tết
Classroom layer (action language, slides, whiteboard), IELTS essay judge with human calibration, Elo item difficulty,
more subjects, mastery hysteresis wired with stored state.

## Log
| Date | Change |
|---|---|
| 2026-11-12 | Plan created; week 0 done |
