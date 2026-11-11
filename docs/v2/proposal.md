# NodeTrail v2 — proposal

Date: 2026-11-11. Owner: one person (student, aiming at ML engineer, AI engineer, MLOps and data science roles),
working with an AI coding agent. Repository: `thienandinh29/projectQ` (code Apache-2.0, `data/` CC BY-NC-SA 4.0).

## 1. What NodeTrail is, and what it is not

An adaptive tutor that answers one question well: **what should this learner learn next, and can we trust what we
show them?** A learning engine (BKT, Bayesian placement, FSRS, prerequisite remediation) decides; language models
explain and generate inside a harness of citations, verification and deterministic grading; every decision carries
a readable reason.

It is **not** a lesson-presentation product. OpenMAIC (Tsinghua, ~43k stars) is far ahead there; we learn from it
(`docs/research/openmaic-study.md`) and stay different on the learner model, content verification and grading. We do
not fork it: a different stack (TypeScript vs our Python core) and an opposite core design (an LLM agent runs their
class; our engine decides).

## 2. Where it stands (evidence, not claims)

| Area | State | Evidence |
|---|---|---|
| Learning engine | BKT, FSRS, remediation, next-step rules, traces in Vietnamese | Unit tests; `specs/engine/` |
| Placement | Bayesian placer is the default; graph walk kept | `docs/v2/placement-eval.md`: 53–82% exact gap at 6 questions, ≥ 90% at 10–30; target (90% in 6) **not met** |
| Mastery | Confirmed mastery needs 2 unaided correct answers; hints weaken evidence | `specs/mastery-gate/spec.md` |
| BKT fitting | EM with held-out scoring | `docs/v2/bkt-fit-eval.md`: needs ~100 learners per concept to beat the defaults reliably |
| Content safety | Citations, cross-family blind verifier, deterministic hint-leak checks | `tests/content/test_hint_leaks.py`; verifier catch rate **not measured** |
| Sources | OpenStax books from git with licence and chapter order from metadata; fixed HTML licence inheritance | `specs/source-catalog/`; not yet indexed with the embedding server |
| Curriculum | Courses declare modalities and figure kinds per objective; figures are data with computed ground truth | `specs/curriculum-modalities/`; no renderer yet |
| Evaluation in CI | Placement accuracy gate against a committed baseline | `evals/` |
| Tests | API 1,656 passing (20 skipped), ruff and mypy clean; web tests in CI | Local runs and CI |
| Not proven | Real learners, learning outcomes, retrieval quality, verifier catch rate, LLM-judge agreement, Deep Research on the catalogue, the web flow without sample data | — |

## 3. Plan

Principle: **one vertical slice finished, measured and running beats a wide platform 60% done.** The slice is
*Python basics, end to end*. Each milestone has a definition of done that can be checked.

### Milestone A — Python slice runs for real (engineering)
1. **Code sandbox and grader**: learner code runs against the course's test cases in isolation (no network, CPU,
   memory and time limits); a grader returns a 0–1 score; BKT updates from it. *Done when* the Python course's code
   objectives are graded end to end, with tests for escape attempts (network, file system, fork bomb, long loops).
2. **Web flow without sample data** for the Python course: topic → placement → practice (MCQ and code) → hint →
   review. *Done when* a recorded run uses only the real API.
3. **One-command start**: Dockerfiles for API and web, compose with database and embedding server, health checks.
   *Done when* a fresh machine runs the slice with one command and a `.env`.

### Milestone B — measured (AI engineering, data science)
4. **Retrieval quality**: index the catalogue, run the labelled Vietnamese question set; hit rate and MRR with
   intervals; compare with and without a reranker. Needs the embedding server.
5. **Verifier catch rate**: plant errors in 50+ items; report catch rate and false alarms with intervals. Needs model
   API keys.
6. **Claim-shortlist fact check** for explanations and hints (idea from OpenMAIC): numbers, dates, absolute words,
   contradictions; checked against cited passages.
7. **More gates in CI** for what can run without secrets; scheduled jobs for the rest.

### Milestone C — real learners (data science, ML)
8. **Pilot**: 10–20 learners, consent and privacy notice, anonymised attempts. Report: placement agreement with later
   performance, calibration of BKT predictions (log loss, Brier, reliability plot), hint use, drop-off.
9. **Fit BKT per course** on pooled pilot data; adopt only if it beats the defaults on held-out learners
   (`bkt-fit-eval.md` explains why per-concept fits need more data).
10. **Mastery hysteresis wired** (needs stored mastery state, an additive migration).

### Milestone D — teaching layer (AI engineering, product)
11. **Action language for the classroom** (idea from OpenMAIC): `say`, `show_slide`, `show_figure`, `draw`, `ask`;
    the engine inserts questions and decides the next scene.
12. **Figure renderer** in the web app (charts, maps, processes, diagrams) and the item `figure` field.
13. **Rubric judge** for short answers, essays and figure descriptions, with a human-labelled calibration set and
    agreement (kappa) reported before use; IELTS Writing as the second course.
14. **Deep Research on the catalogue** (M1 in `docs/v2/plan-m0-m1.md`).

### Platform hygiene (any time)
Row-level security on the learner tables, renaming the contest-era `p4_*` tables and modules, a README with a
diagram, screenshots and the measured numbers.

## 4. What each role can point to

| Role | Strongest evidence after the plan |
|---|---|
| ML engineer | Bayesian placement with an evaluation; EM fitting with a data-needs study; calibration on pilot data |
| AI engineer | Cross-family verification with a measured catch rate; hint-leak checks; retrieval evaluation; a calibrated rubric judge |
| MLOps | Evaluation gates in CI with baselines; reproducible runs; one-command deployment; versioned sources and models |
| Data science | Pilot analysis, ablations (placement strategies, hints), honest negative results with intervals |

## 5. What is needed from the owner

- A machine with Docker for the embedding server, and model API keys (DeepSeek, Gemini) for milestones B and D.
- People for the pilot, and a decision on consent wording and data retention.
- Decisions flagged in PRs: placement default (`bayes` vs `walk`), the constants of the mastery gate (2 unaided
  answers, hint shares), whether to add a symbolic-maths dependency for function plots.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Scope grows again (as in the contest) | One slice at a time; a milestone ends with a recorded run and a report |
| Simulation results do not hold for real learners | Every claim is labelled simulated until the pilot; gates protect against regressions, not against wrong models |
| LLM judges and verifiers look reliable without being measured | No judge used without a human-labelled agreement report |
| Licences (NC textbooks) block commercial use | Data licensed separately; commercial use needs CC BY / BY-SA sources or permission |
| Running learner code | Sandbox with no network and hard limits; escape tests in CI |

## 7. Merged on 2026-11-11

PR #2 Bayesian placement, #3 curriculum modalities and figures, #4 mastery gate, #5 hint leak checks, #6 evaluation
gates, #7 BKT fitting. Combined `main` after #4–#7: API 1,656 tests passed (20 skipped), ruff and mypy clean,
placement gate passed.
