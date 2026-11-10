# Plan: Remediation rules

Spec: `specs/remediation/spec.md`. No new dependency; pure Python in `apps/api/app/engine/`.

## Design
- `graph.py`: add `WEAK_THRESHOLD`; `root_cause` uses it by default (**bug fix**: it used the mastery threshold, which
  sent a learner placed as "known" at 0.85 back to a concept they know).
- `remediation.py`: `RemediationPlan` (frozen), `remediate`, `resume`. `remediate` calls `root_cause` and re-labels its
  trace (`remediation.*` rule ids, same kind `root_cause`); `resume` uses kind `next_item` and clears the evidence.
- The misconception count is `earlier_misconceptions.count(misconception) + 1`. The engine only compares the strings,
  so slugs or database ids both work if the same kind is used for both arguments.

## Decisions
- Prerequisite beats misconception: a weak foundation explains a repeated mistake better than a re-read does.
- Two repeats, not three: a demo learner makes few attempts; tune at H8 from real runs.
- No contract change: `Remediation` stays `{concept_slug, reason_vi}`; `practice_again` returns no remediation.

## Risks
`misconceptions` has no `slug` column, so traces would carry database ids unless P4's `0005` adds one
(`review.md` #21). Thresholds (0.5, 2 repeats) are untuned guesses.
