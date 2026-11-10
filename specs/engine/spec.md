# Feature: Learning engine (graph walk, root cause, traces)

Lane P1. Contracts: `TEAM.md` → "Python interfaces", "Placement", "DecisionTrace" (linked, never copied).

## Why
The judge must see NodeTrail *locate a gap* in ~6 questions and *explain why* ("Vì sao?"). Decisions come from
deterministic rules over the Knowledge Graph and BKT mastery, never from the LLM.

## User stories
1. **Placement (P1 priority).** As a learner on a fresh topic, I answer ~6 questions and the map lights up with
   what I know, and NodeTrail names my gap (`gap_slug`).
2. **Remediation.** When I answer wrong, NodeTrail sends me to the weakest prerequisite, not just "try again".
3. **Explainability.** Every step shows a Vietnamese reason: which rule fired, the probabilities, and the other
   concepts it considered and why they lost.
4. **Mastery + review.** A correct answer raises `p_known`; on mastery a review is scheduled (FSRS).

## Functional requirements
- FR1 `graph.py`: build a DAG from `KnowledgeGraph` (`app/schemas.py`); ancestors, descendants, topological order,
  depth. Cycles rejected (already enforced by the schema validator).
- FR2 `graph.root_cause(graph, mastery, failed_slug) -> (slug, DecisionTrace)`: among the failed concept's
  prerequisites (transitively, nearest first), pick the one with the lowest `p_known` below mastery; ties → the
  deeper foundation (closer to a root); no weak prerequisite → the failed concept itself. Trace kind `root_cause`,
  `alternatives` = every other candidate with `why_not_vi`.
- FR3 `placement.next_question(graph, answers) -> (slug | None, DecisionTrace)` and `placement.gap(graph, answers)`:
  start at the most advanced concept (max depth, most ancestors); correct → its ancestors are inferred known;
  wrong → ask the unknown prerequisite that splits the remaining candidates best; stop at 6 questions or when a
  concept is wrong and all of its prerequisites are known. Trace kind `placement_step`.
- FR4 Traced wrappers `bkt.update_traced` and `srs.review_traced` return `(result, DecisionTrace)`; `bkt.update`
  and `srs.review` stay unchanged.
- FR5 All functions are pure (no DB, no LLM, no clock unless `now` is passed) and deterministic.

## Success criteria
- On golden topics #1–3 (different shapes: chain, wide, diamond) a simulated learner with one planted gap is
  located within 6 questions in ≥ 90% of simulated runs (seeded, slip/guess noise).
- 100% of engine decisions carry a valid `DecisionTrace` with non-empty `rule_vi`.
- Unit tests cover shallow/deep and small/large graphs; `pytest` + `ruff` green.

## Out of scope (demo)
Elo difficulty calibration, fitted BKT parameters (defaults from the literature), exam-plan scheduling (H8–H11).

## Measured status (H3–H7, placement.py)
The success criterion above is **not yet met under noise**. Seeded simulation, slip 0.10 / guess 0.25, one planted gap
per concept: exact gap located in 43–55% of runs without verification and 56–64% with it (`verify`, now the default); noiseless runs are exact on all shapes.
Cause: one lucky MCQ guess (25%) settles whole branches by inference. Decided: `verify` is on by default. Remaining options: (1) accept
"within one concept" as the criterion, (2) probabilistic placement (per-concept BKT
posteriors, ask the highest-entropy concept; more work than the demo window allows).
