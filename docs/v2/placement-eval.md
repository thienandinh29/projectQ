# Placement evaluation: graph walk vs Bayesian (2026-11-11)

Measured by `app/evalkit/placement_sim.py` (seeded, no DB, no LLM). Learners answer with the BKT
observation model for multiple-choice items: slip 0.10, guess 0.25. Each cell is 1,000 simulated
learners; **gap exact** is how often the located gap equals the true one, with a 95% Clopper-Pearson
interval, and `q` is the mean number of questions asked. Raw numbers: `placement-eval.json`
(reproduce with `uv run python -m app.evalkit.placement_sim --runs 1000 --out ...`).

Strategies
- `walk` — the original graph walk (`placement.py`), `walk+verify` — with its verification re-check (the previous default).
- `bayes` — posterior over knowledge states, question by information gain, stops at 90% confidence or at the budget; a concept may be asked repeatedly (each time a new item).
- `bayes-once` — the same, but each concept is asked at most once. This is what a service with a single verified item per concept can do.

Learner models: `single_gap` (one planted concept plus everything that builds on it; the criterion of `specs/engine/spec.md`) and `any_state` (a uniformly random prerequisite-closed state, so several gaps or none).

## Results: single planted gap
Cell format: gap exact % (95% interval) · mean questions.

| Graph (concepts) | Budget | walk+verify | bayes-once | bayes |
|---|---|---|---|---|
| chain-4 (4) | 6 | 63% (60–66) · 3.2q | 65% (62–68) · 4.0q | 82% (79–84) · 5.3q |
| chain-4 (4) | 10 | 64% (61–67) · 3.2q | 63% (60–66) · 4.0q | 91% (89–93) · 6.5q |
| chain-4 (4) | 20 | 60% (57–63) · 3.2q | 61% (58–64) · 4.0q | 92% (90–94) · 7.0q |
| wide-6 (6) | 6 | 61% (58–64) · 5.6q | 60% (57–63) · 6.0q | 57% (54–60) · 6.0q |
| wide-6 (6) | 10 | 57% (54–60) · 5.6q | 59% (56–62) · 6.0q | 72% (69–74) · 10.0q |
| wide-6 (6) | 20 | 61% (58–64) · 5.5q | 58% (55–61) · 6.0q | 90% (89–92) · 18.8q |
| diamond-5 (5) | 6 | 62% (59–65) · 4.0q | 60% (57–63) · 5.0q | 76% (73–79) · 5.7q |
| diamond-5 (5) | 10 | 62% (58–65) · 4.0q | 62% (59–65) · 5.0q | 89% (87–91) · 7.7q |
| diamond-5 (5) | 20 | 62% (59–65) · 4.0q | 62% (59–65) · 5.0q | 94% (92–95) · 8.7q |
| two-chains-6 (6) | 6 | 58% (55–61) · 3.1q | 61% (58–64) · 6.0q | 71% (68–74) · 6.0q |
| two-chains-6 (6) | 10 | 60% (57–63) · 3.1q | 63% (60–66) · 6.0q | 82% (79–84) · 9.4q |
| two-chains-6 (6) | 20 | 61% (58–64) · 3.2q | 63% (60–66) · 6.0q | 94% (92–95) · 12.2q |
| tree-10 (10) | 6 | 53% (50–56) · 4.0q | 53% (50–56) · 6.0q | 53% (50–56) · 6.0q |
| tree-10 (10) | 10 | 56% (53–59) · 4.2q | 59% (56–62) · 10.0q | 61% (58–64) · 9.9q |
| tree-10 (10) | 20 | 53% (50–56) · 4.3q | 59% (55–62) · 10.0q | 85% (83–87) · 17.7q |

## Results: any knowledge state

| Graph (concepts) | Budget | walk+verify | bayes-once | bayes |
|---|---|---|---|---|
| chain-4 (4) | 6 | 63% (60–66) · 3.3q | 68% (66–71) · 4.0q | 83% (80–85) · 5.2q |
| chain-4 (4) | 10 | 61% (58–64) · 3.3q | 65% (62–68) · 4.0q | 91% (89–93) · 6.2q |
| chain-4 (4) | 20 | 63% (60–66) · 3.3q | 68% (65–70) · 4.0q | 93% (91–94) · 6.8q |
| wide-6 (6) | 6 | 70% (67–73) · 5.3q | 70% (67–73) · 6.0q | 74% (71–76) · 6.0q |
| wide-6 (6) | 10 | 68% (64–70) · 5.3q | 70% (67–73) · 6.0q | 84% (81–86) · 10.0q |
| wide-6 (6) | 20 | 66% (63–69) · 5.3q | 66% (63–69) · 6.0q | 95% (93–96) · 17.3q |
| diamond-5 (5) | 6 | 61% (58–64) · 4.1q | 66% (63–69) · 5.0q | 76% (73–78) · 5.7q |
| diamond-5 (5) | 10 | 62% (59–65) · 4.1q | 64% (61–67) · 5.0q | 89% (87–91) · 7.8q |
| diamond-5 (5) | 20 | 60% (57–63) · 4.1q | 66% (63–69) · 5.0q | 95% (94–96) · 8.8q |
| two-chains-6 (6) | 6 | 49% (46–52) · 3.0q | 63% (60–66) · 6.0q | 69% (66–72) · 6.0q |
| two-chains-6 (6) | 10 | 50% (47–53) · 3.0q | 61% (58–64) · 6.0q | 82% (79–84) · 9.5q |
| two-chains-6 (6) | 20 | 47% (44–50) · 3.0q | 64% (61–67) · 6.0q | 94% (93–96) · 12.9q |
| tree-10 (10) | 6 | 37% (34–40) · 3.4q | 54% (50–57) · 6.0q | 52% (49–55) · 6.0q |
| tree-10 (10) | 10 | 37% (34–40) · 3.6q | 61% (58–64) · 10.0q | 68% (65–71) · 10.0q |
| tree-10 (10) | 20 | 35% (32–38) · 3.5q | 61% (58–64) · 10.0q | 89% (87–91) · 18.6q |

## What the numbers say
- **The 90% target of `specs/engine/spec.md` (≥ 90% within 6 questions) is still not met.** With a 6-question budget `bayes` reaches 53–82% on a single gap (previous default `walk+verify`: 53–63%).
- **The target is reachable with a larger budget.** Smallest budget at which `bayes` reaches 90% on a single gap: chain-4 10, wide-6 20, diamond-5 15, two-chains-6 15, tree-10 30 questions. Accuracy keeps rising with the budget (93–96% at 30 questions, both learner models), because every extra answer is evidence, not a verdict.
- **The gain depends on asking a concept more than once.** With one question per concept (`bayes-once`) accuracy is 53–65% at a budget of 6, close to `walk+verify`, while asking a few more questions. Repeats need extra verified items per concept, so the benefit scales with the item bank.
- **Why:** an MCQ is correct by luck 25% of the time. The walk treats one answer as a fact; the posterior does not, so a lucky guess moves it only a little and the next question corrects it.
- **Limits of this evidence:** simulated learners that follow exactly the model the placer assumes (same slip and guess), on five small graphs of 4–10 concepts, one question type. Real learners, real item quality and larger graphs can behave differently. These numbers say nothing about learning outcomes.

## Decision
`PLACEMENT_STRATEGY=bayes` is the default; `walk` stays available. `BayesPlacer` asks up to 10 questions, stops early at 90% posterior confidence, and never asks a concept more often than the verified items available for it. The services pass those counts, so on a topic with one item per concept it behaves like `bayes-once`.
