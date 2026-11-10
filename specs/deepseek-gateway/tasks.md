# Tasks

- [x] Back up local DB and apply only migrations 0003/0004; verify idempotence.
- [x] Index one licensed Think Python chapter and check vectors/citations/retrieval.
- [x] Add DeepSeek adapter, runtime settings and generation routing.
- [x] Verify different-family checks, failure paths and provider metadata.
- [x] Support Gemini Developer API keys without assuming Vertex access.
- [x] Restrict default generation to DeepSeek and verification to Gemini.
- [x] Run full API tests, Ruff and mypy; prepare the scoped change for main.
- [x] Live generator/verifier smoke calls with owner-supplied credentials.

Live receipt: `docker/llm-live-smoke.json` records one Vietnamese synthetic MCQ,
DeepSeek generation and independent Gemini verification without passing the
generator's answer key to the verifier. This is connectivity/schema evidence;
P4 gates, graph/item acceptance and full topic generation remain separate work.
