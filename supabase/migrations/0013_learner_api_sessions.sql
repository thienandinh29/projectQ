-- Browser proof of anonymous learner ownership; UUIDs/shared API keys are not identity.
create table learner_api_sessions (
    token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
    learner_id uuid not null references learners(id) on delete cascade,
    issued_at timestamptz not null default now(),
    expires_at timestamptz not null,
    check (expires_at > issued_at)
);
create index learner_api_sessions_learner_idx on learner_api_sessions(learner_id);
alter table learner_api_sessions enable row level security;
-- No public policies. Tokens are hashed; only the trusted backend accesses this table.
