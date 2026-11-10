-- NodeTrail schema v1: everything the 14-day demo sprint needs.
-- Plain Postgres + pgvector so it runs on local Docker and on Supabase unchanged.

create extension if not exists vector;

create table learners (
    id           uuid primary key default gen_random_uuid(),
    display_name text not null,
    locale       text not null default 'vi' check (locale in ('vi', 'en')),
    created_at   timestamptz not null default now()
);

create table subjects (
    id      uuid primary key default gen_random_uuid(),
    slug    text not null unique,
    name_vi text not null,
    name_en text not null
);

-- Trusted textbooks; every explanation must trace back to one of these.
create table sources (
    id         uuid primary key default gen_random_uuid(),
    subject_id uuid not null references subjects (id) on delete cascade,
    title      text not null,
    author     text,
    license    text not null,
    url        text
);

-- Embedding dimension is a placeholder until the embedding model is chosen (Day 3).
create table chunks (
    id        uuid primary key default gen_random_uuid(),
    source_id uuid not null references sources (id) on delete cascade,
    chapter   text,
    page      integer,
    content   text not null,
    embedding vector(1024)
);
create index chunks_source_idx on chunks (source_id);
create index chunks_embedding_idx on chunks using hnsw (embedding vector_cosine_ops);

create table concepts (
    id          uuid primary key default gen_random_uuid(),
    subject_id  uuid not null references subjects (id) on delete cascade,
    slug        text not null,
    name_vi     text not null,
    name_en     text not null,
    description text,
    unique (subject_id, slug)
);

-- Directed prerequisite graph: prerequisite_id must be learned before concept_id.
-- Cycle detection lives in the KG loader (Day 5); the DB only blocks self-loops and duplicates.
create table concept_edges (
    prerequisite_id uuid not null references concepts (id) on delete cascade,
    concept_id      uuid not null references concepts (id) on delete cascade,
    primary key (prerequisite_id, concept_id),
    check (prerequisite_id <> concept_id)
);
create index concept_edges_concept_idx on concept_edges (concept_id);

create table concept_sources (
    concept_id uuid not null references concepts (id) on delete cascade,
    chunk_id   uuid not null references chunks (id) on delete cascade,
    primary key (concept_id, chunk_id)
);

create table misconceptions (
    id             uuid primary key default gen_random_uuid(),
    concept_id     uuid not null references concepts (id) on delete cascade,
    description_vi text not null,
    description_en text
);

create table items (
    id         uuid primary key default gen_random_uuid(),
    concept_id uuid not null references concepts (id) on delete cascade,
    kind       text not null check (kind in ('mcq', 'code')),
    prompt     text not null,
    -- mcq: unused; code: {"starter": str, "tests": str, "timeout_s": int}
    payload    jsonb not null default '{}'::jsonb,
    difficulty real not null default 0.5 check (difficulty between 0 and 1)
);
create index items_concept_idx on items (concept_id);

-- Every wrong option points at the misconception it reveals.
create table item_options (
    id               uuid primary key default gen_random_uuid(),
    item_id          uuid not null references items (id) on delete cascade,
    label            text not null,
    is_correct       boolean not null,
    misconception_id uuid references misconceptions (id) on delete set null,
    check (not (is_correct and misconception_id is not null))
);
create index item_options_item_idx on item_options (item_id);

create table attempts (
    id               uuid primary key default gen_random_uuid(),
    learner_id       uuid not null references learners (id) on delete cascade,
    item_id          uuid not null references items (id) on delete cascade,
    answer           jsonb not null,
    is_correct       boolean not null,
    misconception_id uuid references misconceptions (id) on delete set null,
    created_at       timestamptz not null default now()
);
create index attempts_learner_idx on attempts (learner_id, created_at);

-- BKT state per learner x concept.
create table mastery (
    learner_id uuid not null references learners (id) on delete cascade,
    concept_id uuid not null references concepts (id) on delete cascade,
    p_known    real not null check (p_known between 0 and 1),
    updated_at timestamptz not null default now(),
    primary key (learner_id, concept_id)
);

create table review_cards (
    learner_id uuid not null references learners (id) on delete cascade,
    concept_id uuid not null references concepts (id) on delete cascade,
    fsrs_state jsonb not null,
    due_at     timestamptz not null,
    primary key (learner_id, concept_id)
);
create index review_cards_due_idx on review_cards (learner_id, due_at);
