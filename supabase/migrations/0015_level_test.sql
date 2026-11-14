-- Milestone tests and the level test (specs/level-test). Additive. Mastery of hidden nodes stays in `mastery`.

-- The adaptive level test: answers so far and the question being asked.
create table level_tests (
    id          uuid primary key default gen_random_uuid(),
    learner_id  uuid not null references learners (id) on delete cascade,
    course      text not null,
    target      text check (target in ('A2', 'B1', 'B2', 'C1')),
    phase       text not null default 'grammar' check (phase in ('grammar', 'vocab', 'done')),
    answers     jsonb not null default '[]'::jsonb check (jsonb_typeof(answers) = 'array'),
    pending     jsonb,  -- {"part": "grammar"|"vocab", "slug": milestone or tier, "item_id": ...}
    result      jsonb,
    started_at  timestamptz not null default now(),
    finished_at timestamptz
);
create index level_tests_learner_idx on level_tests (learner_id, started_at desc);

-- Fixed sets of items: a milestone test, the quick checks after it, or practice on one hidden node.
create table grammar_runs (
    id          uuid primary key default gen_random_uuid(),
    learner_id  uuid not null references learners (id) on delete cascade,
    course      text not null,
    kind        text not null check (kind in ('milestone', 'checks', 'practice')),
    target      text not null,  -- the milestone (milestone, checks) or the hidden node (practice)
    item_ids    jsonb not null check (jsonb_typeof(item_ids) = 'array'),
    answers     jsonb not null default '[]'::jsonb check (jsonb_typeof(answers) = 'array'),
    outcome     jsonb,
    started_at  timestamptz not null default now(),
    finished_at timestamptz
);
create index grammar_runs_learner_idx on grammar_runs (learner_id, started_at desc);

-- Append-only log of graded grammar answers: unaided correct counts for the mastery gate, item exposure,
-- misconceptions for later analysis.
create table grammar_answers (
    id            bigint generated always as identity primary key,
    learner_id    uuid not null references learners (id) on delete cascade,
    course        text not null,
    node          text not null,
    item_id       text not null,
    correct       boolean not null,
    misconception text,
    context       text not null check (context in ('level', 'milestone', 'checks', 'practice')),
    answered_at   timestamptz not null default now()
);
create index grammar_answers_learner_idx on grammar_answers (learner_id, course, node);
