-- 0003 (P1): half-precision vectors and source_uri, before bulk indexing (TEAM.md, "Data").
-- halfvec halves vector storage (1024 x 2 bytes), so ~30k chunks fit the Supabase free tier.
-- Not additive by design (the one exception): type change, rename, index drop.
-- Needs pgvector >= 0.7 (halfvec). Supabase and pgvector/pgvector:pg16 both ship it.

-- The HNSW index is NOT recreated here: building it row by row during bulk loading is slow and
-- bloats the index. `app.rag.store.build_vector_index` builds it once loading has finished.
drop index if exists chunks_embedding_idx;

alter table chunks
    alter column embedding type halfvec(1024) using embedding::halfvec(1024);

-- Every chunk points at its original: a web URL, or the Supabase Storage path of an upload.
alter table chunks rename column url to source_uri;
