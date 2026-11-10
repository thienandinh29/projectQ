# Plan: Learning engine

Spec: `specs/engine/spec.md`. Contracts: `TEAM.md` → "Contracts" (shapes live in `app/schemas.py`,
`app/engine/trace.py`).

## Technical context
Python 3.12, Pydantic v2 for the trace model only, no new dependencies. Module layout in `apps/api/app/engine/`:

| Module | Contents |
|---|---|
| `trace.py` | `DecisionTrace`, `Evidence`, `Alternative` (done in H0–H1) |
| `graph.py` | `Graph` (frozen: slugs, parents, children, topological order); `from_contract(KnowledgeGraph)`; `ancestors`, `descendants`, `depth`; `root_cause` |
| `placement.py` | `Answer(slug, correct)`; `next_question`, `gap`; inference of known/unknown sets from answers |
| `bkt.py` / `srs.py` | add `update_traced`, `review_traced` beside the existing functions |

## Key decisions
- Default FSRS scheduling is deterministic (`make_scheduler(fuzz=False)`); explicit
  `fuzz=True` is an opt-in to randomized date spreading. Identical state, answer
  and time replay identically without mutating the supplied card state.
- **Graph in memory, not networkx:** graphs are < 100 nodes; plain dicts keep the engine dependency-free.
- **Placement inference:** correct on X ⇒ ancestors(X) known; wrong on X ⇒ descendants(X) unknown. Next question
  = the undecided concept that best halves the undecided set (binary search on the DAG); ties → deeper concept,
  then slug order (determinism).
- **Placement → BKT seed:** known → `p_known = 0.85`, unknown → `0.15`, asked items go through `bkt.update` too.
- **Vietnamese text:** `rule_vi` built from small templates in the engine (decision explanations, not UI chrome);
  numbers formatted with a decimal comma.

## Risks
Large flat graphs (no prerequisites) make placement degenerate to sampling → cap at 6 and report the lowest
`p_known` as the gap. Golden topics are deliberately different shapes to catch this early.
