# Tasks: Cited retrieval

- [x] T1 `TeiEmbedder` (sync + async, batching, retries, validation) + `ThreadedEmbedder`, `make_embedder`
- [x] T2 `Retriever.search` / `search`: subject-scoped cosine, NFC query, iterative scan, exact re-sort
- [x] T3 Tests: fake TEI server (`httpx.MockTransport`); real pgvector with and without the HNSW index
- [x] T4a `ingest` CLI can use the TEI server (`--embedder tei`), builds the index once (`--build-index`); local model picks the GPU when PyTorch sees one
- [ ] T4b Live check on the host machine: query embedding < ~1 s (needs the TEI container running there, H2)
- [x] T5a Evaluation harness `app/rag/evaluate.py` (hit rate@k, recall@k, MRR, misses with their rank, CLI gate) + `data/eval/README.md`
- [ ] T5b Label ≥ 20 Vietnamese questions on golden topic #1 (P4's chunks, H3) in `data/eval/`, run it, report recall@5
- [ ] T6 Reranker decision at H8 from T5; `rerank.py` only if recall is weak
