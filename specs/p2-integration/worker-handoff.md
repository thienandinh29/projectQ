# Worker and storage handoff

The independent worker is runnable from `apps/api`, but its production pipeline
factory remains unavailable. Do not run the following illustrative command until
P4's content/mapping handoff and the P2 factory implementation exist:

```powershell
uv run python -m app.jobs.worker --pipeline-factory app.services.content:make_pipeline
```

`app.services.content` is the pending P4 integration adapter, not an existing module.
The factory signature is `make_pipeline(database_url: str) -> TopicPipeline` and is
called once per claimed real job. It supplies real PipelinePorts and per-job gateway
context. Without a factory, real jobs fail with an explicit Vietnamese P4-unavailable
message. The fixture flag only completes explicitly marked fixture jobs, never a real
request. API requests do not run the worker inline.

P2 commits a claim before generation, then persists each progress/trail callback in
its own transaction. Queue mode, tier, goal and upload ID reconstruct the exact
TopicInput, including a null goal for upload-only requests. Source full text is never
written to snapshots. Percentages remain integer 0–100 in DB and become 0–1 at the
snapshot boundary. A pipeline failure retains previously persisted graph readiness.
`services.topics.load_upload(database_url, upload_id)` reconstructs the source URI,
MIME type and contiguous page numbers for the content adapter.

P4 still needs to supply generation, verification and a reliable association of
each generated Item to its concept before graph/item DB persistence can be finished.
P3's internal Item currently has no concept identifier; do not infer one from text.
Migration 0005 is still reserved for P4 and has not been fabricated or renumbered.

Configure `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `UPLOAD_BUCKET` on the server.
Create the bucket privately with a 20 MB object limit and PDF/DOCX MIME allowlist.
SupabaseStorage checks privacy before uploading and writes a UUID object path with
upsert disabled. It persists the same UUID in uploads metadata. A failed metadata
write deletes only that object. Linked-document metadata needs no Storage key.
No public bucket policies or client service-role keys are needed.

Interrupted claims are left nonterminal for operator inspection; automatic lease
reclaim is not implemented. Do not bulk-reset researching jobs while a worker is
still running. Storage transport errors return a sanitized 503, and file metadata
insert failures attempt object cleanup before propagating the error.

Verified locally: isolated migrated-DB tests cover pipeline ready/partial failure,
upload page roundtrip, queued deep/upload-only input, cleanup after failed metadata
insertion, and public-bucket rejection. These checks use fake content ports and HTTP
transport; they do not establish live H7, real cloud Storage or a P4 verification gate.

## P2 document indexing adapter

`app.services.indexing.index_document(database_url, metadata, document, embedder=None)`
accepts P1's `SourceMeta` and `ParsedDocument` after P3 source/license acquisition.
Call it through `asyncio.to_thread` from the future `PipelinePorts.index` adapter.
Use P3's persisted upload URI and page numbers when making document blocks; never
invent an open license for a private upload. Source naming and item/concept mapping
still require the content handoff; this helper is not a production pipeline factory.

The helper returns real persistent `PreparedChunk` IDs and exact URI/page provenance.
It uses P1's chunker and vector writer in one transaction, serializes retries with
the source upsert lock, and skips embedding for identical input. An embedding failure
rolls back source/subject/chunks. Changed text under an existing source identity is
rejected; choose a new versioned identity explicitly to avoid invalidating citations.
No source deletion or migration of old references is performed.

If no embedder is supplied, it lazily constructs P1's `make_embedder` from P2 settings,
including the TEI URL/key. Pass one shared embedder when indexing multiple sources to
reuse local model weights. For the initial CPU run, launch the worker with
`CUDA_VISIBLE_DEVICES=-1`; P1's local factory otherwise automatically chooses a GPU
when PyTorch can see one. Tests use fake vectors and do not establish B2 acceptance.

Worker startup exports supported search/provider/model settings to process environment
before importing the supplied factory. Existing process variables take precedence.
The gateway still enforces Gemini/Claude family separation; DeepSeek is unsupported
by the delivered P3 routing and cannot alone satisfy cross-family verification.
All model IDs in `.env.example` are blank until the account owner configures them.
