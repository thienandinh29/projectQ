# Implementation plan

Follow TEAM.md lanes and P4 graph-confirmation-handoff.md. Reuse graph_revision,
Repository, existing pool/routers and Supabase storage; no dependency/engine change.

Add migration0012 with one private RLS-protected confirmation row per learner and
subject, exact revision and timestamp. A graph-update trigger removes the old row
(including A -> B -> A), without changing P4 tables or verification rules.
Serialize confirmation writes with learner -> subject row locks, matching P4.

The existing three-argument P4 callback runs inside a transaction already holding
a shared pool connection. Its persistence service uses a short independent DB
connection, preventing pool starvation when concurrent learners invoke the callback.

Port the existing P2 create_content_app and nine factory tests from ptest3 into
ptest2 without overwriting P4's files. Use durable confirmation by default; retain
explicit test callback injection. Validate both required schemas at startup and
close the platform pool on failure. Expose the service on app.state for P3 wiring.

Run focused SQL/HTTP tests then API lint/format/mypy/full pytest. Apply0012 only to
the explicitly named local dev DB after SQL checks. Rollback may select the older
entry point with confirmation denied; the additive private table can remain unused.
Spec/plan/tasks are recorded manually because slash commands are unavailable here.
