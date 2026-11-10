# Spec: source catalogue (v2, M0)

**Problem.** Deep Research and library acquisition crawled HTML pages and inferred every page's licence from
its text. Pages that print no licence (front matter, back matter, many section pages) failed with
"Chưa xác định được giấy phép mở của tài liệu", and the live run could not reach its source bar.

**Goal.** Books enter the library from sources that publish structured metadata, so the licence and the
chapter order are read, never guessed. The HTML crawler stays as a second route, with the licence rule fixed.

## Behaviour
1. A catalogue (`data/sources/catalog.yaml`) lists books: slug, adapter, publisher, repository, collection,
   Vietnamese and English names, topic keywords.
2. The `openstax_git` adapter does a sparse git checkout (collection XML, page CNXML, no media) and writes
   the existing library folder contract (`source.json`, `document.json`) plus `outline.json`
   (chapters → pages → learning objectives).
3. Licence from the collection's licence URL. ND or unknown → the book is refused with the reason.
4. A module listed in the collection but missing from the checkout fails the book; nothing is skipped silently.
5. Exercises become `exercise` blocks only when their problem has text; embedded interactive exercises
   (no text in the repository) are dropped.
6. MathML is linearised to readable text (`x̄=(a+b)/(2)`, `x^2`, `sqrt(x)`).
7. Each built folder is validated with the indexer's own `load_book`; the run writes a report.
8. **HTML crawler fix:** a page inside a book whose licence page was verified inherits the book's licence when
   the page states none. A page that states a licence keeps it; ND, AI-restricted and explicitly undeclared
   pages are still refused. Stored metadata records `license_origin` (`page` or `book`) and the export audit
   honours it.

## Done when
- Unit tests cover licences, the collection tree (units, front matter), module parsing, missing modules,
  validation through `load_book`, and the crawler's inheritance rule. **Met:** 25 new tests; full suite 1,577
  passed with ruff and mypy clean (2026-11-10).
- Three books fetched live and validated. **Met** from the agent's sandbox: Python (422 chunks), Introductory
  Statistics (2,555), Business Statistics (2,254); report in `data/sources/catalog-report.json`.
- Indexed with TEI and a retrieval smoke query per book. **Not met:** no TEI in the sandbox; run on the host.

## Not in scope
Images, MathML layout, a second publisher in the catalogue (M1 decides), Deep Research changes (M1).
