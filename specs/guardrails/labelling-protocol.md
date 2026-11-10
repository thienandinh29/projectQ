# Labelling hour (H15–H16): one page for everyone

You label items and hints as **good** or **bad**. You do not decide whether the gate was right; you never see its verdict.

## Before you start (10 min, all together)
1. Everyone labels the same **5 shared items** alone, then compares. Argue until you read the rules the same way.
2. P4 confirms the sample was drawn at random from everything generated (seed written down), and that nobody tuned on it.

## For each record
Read the item or hint and **only the cited chunks**. Answer from those chunks, not from what you know.
Then write the defects you find (none = good):

| Defect | Say it when |
|---|---|
| `key_wrong` | the marked answer is not what the chunks support |
| `not_supported` | the chunks do not contain what is needed to answer or to say this |
| `ambiguous` | two options could be right, or none is clearly right |
| `wrong` (hint) | the hint states something the chunks contradict |
| `leaks_answer` (hint) | the hint hands over the final answer |
| `not_socratic` (hint) | it tells instead of guiding, for its level |
| `misconception_mismatch` | a wrong option is tagged with a misconception it does not show |
| `vietnamese_error` | wrong or unnatural Vietnamese that would confuse a learner |
| `other` | anything else wrong; write a note |

If unsure, mark it and write why; do not guess a clean "good". About 2 minutes per record; skip nothing silently.

## Rules
- Work alone; no looking at a neighbour's labels until you have both finished.
- Records are shuffled; you do not know the topic's generator model. Do not try to find out.
- Planted records are not in your pile (they are made on purpose). P4 hand-checks 5 of them.
- Disagreement on good / in scope / out of scope is settled by **P4 and P1 together**, written as `resolved_defects`.
  Same class, different defects: nothing to settle.

## When time is short
Order of value: (1) all generated items single-labelled, (2) 15 double-labelled for agreement, (3) hints, (4) the rest of
the double labels. Whatever is not done is reported as not done; the report prints what the sample cannot show.

## After
P4 runs `metrics.py`. If kappa < 0.6, stop: re-align on the definitions and relabel the disagreements before using the
numbers. Do not change the gate and re-measure on the same records.
