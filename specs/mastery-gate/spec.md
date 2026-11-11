# Spec: confirmed mastery and help-weighted evidence

**Problem.** "Mastered" (what the map shows and what Sena praises) was `p_known >= 0.95` alone. With the default MCQ
parameters, three or four correct answers in a row reach it, including answers given after the tutor's hints, which
say little about independent understanding. Idea taken from OpenMAIC's proficiency gate
(`docs/research/openmaic-study.md`, section 3).

## Behaviour
1. **Confirmed mastery** = `p_known >= 0.95` **and** at least `MIN_UNAIDED_CORRECT = 2` correct answers on the
   concept given without any hint (`bkt.is_confirmed_mastery`). Both backends use it for the `mastered` flag in the
   graph view and in attempt responses, and for starting FSRS reviews.
2. **Help weakens evidence.** A correct answer after `h` hint levels is scored with a raised guess probability
   (`bkt.params_with_help`): the guess moves 30%, 60% and 85% of the way towards 1 for 1, 2 and 3+ hints; slip is
   unchanged and `slip + guess < 1` always holds.
3. **Trace.** Crossing 0.95 without enough unaided evidence is traced as `bkt.<correct>.pending_confirmation`, with the
   Vietnamese reason naming how many unaided correct answers are still needed.
4. **Hysteresis** (`was_confirmed=True` keeps mastery while `p_known >= 0.85`) is implemented in the engine but **not
   wired**: the services do not store whether mastery was confirmed, and adding that needs a migration. Next step.

## Not changed
`path.next_step` still uses the 0.95 threshold to choose what to practise; the gate changes what is called mastered
and praised, not the practice order. Parameters (2 unaided answers, the hint shares) are design choices, not fitted.
