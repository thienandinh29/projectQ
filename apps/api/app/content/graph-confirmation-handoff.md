# Graph confirmation integration handoff

P4 currently accepts the existing `GraphConfirmation` callback through
`app.content.runtime.create_app(confirmation=...)`. Its exact signature is
`(learner_id: str, subject_slug: str, graph_revision: str) -> bool`.
`graph_revision` is computed by `app.content.learning.graph_revision` from the
current P4 Graph payload (SHA256 of canonical JSON). It is not item verification,
learner mastery or a job readiness flag.

Inspection of the present P2/P3 API route factories, DTOs and P5 client found no
published graph-confirmation route/DTO. P4 has not invented a competing route or
button. P2/P3/P5 must agree and wire that public operation and its durable record;
until supplied, the production callback remains absent and teaching/tutor return
409. No confirmation is granted by loading a graph or marking items verified.

The implementation used by integration must check the triple of authenticated
learner, subject/topic and current graph revision. A changed graph must require a
new confirmation; an old graph revision, another learner or another topic cannot
unlock learning. Tutor rechecks the current revision both before generating a hint
and before publication after the model await. Do not provide an unconditional True
callback for production or demonstration.

The DB tests now use an explicit per-test approval registry and confirm the actual
learner/topic/current stored revision after creating the learner. Only the tests
whose setup requires confirmed learning receive that fixture. Offline guard tests
retain unconfirmed =>409 and cover wrong learner/topic/old version for both learning
and tutor. They use simulated repository ports. The PostgreSQL-backed full API CI
for b2f8190 passed: https://github.com/thienandinh29/SenaEmpire36/actions/runs/42386105551.
P2's real application/import/verification acceptance remains pending.

End-to-end run sheet: create learner/topic, inspect source-backed graph, explicitly
confirm that version through the agreed integration, perform placement/practice,
answer, then request a verified hint. If the graph changes, return to inspection and
confirmation before further teaching. The public HTTP integration remains pending
P2/P3/P5 agreement; no external member review is claimed by this document.
