# Plan: Next step

Spec: `specs/next-item/spec.md`. Pure Python in `apps/api/app/engine/path.py`; no dependency.

## Design
- `next_step(graph, mastery, *, now, resume_origin=None, due_reviews=None) -> (NextStep, DecisionTrace)`.
  `NextStep` = concept (None when done), kind, target difficulty, Vietnamese reason. The API's `reason_vi` is its reason.
- **Order of the groups matters after placement.** Placement marks known concepts at 0.85, "probably known". If those
  came first the learner would be re-asked what placement found they know, so `continue` and `learn` (the gap) come
  before `confirm`.
- **Finish what you started:** an in-progress concept (`0.5 ≤ p < 0.8`) beats a fresh one even if the fresh one is
  shallower, so a diamond-shaped graph does not make the learner hop between branches.
- **Review grace of 1 hour:** `srs.new_card` is due immediately, so a just-mastered concept would otherwise be asked
  again at once. Reviews surface when overdue, not merely due.
- **Target difficulty:** `0.2 + 0.6 · p_known` (0.32 for a new concept, 0.74 near mastery); items carry `difficulty` in
  0–1. A starting point to tune, not a fitted value.
- The trace's alternatives: the other candidates in rank order, plus up to two blocked concepts with the weak
  prerequisite that blocks each, so "Vì sao?" can say why the learner is not jumping ahead.

## Decisions
- Thresholds reuse `WEAK_THRESHOLD` (0.5) and `MASTERY_THRESHOLD` (0.95); the confirm line is 0.8, just under the 0.85
  placement gives to known concepts.
- No contract change: `NextItem` stays `{item, reason_vi}`; the concept and difficulty are internal to P3's call.

## Risks
The thresholds are untuned guesses. A learner who keeps failing one concept is handled by remediation, not here.
Nothing here limits how many reviews come in a row; P3 can cap that.
