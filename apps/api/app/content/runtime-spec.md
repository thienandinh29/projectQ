# P4 runtime completion

Extend the existing integration/p1-p5 checkout, without merge/push or provider clients.
Implement adapters to P3 TopicPipeline and HTTP protocols backed by P2's connection
pool/tables and learning writes; reuse P1 chunker, placement, BKT, remediation and FSRS.
Use stable persisted chunk IDs; publish only current independent model audits.
Add an additive SQL proposal after 0007; never rewrite the historical reserved 0005.
Edits atomically invalidate questions and hint caches, preserving audit history.
Avoid network calls in unit tests. Keep actual DB/model checks distinct from mock tests.

Order: source permission/audit fixes; schema proposal; repository adapter; pipeline
ports and claimed-job handler; learning/tutor HTTP adapters; binding instructions;
focused tests; real-environment probes; current handoff and reproducible demo commands.

Missing credentials or a local DB must not become fake verified content. Remaining
P2 ownership points and unapplied migration are explicit in the handoff. The API
factory wraps the existing P2 create_app with its already-supported dependency kwargs.
