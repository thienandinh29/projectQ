# Integration checklist

- [x] Preserve P4 with a named safety stash; create integration branch.
- [x] Merge P1, P2, P3 and retain P5; restore P4.
- [x] Resolve pyproject/uv.lock conflict with combined requirements.
- [x] Adapt actual P3 task routing, Completion metadata and family policy.
- [x] Validate P4 golden exports against P1; gate P4->P3 items by current hashes.
- [x] Mount P3 routers in P2 with explicit 503 for absent backend adapters.
- [x] Align answer indices/hint inputs/upload conventions and trace null handling.
- [x] Run API offline suite and P5 contract tests; confirm DB remains inaccessible.
- [x] Export integrated OpenAPI, generate frontend types and pass lint/types/build checks.
- [x] Record handoff and restart frontend with the integrated production build.

Pending H7 dependencies: actual DB services and PipelinePorts registrations, queue mode/
upload persistence, worker TopicPipeline wiring, upload storage, source indexing, real
model/search credentials, independently verified items and human evaluation. These are
not marked complete merely because imports, route mounts and offline tests work.
