# P1 H7 integration review — 2026-11-07

Reviewed read-only: P1/main `5245e56`, P2 `651bc7b`, P3 `acb048b`, P5 `d45cc3e`.
This is source review, not an integrated runtime acceptance result.

## Engine handoff

P3's `contract-review.md` correctly describes concept selection versus item
selection, integer-index grading, ordered placement history, one-time mastery
seeding, earlier-only misconception history, atomic attempt/mastery/review/trace
storage, and async retrieval. P2's current services do not yet implement all of
these. No P1 algorithm or shared wire shape needs changing to begin integration.

Acceptance sequence for P2/P3, with P1 reviewing the engine results:

1. Seed one P4 verified topic, concepts, ordered options and misconception slugs.
2. Complete placement: persist seeded mastery once; repeated completion must not
   overwrite mastery earned later. Preserve `item: null`, gap and trace.
3. Request next-item: select an unserved verified item near target difficulty;
   persist its trace. P1 `NextItem` has no trace field, so P3's wire response also
   omits it. A route for P5's next-step “Why?” trace is still unresolved; agree the
   exposure with P3/P5 before claiming every decision is visible. Do not silently
   change the frozen response contract.
4. Submit a wrong answer: persist objective grade, BKT, earlier-only misconception
   history, remediation and traces together. Load them through a fresh DB read.
5. Learn the prerequisite; next-step resumes the origin when ready. Submit a
   correct answer; verify mastery and an appropriate FSRS review card survive a
   fresh read. Invalid answer indexes must produce no writes.
6. Exercise worker failure/retry and client retry without duplicate attempts or
   placement reseeding. Transaction boundaries/idempotency belong to P2.
7. Run topic -> worker -> graph/items -> placement -> attempt with actual models,
   retrieval and the P4 verification gate before claiming H7.

## Library review

P3 reports 8 exported books / 1,255 pages / 17,390 schema-valid chunks; the raw
pages are git-ignored and unavailable in this checkout. That report does not
prove DB indexing, complete coverage or retrieval quality.

Two issues prevent unconditional approval of the current exports:

- `_write_p1_pair` sorts pages by URI, while ParsedDocument requires reading
  order. P3 should preserve publisher TOC order or explicitly isolate/order page
  blocks; lexical URL sorting is not evidence of reading order.
- Manifest entries omit subject overrides, so `subject_name_vi` defaults to an
  English book title and subjects are book slugs. Before bulk indexing, agree
  topic/subject routing with P3 and add Vietnamese labels through the supported
  manifest fields. Do not silently rename already-indexed subject identities.

Then P1/P3 check one HTML book and one real PDF: provenance/page preservation,
chunk-size spread and ten known-answer queries. P2 measures TEI query latency
(target ~1 s), indexes once, checks total DB budget and builds HNSW after load.
P4's >=20 Vietnamese labelled questions unlock recall@5 measurement (target 0.8).
Reranking remains conditional on that measured result.

## Placement decision for integration

Keep the existing deterministic placement and `verify=True` for H7; do not
redesign the engine during wiring. The original >=90% noisy exact-gap target
remains unmet, not waived. Existing recorded exact accuracy is 56–64% under
slip/guess noise. Any adjacent-gap metric is supplementary and needs measurement
before being quoted. Tune only after observing real end-to-end runs; no threshold
or public accuracy claim is changed here.

## Still needs runtime/data

P2: integrated persistence, worker, host and TEI. P3: real gateway/search receipt,
reader fixes and source coverage. P4: golden topic, 0005 and held-out cases.
P1: review these receipts, approve measured gates/budget and make the H8 model
and reranker decisions. No checkpoint is declared by this review.
