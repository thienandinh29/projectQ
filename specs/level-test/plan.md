# Plan: milestone tests and the level test (1.3a)

- **Items:** `app/curriculum/items.py`: `GrammarItem` (id, node, prompt, options with misconceptions, status) and
  `load_items(course, path)` with the checks of spec point 11. Data: `data/items/english-ielts.yaml`, about
  4 items per milestone and 2 per hidden node for the starter roadmap (~80), agent-written, `status: draft`.
- **Engine (pure, traced, no DB):** `app/engine/milestones.py`:
  - `milestone_state(course, p_known) -> {milestone: known | gap | open | mastered}` (spec 1, 6);
  - `milestone_outcome(answers) -> pass | pass_with_gap(node) | fail` (spec 4) with a `DecisionTrace`;
  - `checks_to_ask(course, milestone, p_known)` and `next_to_learn(...)` reusing `remediation.remediate` (spec 5);
  - `level_estimate(course, belief) -> grammar tier` and `vocab_tier(answers)` (spec 8, 9).
- **Placement on milestones:** a `Graph` of milestones only (`CourseSpec.milestone_edges()`: explicit edges and
  those implied by hidden nodes), passed to the existing Bayesian placer, which falls back to single-gap states by
  itself past `MAX_STATES`. Starter roadmap: 10 milestones, 69 states, exact.
- **IELTS range:** a small table in `app/curriculum/levels.py`, with the source named and checked by the owner
  before it is shown.
- **Service and routes** (`app/services/level_test.py`, `app/api/level_test.py`): `POST /level-test` (start),
  `POST /level-test/answers` (next question or result), `GET /roadmap` (milestones with state and traces),
  `POST /milestones/{slug}/answers` (milestone test and quick checks). State in the existing `mastery` table (hidden
  nodes) and a new `level_tests` table for the session (migration 0015, additive).
- **Gate:** run `evalkit.placement_sim` on the English roadmap; commit `evals/baselines/english-placement.json`
  and add it to the CI gate.
- **Tests:** engine functions on small graphs (pass, gap, fail, reopen), item validation, placement state count,
  routes and persistence, the simulated gate.
