# Plan: vocabulary

- **`app/graders/typed.py`**: `normalise(text)` and `grade_typed(answer, accepted)`. The baseline normaliser does
  Unicode NFC, case folding and whitespace collapsing only. The owner extends it, with tests, in
  `tests/graders/test_typed.py` (see tasks).
- **`app/vocabulary/wordlist.py`**: pydantic models (`Word`, `Example`, `Collocation`, `Form`, `WordList`) with the
  load-time checks; `load_wordlist(path)`.
- **`app/vocabulary/items.py`**: `item_id`/`parse_item_id`, `build_item(wordlist, word, kind, n)` returning an
  internal `Item` (with the key) and `learner_view(item)`, `grade(item, answer)`; distractors chosen by a seeded
  `random.Random(sha256(item id))`, so they are stable.
- **`supabase/migrations/0014_vocabulary.sql`** (additive): `vocab_cards (learner_id, list_slug, word_key,
  fsrs_state, due_at, reviews, lapses)` keyed by learner and word, and an append-only `vocab_reviews` log (item kind,
  correctness, the typed answer cut to 100 characters, time) for later analysis. Word data stays in YAML; the
  database holds only learner state.
- **`app/services/vocabulary.py`**: `VocabPractice(pool, lists_dir)`: `session(...)` and `answer(...)`, using
  `engine.srs` (`new_card`, `review_traced`) and `services.backend.save_trace` under a subject row per word list.
- **`app/api/vocab.py`**: `GET /vocab/session`, `POST /vocab/answers`; mounted in `create_app` (no external service
  needed), settings `vocab_dir`.
- **Data:** `data/vocabulary/core-seed.yaml`, about 24 authored words.
- **Tests:** word list validation; item determinism and no key leakage; typed grading; the FSRS schedule across
  answers (wrong → due again soon, right → later); due before new; the daily new-word limit; routes and persistence;
  the seed list loads and every word yields at least one item.
