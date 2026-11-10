# P2 integration

Connect existing P1 engine and P3 routers to durable P2 storage. Topic requests must
return immediately, retain mode/tier/upload input, and run P3 TopicPipeline only in
the separate claimed-job worker. Progress, source summaries and trails survive API
restarts. A job cannot claim readiness before graph/items persistence completes.

Uploads retain exact page provenance; files use a private Storage bucket and a
failed metadata insertion removes only the newly written object. Missing P4 content
generation/verification must fail explicitly. No fabricated verified content or
automatic golden fallback is allowed. Migration 0005 remains P4-owned and pending.

P2's document-index adapter accepts P1 SourceMeta/ParsedDocument and uses P1's
chunker/embedder. Repeated identical input retains chunk IDs and skips embedding;
changed text under an existing source identity fails without replacing citations.
Worker settings must forward only the supported P3 runtime environment names,
respect shell overrides and never log credentials. These helpers do not supply
P4 generation, verification, item mapping or a production pipeline factory.
