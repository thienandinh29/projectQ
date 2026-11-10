# Example library book (for P3's readers)

A book is a folder with two files; put many folders under `data/library/` and P2 indexes them with
`uv run python -m app.rag.library data/library --tei-url ... --build-index`.

- `source.json`: `SourceMeta` in `app/schemas.py` (who it is, licence; **ND licences are rejected**).
- `document.json`: `ParsedDocument`: blocks **in reading order**. Each block carries `chapter`, `section`
  (heading path), `kind` (`text` | `exercise` | `glossary`), the `text`, and where to open it: `source_uri` (page URL
  with an anchor, or the Supabase Storage path) plus `page` for PDFs.

What a reader does **not** do: split or merge text. Emit a block per heading/paragraph group as the source has it;
the chunker handles size (≤ 1800 chars), never mixes sections or pages, and keeps code indentation.
Blank blocks are fine (dropped). One exercise per block keeps exercises apart.

This sample is made up for the format; it is checked by `tests/rag/test_library.py`.
