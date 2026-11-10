# Source acquisition status

`allowlist.yaml` is a P3 proposal based on TEAM's publisher list; P1 must review it.
Wikipedia is disabled by default (`fallback_only`) and is not automatically included
to meet the research quality bar. Research requires three distinct final URLs from
at least two publishers; redirects cannot inflate that source count.

`library.yaml` lists eight acquisition candidates hosted by LibreTexts. Actual
per-book download/cache counts and failures are in `acquisition-report.json`.
P1 reviews selection and table-of-contents coverage before P2 indexes. Every page is
license-checked; ND, unknown grants and explicit LLM-ingestion restrictions are rejected.
The old OpenStax candidates are retained only in `openstax-review.yaml`.

The checked local export contains **1,255 accepted pages across all 8 books**.
The acquisition receipt still reports incomplete traversal coverage where individual
pages lacked license evidence or left the book scope; those pages were not exported.
All rows in the resulting `index.jsonl` exports passed a fresh hash/license/URL-scope
audit. This establishes usable data, not complete publisher table-of-contents coverage.

The live Biology 2e preface on 2026-11-07 was reachable through the pinned HTTPS
reader (~380 KB HTML, ~19K characters extracted). It currently states that LLM/AI
ingestion needs prior written permission. This is why no bulk acquisition/indexing
was run and why the initial OpenStax candidate list needs P1's review or replacement.
No OpenStax bulk acquisition was run. LibreTexts acquisition was subsequently run
using the separate current manifest.
Evidence: https://openstax.org/books/biology-2e/pages/preface (Citation/Attribution).
The restriction detector intentionally fails closed on that explicit text; it is not
a comprehensive license/compliance engine or a claim that all CC sources allow AI use.

After approval and source selection, from `apps/api`:

```powershell
uv run python ../../scripts/build_library.py --help
uv run python ../../scripts/build_library.py --book <approved-slug>
uv run python ../../scripts/build_library.py --jobs 2 --report ../../data/sources/acquisition-report.json
```

Raw HTML and per-page provenance JSON go to git-ignored `data/raw/library/<slug>/`.
Each report includes download/cache counts, failures and whether link discovery
exhausted its queue. A successful traversal does not prove full textbook coverage:
compare its pages against the publisher's actual table of contents before H5 handoff.
P2 indexes the approved files with P1's ingestion code; this CLI never writes the DB.

Limitations: HTML only for library crawling; no JavaScript rendering, OCR or publisher
API adapter. Uploads additionally support PDF/DOCX. DOCX page numbers count explicit
page breaks, not Word's layout-dependent rendered pagination. Parsing runs off the
event loop for linked files; a hard CPU/memory sandbox for hostile document parsing
requires P2's worker process/container limits.
