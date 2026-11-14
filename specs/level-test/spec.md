# Spec: milestone tests and the level test (step 1.3a of `docs/v2/plan-english-pack.md`)

Uses the two-layer roadmap of `specs/english-course/` (milestones with hidden nodes). Nothing here calls an LLM:
items are authored, grading is by answer key, decisions are the engine's and come with a `DecisionTrace`.

## Mastery lives on hidden nodes only
1. BKT tracks each **hidden node**. A milestone has no probability of its own: it is **passed** when every hidden
   node under it is at or above the "assumed known" level (`p ≥ 0.9`), and **mastered** when every hidden node is
   mastered under the existing gate (`p ≥ 0.95` and 2 unaided correct answers). One source of truth, no drift.

## Milestone test
2. Each milestone has a test of 3–4 multiple-choice questions spread over its hidden nodes, each hidden node at
   least once (4 questions when it has 4 or more; at least 3 otherwise, so a milestone with one hidden node asks 3
   on it), so one lucky guess cannot pass it. Corrected 14 Nov: the starter roadmap has milestones with one or two
   hidden nodes, so "each on a different hidden node" was impossible there. Every wrong option names its misconception (e.g. `since-with-past-simple`).
3. Each answer updates the BKT of the hidden node it touches.
4. Outcome:
   - **all correct → pass**: hidden nodes not yet above 0.9 are raised to 0.9 ("assumed known"), not to mastered;
   - **one wrong out of 4 → pass with a gap**: only that hidden node is opened;
   - **two or more wrong, or one wrong out of 3 → fail**: every hidden node under the milestone gets a quick check.
5. **Quick check**: 1–2 questions per opened hidden node; the weakest one becomes the next thing to learn
   (`engine.remediation`, which already walks prerequisites, now including hidden node → milestone edges). After
   practice the learner retakes the milestone test, with questions not seen last time when the bank allows.
6. **Evidence from elsewhere reopens.** Any later evidence that drops a hidden node below 0.9 (practice now, Writing
   errors from phase 2) reopens it, and its milestone shows as "cần ôn" (needs review) on the roadmap.

## Level test
7. Adaptive, over **milestones only**: Bayesian placement (`engine/placement_bayes.py`) on the milestone graph,
   where a milestone is known when all its hidden nodes are, and each question is one milestone-test item.
   Stops at 90% confidence in one knowledge state or after 20 questions, whichever comes first. A target (B2 or C1)
   chosen by the learner limits the roadmap to the milestones up to it.
8. A short vocabulary part: 3 meaning questions per CEFR tier from the word list, from A2 upwards, stopping at the
   first tier with fewer than 2 correct. It sets the vocabulary `max_level` of `specs/vocabulary/`.
9. Result, in Vietnamese, labelled as an estimate:
   - a grammar level: the highest CEFR tier whose milestones are all estimated as known;
   - a vocabulary level;
   - an indicative IELTS range for the lower of the two, from IELTS's published CEFR alignment, always with the
     words "ước lượng, không phải điểm IELTS" (an estimate, not an IELTS score);
   - the roadmap: milestones known, the frontier, and what to learn first, each with its "Vì sao?" trace.
10. Answers seed the learner's state: known milestones set their hidden nodes to 0.9; the rest stay at the prior.

## Items
11. Authored YAML next to the course (`data/items/english-ielts.yaml`), validated against the course: every
   item names an existing hidden node, has exactly one key, and a misconception on every distractor.
   Status `draft` (written by the agent) or `reviewed` (checked by the owner).
12. **Decided (owner, 14 Nov):** `draft` items are served to the owner alone while testing, labelled "Bản nháp";
   other testers only ever see `reviewed` items.
12a. **IELTS range (owner's table, 14 Nov):** B1 4.0–5.0, B2 5.5–6.5, C1 7.0–8.0 (C2 8.5–9.0), matching IELTS's
   published alignment. IELTS publishes no band for A1–A2, so those show "dưới 4.0" (below 4.0), an estimate.

## Gate (measured, from the plan)
13. Placement accuracy curve by number of questions, simulated on the English roadmap (`evalkit/placement_sim.py`,
   learners drawn from the graph): target ≥ 90% with ≤ 20 questions; the result is committed as a baseline and
   checked in CI, whatever it is. The level shown to the learner is measured too (`level_exact`). If the
   milestone graph has too many knowledge states for exact placement, the placer's own fallback (single-gap
   states) runs, and the baseline records which family ran.

## Not in scope
Generated items (1.3b), the web screens (1.4), Writing evidence (phase 2, only the reopening hook is built here).
