# What NodeTrail can learn from OpenMAIC

Studied: `THU-MAIC/OpenMAIC` at commit `6e51916` (shallow clone, 2026-11-11), MIT licence. Code was read, not run.
Every claim below names the file it comes from; anything not named was not checked. OpenMAIC is a large, mature
project (about 43k GitHub stars, a JCST 2026 paper, ~1,250 test files); this note is about ideas worth adopting,
not a ranking.

## Correction to an earlier claim

Earlier (from the README only) we said OpenMAIC "describes no learner model". That is wrong for its project-based
learning mode. `packages/@openmaic/generation/src/pbl/operations/kernel/proficiency.ts` and
`lib/pbl/v2/types.ts` (`PBLProficiencyAssessment`) keep a learner proficiency estimate:

- one continuous score in [-1, +1] per project, updated as an exponentially weighted average (`EWMA_ALPHA = 0.2`)
  of weighted signals (`quiz_accuracy`, `submission_score`, `help_request`, `concept_confusion`,
  `self_correction`, `task_speed`, ...), each with a weight cap;
- three tiers (beginner, intermediate, advanced) with **hysteresis** (enter advanced at 0.5, leave at 0.2) and a
  **confidence gate** (no tier change below confidence 0.4, plus a minimum number of new signals), so one
  anomalous answer cannot flip the tier;
- the tier changes the instructor's guidance (`lib/pbl/v2/agents/tier-guidance.ts`).

The accurate contrast: OpenMAIC has a **coarse, heuristic, project-level** proficiency tier that steers how the
AI teaches. NodeTrail has a **per-concept, probabilistic** model over a prerequisite graph (BKT, Bayesian
placement, FSRS) that decides what to learn next, with a trace per decision. Our search for knowledge tracing,
mastery or spaced repetition in `lib/`, `app/` and `packages/` found nothing else; that search was by keyword
and is not exhaustive.

## Ideas worth adopting

### 1. A typed action language for teaching (`packages/@openmaic/dsl/src/action.ts`)
Agents never drive the UI directly; they emit typed actions: `speech`, `wb_open`, `wb_draw_text`, `spotlight`,
`laser`, and others. Actions are split into fire-and-forget (visual effects) and synchronous (wait for speech or
drawing to finish). The same actions serve live streaming and offline playback.
**For NodeTrail:** the classroom layer (M4) should be a small action language of this kind, where `show_figure`
takes our figure specs (`app/curriculum/figures.py`) and `ask` takes a verified item, so the engine can insert a
question after any action and update BKT from the answer.

### 2. Pedagogy as versioned modules ("skills", `skills/agent-runtime/*/SKILL.md`)
Teaching strategies are written as versioned instruction modules: zone of proximal development, spiral curriculum,
fact check, learning to learn, lecture style. The ZPD module has concrete rules we should copy:
- start from an independent attempt; give no hint, method or answer before the first try;
- diagnose from evidence ("you wrote X, which may mean Y"), never from a self-reported level or a single answer;
- do not let a later sentence leak the answer to an earlier question in the same turn;
- help one step at a time, then leave the learner something to do;
- a solved-after-help task is not independent evidence.
`tier-guidance.ts` adds a 4-rung **disclosure ladder** (L0 why/what, L1 how and where to look, L2 a partial step,
L3 the worked answer).
**For NodeTrail:** our hint ladder should adopt these rules. Where possible, enforce them in code rather than in
prompts: for example, a deterministic check that a hint does not contain the answer key, and BKT treating an
answer given after level-3 help as weaker evidence than an unaided answer.

### 3. Hysteresis and confidence gates on learner-state changes
OpenMAIC's tier cannot flip on one observation. NodeTrail's mastery threshold (0.95) and Sena's praise have no
such gate: one lucky streak can cross 0.95. **For NodeTrail:** require a minimum number of unaided answers and a
recent correct review before "mastered" and before Sena praises. This is a small, testable change in the engine.

### 4. An evaluation suite per behaviour (`eval/`)
Separate suites: orchestration routing (deterministic), answer-first replies (LLM judge,
`eval/orchestration/answer-content-judge.ts`), outline language (LLM judge), whiteboard layout (vision-model rubric,
`eval/whiteboard-layout/scorer.ts`), whiteboard geometry (deterministic, `eval/whiteboard-shapes/geometry-checks.ts`),
and dated baselines (`eval/sandbox-lifecycle/*-2026-10-23.json`). Two details matter:
- judge outputs are parsed strictly: a malformed answer is flagged, never coerced into pass or fail
  (`asStrictBool`);
- deterministic checks are used wherever the property is mechanically decidable, and a judge only where it is not.
**For NodeTrail:** make `evals/` first-class, one suite per behaviour (placement accuracy, retrieval hit rate,
verifier catch rate, hint leakage, judge agreement), each writing a dated JSON baseline that CI compares against.
Our placement simulation already produces such a file.

### 5. Targeted fact checking (`skills/agent-runtime/fact-check/SKILL.md`)
Instead of checking everything, shortlist high-risk claims (exact numbers, dates, names, formulas, absolute words
such as "always" or "only", contradictions between pages) and verify only those, with a source read in full, not a
search snippet. **For NodeTrail:** this complements the blind verifier: run a cheap claim-shortlist pass on
explanations and hints, and send only those claims to source checking.

### 6. Engineering habits
- Retries with jitter, a delay ceiling, and an explicit retryable/non-retryable status split
  (`packages/@openmaic/generation/src/generation-retry.ts`).
- JSON repair and validation around every model output (`json-repair.ts`, `packages/@openmaic/dsl/src/validate.ts`).
- Review rules for coding agents with a severity scale and "provider neutrality" and "owner scoping" as explicit
  focus areas (`AGENTS.md`).

## Where we deliberately differ

- **Speed as a signal.** OpenMAIC's proficiency uses `task_speed` as a weighted signal. NodeTrail's principle is to
  reward understanding, never speed, so we would not adopt that signal for praise. Speed could still be logged for
  research.
- **Who decides.** In OpenMAIC an LLM agent orchestrates the class within skill instructions. In NodeTrail the
  engine decides the next step and the LLM explains; the classroom layer should keep that split.
- **Judging.** OpenMAIC grades quizzes with AI. NodeTrail grades deterministically where it can (keys, tests,
  values computed from figure data) and calibrates any LLM judge against human grades before trusting it.

## Proposed changes, in order of value per effort

1. Mastery gate with hysteresis and minimum unaided evidence (engine change, small, testable).
2. Hint rules from the ZPD module, plus a deterministic "hint leaks the answer" check.
3. `evals/` with dated baselines and CI comparison (placement first, since it exists).
4. Claim-shortlist fact check for explanations and hints.
5. The action language for the classroom layer (M4), using our figure specs.
