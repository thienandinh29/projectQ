-- P2: preserve the complete request for the independently running topic worker.
alter table topic_jobs
    add column mode text not null default 'quick' check (mode in ('quick', 'deep')),
    add column upload_id uuid references uploads(id),
    add column dropped_items integer not null default 0 check (dropped_items >= 0);
alter table topic_jobs add constraint topic_jobs_mode_tier
    check (mode <> 'deep' or tier = 'pro');
