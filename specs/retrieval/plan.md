# Plan: Cited retrieval

Spec: `specs/retrieval/spec.md`. Contracts: `TEAM.md` (linked, not copied).

## Technical context
`httpx` (promoted from dev to runtime dependency, approved by P1; already locked), psycopg pool, pgvector 0.8 with
`halfvec(1024)` (migration `0003`). Files in `apps/api/app/rag/`: `embed.py` (protocols, `TeiEmbedder`,
`ThreadedEmbedder`, `make_embedder`), `retrieve.py` (`Retriever`, `search`).

## Key decisions
- **Two protocols, one TEI class:** `Embedder` stays sync for ingestion; `AsyncEmbedder` is what the API uses, so the
  event loop is never blocked. `ThreadedEmbedder` adapts any sync embedder (local model, test fake).
- **`search` needs a pool and an embedder**, which the contract's `(query, subject, k)` omits: a `Retriever` holds them
  (built once in app startup) and keeps the contract's call shape.
- **SQL on the sync pool in a worker thread** (`db.py` is P2's and sync); no second async pool.
- **Filtered HNSW:** `set local hnsw.iterative_scan = relaxed_order` so a selective subject filter still yields `k` rows;
  a materialised CTE then re-sorts exactly. Older pgvector without the setting still works, with fewer rows possible.
- **Retries:** 429/502/503/504 and connection errors, exponential backoff, then `EmbeddingError`.
- **Settings are P2's file:** `make_embedder` takes explicit arguments; P2 adds `EMBEDDING_BACKEND`, `TEI_URL`,
  `TEI_API_KEY` to `config.py` and `.env.example`.

## Risks
`sources` has no publisher column, so `Citation.publisher` is always `None` for now. Supabase's pgvector may predate
0.8. bge-m3 truncation (server-side) silently cuts very long chunks; chunker caps at ~1800 characters.
