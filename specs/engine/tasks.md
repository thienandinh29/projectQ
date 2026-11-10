# Tasks: Learning engine

Window per `TEAM.md` timeline. `[x]` done. Tests in `apps/api/tests/engine/`.

## H0–H1 (contracts)
- [x] T1 `app/engine/trace.py`: `DecisionTrace` per contract; round-trip test
- [x] T2 `app/schemas.py`: KG + Items (cycle, misconception, one-correct validators), `Citation`, API bodies
- [x] T3 Migration `0003` (`halfvec(1024)`, `url` → `source_uri`, HNSW dropped) + `store.py` casts, `build_vector_index`

## H1–H3
- [x] T4 `bkt.update_traced`, `srs.review_traced` + tests (prior/posterior/slip/guess in the trace)
- [x] T5 `graph.py`: `Graph.from_contract`, ancestors/descendants/depth/topo order + tests on chain, wide, diamond
- [x] T6 `graph.root_cause` + tests (nearest weak prerequisite, ties, no weak prerequisite, alternatives listed)

## H3–H7
- [x] T7 `placement.py`: inference, `next_question`, `gap`, `seed_mastery`, `verify` (default on) + tests (stops ≤ 6, deterministic)
- [~] T8 Simulated-learner test. **Noiseless: gap located exactly, ≤ 6 questions, every planted gap on 4 shapes (met).
  With slip 0.10 / guess 0.25 noise the ≥ 90% criterion is NOT met** (seeded, 400 runs per planted gap):
  plain 43–55% exact (mean 2.5–4.7 questions), `verify` 56–64% (3.2–5.6 questions). **Decision (P1): `verify` is the
  default.** The 90% criterion stays open: relax it or move to probabilistic placement (see spec.md note)
- [~] T9 Traces on every engine output (done); migration `0004` `decision_traces` written and tested (done); P2 to review/merge
  and store them, P3 to return them from `/attempts` and `/placement/next`

## H8–H11
- [x] T10 Remediation rules on top of `root_cause`: see `specs/remediation/`

P1 H7 handoff reviewed against P3 `acb048b` and P2 `651bc7b`; acceptance sequence
and placement decision recorded in `../contracts/p1-h7-review.md`. Keep verify
enabled; T8's noisy 90% target stays unmet. T9's DB persistence remains pending.

Review fixes: duplicate fixture IDs are rejected; default FSRS scheduling is
deterministic. `tests/engine/test_learning_flow.py` covers placement seeding,
wrong diagnostic -> prerequisite remediation -> resumed target -> mastery ->
overdue review, with JSON state/trace round trips. On an integration checkout it
also runs with P3's real grader; DB/worker acceptance remains separate.
