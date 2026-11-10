"""Structured textbook sources (v2, M0): licence and chapter order come from metadata.

Instead of crawling HTML pages and inferring each page's licence, a source adapter reads a book
from a place that publishes it in a structured form (for OpenStax, the book's git repository) and
writes the existing library folder contract (`source.json`, `document.json`) plus an
`outline.json` sidecar.

- `licence.py`  licence URL -> licence name; NoDerivatives and unknown licences are refused
- `openstax.py` pure parsers: collection XML -> chapters; module CNXML -> blocks, objectives
- `fetch.py`    CLI: sparse git checkout of each catalogue book -> library folders + a report
"""
