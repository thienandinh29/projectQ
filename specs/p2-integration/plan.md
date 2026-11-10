# Plan

Keep P3 protocols and P1 engine unchanged. Add TopicsService around the connection
pool, private Supabase object storage, and migration 0008 for queue request fields
and dropped-item count. Reconstruct TopicInput after committing a queue claim; run
TopicPipeline with short independent database transactions for every callback.
Allow a P4 adapter factory to provide the pipeline without importing test fixtures.
Return normalized probability progress while retaining integer percentages in DB.

P4 must supply generation/verification and reliable item-to-concept association
before live H7 acceptance. Do not derive an item's concept from its text or slug.

Add an index_document database adapter with a source-row lock, atomic writes,
stable IDs on retry and rejection of changed source snapshots. Forward supported
search/provider/model settings before constructing a worker factory. Verify both
with fake embeddings and isolated database tests; leave live acceptance pending.
