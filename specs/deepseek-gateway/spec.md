# DeepSeek generation through the shared gateway

P1/P3 approval and publishing to main were explicitly confirmed by P2 in this
session. Add DeepSeek as a generator without changing the different-family
verification rule. Preserve the delivered P3 gateway's schema validation,
bounded fallback and sanitized telemetry. Never relabel DeepSeek as Gemini/Claude.

Acceptance: DeepSeek generates validated Vietnamese JSON through the gateway;
Gemini remains the configured verifier family. Missing keys, malformed or
truncated output and missing verifiers fail explicitly. Offline tests must not
call paid services. A live call requires the owner's configured credentials.

Scope includes the existing standalone P3 LLM module needed on main, P2 runtime
settings, local TEI deployment and the completed chapter indexing receipt.
The broader ptest2 API/worker/frontend integration is not part of this change.

Final deployment choice: DeepSeek-only generation and Gemini-only verification.
Support the supplied Gemini Developer API key directly; do not silently send it
to Vertex or claim Vertex billing/credit eligibility. Vertex ADC remains an
explicit alternative for Gemini verification. No other-family generation fallback.
