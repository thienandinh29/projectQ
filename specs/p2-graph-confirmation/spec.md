# P2 durable graph confirmation

P4 requires a trusted confirmation for learner + subject + exact graph revision.
Persist this learner action independently from content audits and mastery. A new
or reverted graph requires confirmation again. Loading a graph never approves it.

P2 delivers an additive private migration, synchronous persistence service and
factory wiring to P4 learning/tutor, using existing P2 queue/private uploads.
No public DTO or route is changed: P1/P3 own the pending HTTP contract and P5 UI.

Acceptance: confirmations survive process/pool recreation, scope cannot cross
learner/topic/revision, stale acceptance writes nothing, graph updates invalidate
old acceptance, concurrent retries create one record, and no confirmation bypasses
item verification. Real SQL and fake-model HTTP integration must cover these.
The service is called only after a trusted boundary authenticates the learner and
records an explicit action on the exact displayed graph; a UUID is not identity.
