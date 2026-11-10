# Feature: Next step (`GET /next-item`)

Lane P1 (the choice of concept); P3 serves an item of that concept; P2 supplies mastery and due reviews. Contracts:
`TEAM.md` (`GET /next-item` → `{item, reason_vi}`, `DecisionTrace` kind `next_item`). Builds on `specs/engine/` and
`specs/remediation/`. No contract change.

## Why
After placement and after each answer the learner needs the next thing to do, and the "Vì sao?" panel must say why.
Remediation covers *what to do after a wrong answer*; this covers everything else: continue, learn something new,
confirm what placement thinks is known, review what is due, or finish.

## User stories
1. After placement, I am taken to my **gap**, not asked again about what placement already found I know.
2. I finish what I started before something new appears.
3. I never get a concept whose foundations are weak: the panel shows what blocks it.
4. Mid-remediation, I come back to where I failed once the foundation improves.
5. Overdue reviews surface; a review scheduled a moment ago does not pre-empt learning.
6. When everything is mastered, the path says so.

## Rules, in priority order (first that applies wins)
| # | Kind | When | Picks |
|---|---|---|---|
| 0 | `resume` | a remediation is open and its origin is not mastered | `remediation.resume` |
| 1 | `review` | a card is overdue by more than the grace period (1 h) | the earliest due |
| 2 | `continue` | a ready concept is in progress (`0.5 ≤ p < 0.8`) | the one nearest mastery |
| 3 | `learn` | a ready concept is not yet known (`p < 0.5`) | the shallowest (textbook order) |
| 4 | `confirm` | a ready concept is probably known (`0.8 ≤ p < 0.95`) | the shallowest |
| 5 | `done` | everything is mastered | none |

*Ready* = not mastered, and every direct prerequisite is at least `WEAK_THRESHOLD` (0.5). The shallowest unmastered
concept always has mastered prerequisites, so while anything is unmastered some concept is ready.
Output: the concept, a **target difficulty** that rises with `p_known` (P3 picks an item near it), a Vietnamese reason,
and a trace listing the other candidates and the blocked concepts with what blocks them.

## Success criteria
- Property tests over random graphs and mastery: never returns a blocked concept (except `resume` / `review`), always
  returns one while anything is unmastered, and masters everything in at most n steps.
- A learner placed by `placement.seed_mastery` is sent to the gap, not to concepts placement found known.

## Out of scope
Choosing the item inside a concept (P3, using the target difficulty), Elo difficulty calibration, exam-date planning
(`/exam-plan`), capping reviews per session, fitting the thresholds to learners (tuned from the H8 runs).
