# Feature: Library ingestion (any book or upload → cited chunks)

Lane P1 (chunker, indexing command, contract); P3 writes the readers; P2 runs the indexing. Contracts: `TEAM.md` →
"Embeddings", the `chunks` columns (`source_uri`, `page`); shapes in `apps/api/app/schemas.py` (`ParsedDocument`,
`SourceMeta`). Builds on `specs/retrieval/`.

## Why
Only the Think Python notebooks could be chunked and indexed. P3's downloader and readers (HTML, PDF, DOCX, link) and
P1's chunking had no shared interface, so neither side could start, and the old chunker splits only on line breaks:
a long unbroken paragraph stayed oversized, and the embedding server truncates what is too long without a word, which
hides its tail from retrieval. The chunk shape also had no page, so a PDF citation could not open the right page.

## User stories
1. P3's reader emits one `document.json` per book (blocks in reading order) and does no splitting.
2. P2 indexes the whole library with one command, on the GPU machine.
3. A learner clicks a citation from an uploaded PDF and lands on the right page.
4. Nobody indexes a book with a NoDerivatives licence by accident.

## Functional requirements
- FR1 Contract: `DocBlock` / `ParsedDocument` (what a reader emits) and `SourceMeta` (`source.json`); unknown keys rejected.
- FR2 `chunk_document`: no chunk over `max_chars`; never mixes sections, kinds, source URIs or pages; no text lost or
  reordered; code indentation kept; NFC; blank blocks dropped; deterministic.
- FR3 `Chunk.page` stored in `chunks.page` (the column already existed); `chapter_no` may be absent (uploads).
- FR4 `app.rag.library`: every book folder (`source.json` + `document.json`) is read, validated and chunked **before**
  anything is embedded; re-running replaces a book's chunks; `--build-index` builds the vector index once at the end.
- FR5 ND licences are rejected with a message naming the book.

## Success criteria
- Property tests (random documents): no oversized chunk and no lost text; deliberately broken chunkers fail them.
- One real HTML book and one real PDF indexed end to end at H5 (P3 + P1): chunk-size spread looks sane, and a spot
  check of 10 Vietnamese questions finds the right section.

## Out of scope
The readers themselves (P3), OCR for scanned PDFs, tables and figures beyond their text, chunk overlap, removing
duplicates across books.
