# NodeTrail v2: plan for M0 (source catalogue) and M1 (Deep Research)

Status: written 2026-11-10 after the contest. **Decided by the lead (2026-11-10):** v2 is built on the personal
branch `p1/v2`, started from `ptest2`; the source bar is "collect whatever can be collected with a recorded
licence" instead of 3 sources from 2 publishers; the HTML crawler stays as a route. **M0 is built** on `p1/v2`
(`specs/source-catalog/`), except indexing with TEI on the host.

## Why Deep Research failed, as far as the evidence shows

- The team's acquisition crawls HTML pages (mostly LibreTexts) and infers the licence from each page
  (`app/research/library.py`, `agent.detect_license`). The reports in `data/sources/*-report.json` show pages were
  downloaded (264 for general chemistry, 227 for microbiology), and the recorded failures are
  "Chưa xác định được giấy phép mở của tài liệu" on front matter, back matter and licensing pages.
- On the `mtri` branch a live Deep Research run could not reach 3 sources from 2 publishers.
- Not established: whether the team's machines were also blocked at the network level. The exact error a team member
  saw is still needed.

Conclusion used here: discovering pages and guessing licences from HTML is the fragile part. Take sources from
places that publish **structured metadata** instead.

## What was tried on 2026-11-10 (from the agent's sandbox, not the team's machines)

| Check | Result |
|---|---|
| `openstax.org`, `libretexts.org`, Wikipedia API, MIT OCW, Gutenberg | Not reachable from the sandbox (its own network policy) |
| `raw.githubusercontent.com`, `git clone` of public repositories | Reachable |
| 11 OpenStax book repositories (`openstax/osbooks-*`) | Exist (`git ls-remote`): Python, statistics (2), chemistry, physics (2), algebra, calculus, economics, psychology, microbiology, biology |
| Prototype: `osbooks-introduction-python-programming` → library folder | **Works.** 15 chapters, 384 blocks, 200 learning objectives, licence CC BY-NC-SA 4.0 read from the book's own metadata, 0 missing modules |
| The prototype's output through the project's own `app.rag.library.load_library` | **Passes.** 422 chunks, longest 1,788 characters (limit 1,800) |

Not tried: embedding and indexing the result (no TEI here), any other book, any second publisher.

## M0 — Source catalogue (structured sources, no HTML scraping)

**Goal.** A book enters the library from a source that states its own licence and chapter order, so acquisition
does not depend on scraping.

**Scope**
1. `app/sources/catalog.yaml`: one entry per book: `slug`, `publisher`, `adapter`, `repo` (or API endpoint),
   subject names (`vi`, `en`), topic keywords for matching.
2. Adapters behind one small protocol `fetch(entry, dest) -> BookFolder`:
   - `openstax_git`: shallow, blob-less, sparse clone (collection XML + `modules/*/index.cnxml`, no media);
     licence from `md:license`; chapter order from the collection; one block per section; `source_uri` pinned to
     the commit.
   - `notebook_git`: Think Python and other Green Tea Press books (reuses `app/rag/notebook.py`).
   - `mediawiki` (Wikibooks, Wikipedia as fallback only): the API returns structured text and the licence.
     **Untested here**: must be tried on a team machine.
3. Output is the existing library folder contract, unchanged (`source.json`, `document.json`; kinds stay
   `text | exercise | glossary`), plus a new sidecar `outline.json` (chapters → pages → learning objectives).
   The sidecar is additive; nothing that reads the contract today changes.
4. Licence gate in code: an allowlist of licence URLs; "ND" licences rejected; unknown licence = the book is
   refused, with the reason in the report.
5. A report per run (`data/sources/catalog-report.json`): per book the commit, licence, chapters, blocks, chunks,
   refusals.

**Done when** (each checked by a test or a recorded run)
- 3 books from 2 publishers are fetched and pass `load_library` (proposal: OpenStax Introduction to Python
  Programming, OpenStax Introductory Statistics, Think Python).
- Unit tests on fixture XML: licence mapping, ND refusal, chapter order, section blocks, a missing module is
  reported and not skipped silently.
- The same three books are indexed with TEI on the host and a retrieval smoke query returns chunks from each.

**Not in M0.** Images and figures, mathematics rendering (MathML is flattened to text for now, which loses
formulas: a known limit for physics and calculus), exercises as items.

## M1 — Deep Research on top of the catalogue ("catalogue first, web second")

**Goal.** For a topic, produce a cited source set that meets the quality bar, in under 8 minutes, on the trunk.

**Flow**
1. **Match.** Topic → candidate books by catalogue keywords and by embedding the topic against chapter titles and
   learning objectives (`outline.json`). No LLM needed for this step.
2. **Select chapters**, not whole books: the top chapters per book, capped by a chunk budget.
3. **Fetch and index** the selected chapters only (cached by commit, so a repeated topic is instant).
4. **Check the bar in code**: ≥ 3 sources from ≥ 2 publishers, licence recorded, no ND. If the catalogue cannot
   meet it, the agent adds sources from structured APIs (MediaWiki) and says which.
5. **Hand over** to the existing pipeline (graph → items → verification gate) with the retriever and the subject.
6. **Prerequisite order** starts from the books' chapter order and learning objectives; the LLM proposes edges
   only inside that frame.

**Honest failure.** If the bar is not met, the job ends with a named reason (`not_enough_publishers`,
`no_catalogue_match`, `licence_refused`) and the trail shows what was tried. It never falls back silently.

**Done when**
- Three topics (Python loops, hypothesis testing, one topic outside the catalogue) are run live on the trunk and
  recorded: sources, publishers, time, outcome. The third is expected to fail honestly or use the API route.
- A test replays a recorded run with fake adapters and asserts the bar check and the failure codes.

**Decisions (lead, 2026-11-10)**
- Source bar: collect whatever can be collected, each source with a recorded licence; report how many sources
  and publishers were found instead of failing below 3/2. The trail still says when only one source was found.
- NC licences (all three OpenStax books in the catalogue are CC BY-NC-SA 4.0): fine for study; a commercial
  release needs a per-source review.
- The HTML crawler stays as a route. Its licence rule is fixed in M0: a page that states no licence inherits the
  verified book licence (see `specs/source-catalog/spec.md`, behaviour 8).

## After M1 (order agreed in chat, not specified yet)

M2 real learning loop through the UI (no sample data) → M3 measurements (planted-error test of the verification
gate, retrieval hit rate, placement accuracy, teacher review queue) → M4 AI teacher with slides and whiteboard,
driven by the engine (ideas from OpenMAIC) → engine upgrades (fit BKT parameters, Elo item difficulty, item
analysis).
