# Licence of the `data/` directory

Unless a file says otherwise, everything under `data/` is licensed under the
**Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International** licence (CC BY-NC-SA 4.0):

- Summary: https://creativecommons.org/licenses/by-nc-sa/4.0/
- Full legal code: https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode

You may share and adapt this data for non-commercial purposes, with attribution, under the same licence.

## Why this directory is licensed separately

The source code of this repository is Apache-2.0 (see `../LICENSE`). The data is different: parts of it are
derived from textbooks that are themselves licensed CC BY-NC-SA, and ShareAlike requires derivatives to keep
that licence. Examples:

- `golden/` — chunks and items based on *Think Python* (Allen B. Downey), CC BY-NC-SA 4.0 for the text.
- `sources/catalog.yaml`, `sources/catalog-report.json` — describe OpenStax books (CC BY-NC-SA 4.0 as stated
  in each book's own metadata); the books' text is fetched on demand and is not stored here.
- `sources/*-report.json`, `sources/library.yaml` — acquisition records for LibreTexts books and others, each
  with the licence recorded for the source.
- `eval/`, `guardrails/` — question sets and labelled samples written by the NodeTrail team for evaluating
  retrieval and generation; they quote or refer to the sources above.

## Attribution

- OpenStax, Rice University: *Introduction to Python Programming*, *Introductory Statistics 2e*,
  *Introductory Business Statistics 2e* — https://openstax.org, CC BY-NC-SA 4.0.
- Allen B. Downey: *Think Python* — https://allendowney.github.io/ThinkPython/, CC BY-NC-SA 4.0 (text).
- Other books named in `sources/*.json` and `sources/library.yaml` keep the licence recorded there.

## Commercial use

Commercial use of this data is not permitted by this licence. A commercial product built on the code must use
sources whose licences allow it (for example CC BY or CC BY-SA) or obtain permission from the rights holders.
The Apache-2.0 licence of the code is not affected.
