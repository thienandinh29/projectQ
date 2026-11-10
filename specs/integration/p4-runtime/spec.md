# P4 runtime specification

Continue integration/p1-p5; do not merge/push or overwrite lane work.
Bind existing P3 contracts and TopicPipeline to P4 content/tutor and P2 persistence.
Keep original chunk IDs, independently verified content, durable audits, atomic
invalidation and hint-cache revocation. Reject stale or partial batches.

Acceptance: worker invokes P3/P4; retry preserves IDs; learner sees only current
verified items; edits invalidate choices/chunks; tutor emits only approved cited
Vietnamese hints; fallback metadata and blindness hold. Separate real DB/model
results from fake unit tests. Contracts: ../README.md and ../../contracts/.

Non-goals: extra queues/ORM/provider clients, file Storage, exam planning, retrieval
Q&A, fabricated credentials/reviews or manually verified demo content.
