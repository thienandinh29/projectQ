# P2 local integration foundation

Source of contracts and ownership: [TEAM.md](../../TEAM.md), API and Git workflow.

Provide P2-owned learner creation, topic status/cached endpoints and SSE, database
queue, a standalone worker, learning-state persistence and local request logging.
Keep engines pure. Never call an LLM outside P3's gateway. Fixture execution must
be explicit and must not imply a real topic was researched.

Acceptance: isolated database tests prove competing claims cannot select the same
job, failures are persisted, status survives reconnect, heartbeat is 15 seconds,
and learning-state writes roll back together. No keys or model required.

Dependencies: P1 schemas and decision_traces migration 0004; P3 pipeline/gateway;
P4 golden content. Do not invent these contracts or overwrite other lanes.
