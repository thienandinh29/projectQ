-- P2 only: independent of the pending lane-owned 0003-0005 migrations.
create table topic_jobs (
    id uuid primary key default gen_random_uuid(),
    goal_vi text not null,
    tier text not null check (tier in ('free', 'pro')),
    fixture boolean not null default false,
    status text not null default 'queued'
        check (status in ('queued','researching','indexing','graph','items','ready','failed')),
    step_vi text not null default 'Đang chờ xử lý',
    progress integer not null default 0 check (progress between 0 and 100),
    subject_slug text,
    graph_ready boolean not null default false,
    items_ready boolean not null default false,
    sources jsonb not null default '[]',
    trail jsonb not null default '[]',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index topic_jobs_queue_idx on topic_jobs (created_at, id) where status = 'queued';

create table llm_calls (
    id uuid primary key default gen_random_uuid(),
    topic_id uuid references topic_jobs(id) on delete set null,
    request_id text,
    tier text not null check (tier in ('free','pro')),
    model text not null,
    latency_ms integer not null check (latency_ms >= 0),
    cost_usd numeric not null check (cost_usd >= 0),
    success boolean not null,
    created_at timestamptz not null default now()
);
