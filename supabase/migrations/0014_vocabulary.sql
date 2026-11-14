-- Vocabulary practice (specs/vocabulary). Additive: word data stays in YAML; the database holds learner state only.

-- One FSRS card per learner and word. `word_key` is "<lemma>:<pos>" inside a word list.
create table vocab_cards (
    learner_id uuid not null references learners (id) on delete cascade,
    list_slug  text not null,
    word_key   text not null,
    fsrs_state jsonb not null,
    due_at     timestamptz not null,
    reviews    integer not null default 0 check (reviews >= 0),
    lapses     integer not null default 0 check (lapses >= 0),
    created_at timestamptz not null default now(),
    primary key (learner_id, list_slug, word_key)
);
create index vocab_cards_due_idx on vocab_cards (learner_id, list_slug, due_at);

-- Append-only log of answers, for later analysis (retention against what FSRS predicted, typical misspellings).
create table vocab_reviews (
    id          bigint generated always as identity primary key,
    learner_id  uuid not null references learners (id) on delete cascade,
    list_slug   text not null,
    word_key    text not null,
    item_kind   text not null check (item_kind in ('meaning', 'gapfill', 'collocation', 'wordform')),
    correct     boolean not null,
    answer      text not null check (char_length(answer) <= 100),
    due_at      timestamptz not null,  -- when FSRS scheduled the next review
    answered_at timestamptz not null default now()
);
create index vocab_reviews_learner_idx on vocab_reviews (learner_id, answered_at);
