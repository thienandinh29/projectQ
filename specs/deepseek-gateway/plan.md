# Plan

Reuse P3's gateway and httpx transport. Add a DeepSeek adapter using the official
chat-completions endpoint, JSON mode for schemas, and thinking disabled for
bounded generation latency. Validate returned JSON with the requested Pydantic
schema. Export secret-masked credentials and exact model IDs from P2 settings.

Use DeepSeek-only generation routes and Gemini-only verifier routes.
Extend actual generator-family tracking so fallback still selects a different
family. Test provider payload/errors, routing/fallback, verification and settings.
Run main's full API checks before a normal fast-forward push to main.

Add Gemini Developer API authentication for the supplied API key, retaining
Vertex ADC as an explicit alternative. Reuse Gemini payload/response parsing,
exclude thought parts from content and count thought tokens in output usage.
Verify header-only key transport and error redaction with mock HTTP transport.

References: https://api-docs.deepseek.com/quick_start/agent_integrations/
and https://api-docs.deepseek.com/guides/json_mode/.
