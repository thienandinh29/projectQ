# Feature: Cited retrieval

Lane P1. Contracts: `TEAM.md` → "Embeddings", "Python interfaces" (`Embedder`, `retrieve.search`); the `Citation` shape
is in `apps/api/app/schemas.py`.

## Why
Every explanation, tutor hint and generated item must trace to a source chunk ("no citation, no fact"). Retrieval turns
a Vietnamese question into the best-matching English textbook chunks, each carrying what the web app needs to show the
source and open the original page.

## User stories
1. As the tutor (P4) and `/ask` (P3), I pass a question and a subject and get ranked, cited chunks.
2. As a learner, I click a citation and land on the original page (`source_uri`, plus `page` for an uploaded PDF).
3. As P2, I run bulk indexing and the API against the same TEI server through one client.

## Functional requirements
- FR1 `TeiEmbedder`: sync (`embed`, bulk indexing) and async (`aembed`, API and worker) over TEI `POST /embed`; batches,
  retries busy answers (429/502/503/504) with backoff, rejects wrong counts or dimensions, sends NFC-normalised text.
- FR2 `Retriever.search(query, subject, k=5) -> list[Citation]`, cosine similarity, scoped to one subject, ranked.
- FR3 Unknown subject → empty list. Empty query or `k` outside 1–50 → `ValueError`.
- FR4 Works with and without the HNSW index; a subject filter must still return `k` rows (pgvector iterative scan).
- FR5 `EMBEDDING_BACKEND`: `tei` (default) or `local`; a managed API is out of scope (needs a re-index).

## Success criteria
- Exact text retrieves itself at similarity ≈ 1.0; results never cross subjects; `pytest` + `ruff` green, no network.
- On golden topic #1 (P4, H3), recall@5 of the cited chunk ≥ 0.8 on its Vietnamese questions (measured, then reported).
- Query embedding on the VM < ~1 s (P2's H3 acceptance).

## Out of scope (until measured)
Reranker (`rerank.py`, decided at H8), hybrid keyword search, per-source filters.
