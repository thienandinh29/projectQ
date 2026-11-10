# Plan: Library ingestion

Spec: `specs/library/spec.md`. No new dependency. Files in `apps/api/app/rag/`: `chunker.py`, `library.py`;
`ingest.py` shares its embedder arguments; `store.py` writes `page`.

## Design
- **Readers emit blocks, not chunks.** A block is a passage with its place (chapter, section path, kind, `source_uri`,
  `page`). Chunk size and boundaries live in one place, so every source is chunked alike and P3 never sees a limit.
- **Split coarse to fine:** paragraph, line, sentence, word, and a hard cut only for an unbroken run (a long URL).
  Blank-line splitting does not eat the next line's indentation, so code keeps its shape.
- **A chunk never crosses a page or section:** the citation must open the right place. That costs a few short chunks at
  page ends; accepted.
- **Validate everything, then embed:** a bad licence or empty document stops the run before any embedding work, never
  leaving a half-indexed library. One book per folder; the folder name appears in error messages.
- **Characters, not tokens:** `MAX_CHARS` (1800), as the notebook chunker already does; bge-m3 takes far more tokens, so
  this is for retrieval quality, not a hard limit.

## Decisions
- `Chunk.chapter_no` becomes optional and `Chunk.page` is added (defaults keep `notebook.py` unchanged); `SourceInfo`
  author and url may be absent (uploads).
- `notebook.py` keeps its own packer for now; unifying it with `chunker.py` is a tidy-up, not needed for the demo.

## Risks
Scanned PDFs yield no text (P3 checks on upload). No overlap between chunks, so a fact on a boundary can split: the
heading context in the embedded text and `k = 5` soften it; measure with the retrieval evaluation. Two books with the
same text give duplicate hits.
