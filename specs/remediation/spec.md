# Feature: Remediation rules

Lane P1. Contracts: `TEAM.md` → "Python interfaces", `POST /attempts` (`remediation?: {concept_slug, reason_vi}`,
`traces`), "DecisionTrace" (linked, never copied). Builds on `graph.root_cause` (`specs/engine/`).

## Why
After a wrong answer the learner needs the *right* next step: not another question on the same concept when the
real gap is a weak foundation, and not a trip back to something they already know. This is the "adjust" step of the
loop, and the "Vì sao?" panel must show why.

## User stories
1. Wrong on a concept whose prerequisite is weak → I am sent to the weakest prerequisite, with the reason.
2. Wrong on a concept whose foundations hold → I practise it again; if I keep making the *same* mistake, I am sent to
   the explanation of that mistake instead of more drilling.
3. After I work on the prerequisite → I go to the next weak one, or back to where I failed.
4. A concept placement found known is never treated as a gap.

## Functional requirements
- FR1 `WEAK_THRESHOLD = 0.5`: a prerequisite is a gap when `p_known` is below it. Separate from `MASTERY_THRESHOLD`
  (0.95); placement marks known concepts at 0.85, so using "not mastered" would send learners back to what they know.
- FR2 `remediate(...) -> (RemediationPlan, DecisionTrace)`, rules in order: weak prerequisite → `review_prerequisite`;
  same misconception `REPEATED_MISCONCEPTION` (2) times with solid foundations → `address_misconception`; else
  `practice_again`. `plan.to_contract()` returns the API `Remediation`, or `None` for `practice_again`.
- FR3 `resume(...) -> (slug, DecisionTrace)`: next weak prerequisite of the origin, else the origin itself.
- FR4 Pure and deterministic; every decision carries a trace with a non-empty Vietnamese `rule_vi`.

## Success criteria
- Property tests over 45 graph shapes (chain, wide, diamond, deep, single node, 40 random DAGs) and random mastery:
  the target is the weakest weak ancestor or the failed concept itself; repeated failures descend strictly and stop.
- A learner placed by `placement.seed_mastery` is never sent back to a concept placement found known.

## Out of scope
Choosing the next *new* concept when nothing is failing (`/next-item` selection), fitting the thresholds to real
learners (tuned from the H8 runs), and the tutor's hint text (P4).
