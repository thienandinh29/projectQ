# Tasks: vocabulary (step 1.2)

- [x] Spec, plan, tasks
- [x] Word list models, load-time checks, seed list `core-seed` (30 authored words)
- [x] Items: ids, deterministic build, learner view, grading (multiple choice and typed)
- [x] Typed grader with the baseline normaliser
- [x] Migration 0014, service (FSRS card, review log, trace), routes, mounting
- [x] Tests (unit, database, routes), the stack smoke test, MAP and plan status
- [ ] **Owner:** extend `normalise` in `app/graders/typed.py` and write its tests. Decide, and test, each of:
      curly vs straight apostrophes (`don’t`/`don't`); hyphen vs space vs joined (`well-known`, `well known`);
      trailing full stop or spaces; a leading article the learner typed ("the decision" for `decision`);
      upper case and mixed case; stray punctuation inside the word. Keep the rule that **a misspelling is wrong**.
- [ ] **Owner:** review the seed list (definitions, examples, collocations, Vietnamese glosses) and change
      `status: draft` to `reviewed`.
- [ ] **Owner:** decision-log entry: why vocabulary has no BKT and no prerequisite edges, and what FSRS does instead.
