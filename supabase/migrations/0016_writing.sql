-- Writing (specs/writing/step-2.1.md). Additive.

create table essays (
    id             uuid primary key default gen_random_uuid(),
    learner_id     uuid not null references learners (id) on delete cascade,
    prompt_id      text not null,
    text           text not null check (char_length(text) between 1 and 12000),
    consent        text not null,  -- the notice version the learner accepted, e.g. 'writing-v1'
    status         text not null default 'queued'
                   check (status in ('queued', 'analysing', 'done', 'failed')),
    result         jsonb,
    failure_vi     text,
    submitted_at   timestamptz not null default now(),
    analysed_at    timestamptz
);
create index essays_learner_idx on essays (learner_id, submitted_at desc);
create index essays_queue_idx on essays (submitted_at, id) where status = 'queued';

-- Model calls per learner, for the daily budget (services/budget.py); null for calls not made for a learner.
alter table llm_calls add column if not exists learner_id uuid references learners (id) on delete set null;
create index if not exists llm_calls_day_idx on llm_calls (created_at);
