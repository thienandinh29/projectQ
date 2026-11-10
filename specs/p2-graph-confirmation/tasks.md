# Tasks

- [x] Add migration0012, private storage and graph-update invalidation.
- [x] Implement current snapshot, explicit stale-checked confirmation and callback.
- [x] Port P2 factory/private uploads and default durable confirmation into ptest2.
- [x] Verify real SQL scoping/restart/invalidation/retry and HTTP learning gates.
- [x] Run required checks and document P1/P3/P5 contract/UI handoff.
- [x] Apply reviewed additive migration to local dev and restart the P2 factory.

Public confirmation route/DTO and web action remain P1/P3/P5 work, not silently
invented by the P2 database layer. Real verifier acceptance remains P4/P3 work.
