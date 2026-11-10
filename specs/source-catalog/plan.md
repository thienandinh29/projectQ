# Plan: source catalogue (v2, M0)

- `apps/api/app/sources/licence.py`: licence URL → name; refuse ND and unknown.
- `apps/api/app/sources/openstax.py`: pure parsers (`parse_collection`, `parse_module`), no network.
- `apps/api/app/sources/fetch.py`: catalogue model, sparse git checkout, `build_openstax`, CLI with report.
- `data/sources/catalog.yaml`: three OpenStax books (all CC BY-NC-SA 4.0).
- `apps/api/app/research/library.py`: `page_license(text, book_license)`; used by `download_book` and the
  export audit.
- Tests: `apps/api/tests/sources/`, one new test in `apps/api/tests/research/test_library.py`.

Contracts unchanged: `SourceMeta`, `ParsedDocument`, `DocBlock` kinds. `outline.json` is an additive sidecar.
Run: `uv run python -m app.sources.fetch ../../data/sources/catalog.yaml --out <dir> --report <file>`, then
index with `app.rag.library <dir> --tei-url ... --build-index` on the host.
