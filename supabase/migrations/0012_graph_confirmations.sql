-- Explicit learner approval is separate from verification, job readiness and mastery.
create table learner_graph_confirmations (
    learner_id uuid not null references learners(id) on delete cascade,
    subject_id uuid not null references subjects(id) on delete cascade,
    graph_revision text not null check (graph_revision ~ '^[0-9a-f]{64}$'),
    confirmed_at timestamptz not null default now(),
    primary key (learner_id, subject_id)
);
alter table learner_graph_confirmations enable row level security;

create function invalidate_learner_graph_confirmations() returns trigger language plpgsql as $$
begin
    delete from learner_graph_confirmations where subject_id = new.id;
    return new;
end;
$$;
create trigger invalidate_learner_graph_confirmations
    after update of p4_graph on subjects
    for each row when (old.p4_graph is distinct from new.p4_graph)
    execute function invalidate_learner_graph_confirmations();
