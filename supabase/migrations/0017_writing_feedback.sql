-- Writing step 2.4a (specs/writing/step-2.4.md): what each model call cost, and the learner's
-- self-corrections after a hint. Additive only.

alter table llm_calls
    add column task text,
    add column input_tokens integer check (input_tokens >= 0),
    add column output_tokens integer check (output_tokens >= 0);

-- One row per error the learner tries to correct themselves (hint first, answer after 2 tries).
create table essay_corrections (
    essay_id uuid not null references essays(id) on delete cascade,
    issue_id integer not null check (issue_id >= 0),
    learner_id uuid not null references learners(id) on delete cascade,
    tries integer not null default 0 check (tries between 0 and 2),
    accepted boolean not null default false,
    answer_shown boolean not null default false,
    last_sentence text check (char_length(last_sentence) <= 1000),
    updated_at timestamptz not null default now(),
    primary key (essay_id, issue_id)
);
create index essay_corrections_learner on essay_corrections (learner_id);
