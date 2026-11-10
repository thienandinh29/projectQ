# P4 runtime plan

Use P2 create_app dependency ports and ConnectionPool; P3 PipelinePorts and actual
Completion.route metadata; P1 chunker/placement/BKT/path/remediation/FSRS.
Implement repository/ports/backends in P4-owned content paths. Minimal worker
processor hook requires P2 review. Propose additive0008 outside migration glob;
do not rewrite0005. Use same-transaction triggers/revision/hash checks for edits.

Validate mocked orchestration and guard behavior offline, type/lint checks, then
isolated real PostgreSQL tests and live gateway/Python sequence if services exist.
Missing configuration remains a named blocker. Record exact test outcomes and
human/model/agent review separately in HANDOFF and runtime-validation.json.
