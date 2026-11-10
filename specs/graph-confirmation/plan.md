# Plan

1. Reuse P2 durable GraphConfirmations; bind display and revision to one snapshot.
2. Supply an opaque learner session at POST /learners, storing a hash only in
   additive migration 0013. Keep RLS and startup schema validation fail-closed.
3. Mount review/confirm in the integrated factory. Run synchronous SQL off-loop.
4. Allow the two exact proxy routes; forward only the named session cookie.
   Reissue that cookie at the public origin without backend Domain attributes.
5. Test real disposable PostgreSQL: no approval on GET, stale revision, reload,
   scoped identity, forged/expired session, concurrent retry and P4 guards.
6. Audit current verifier artifacts; respect persisted cooldown, then one probe
   before any bounded live batch. Do not mark synthetic tests as live acceptance.
