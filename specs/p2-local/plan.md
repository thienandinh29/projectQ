# Implementation plan

Follow [TEAM.md](../../TEAM.md). Use existing psycopg and FastAPI, no new package.
Add migration 0006 independently of absent migrations 0003-0005. Do not manufacture
those migrations; P2 must review the missing files in order at integration.

Queue claim commits a running state under SKIP LOCKED; the worker is a separate
process. Updates persist snapshots for GET/SSE recovery; failed jobs retain a
Vietnamese public message and server-side error log. Fixture worker is opt-in;
default worker fails honestly until P3's pipeline is connected.

Use TEAM.md's published P2 route shapes directly while schemas.py is absent.
Do not add P3 business routes or fabricated decision-trace storage. Expose a
fixture marker in response headers, outside the published JSON shape.

Spec Kit commands/CLI are not installed in this checkout. These documents capture
specify/plan/tasks manually; CLI initialization remains a setup follow-up.
