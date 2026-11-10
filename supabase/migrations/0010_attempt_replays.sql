-- Store the exact result in the same learner-locked transaction as mastery/reviews.
create table attempt_replays (
    learner_id uuid not null references learners(id) on delete cascade,
    item_id text not null,
    client_attempt_id uuid not null,
    request jsonb not null,
    response jsonb not null,
    primary key (learner_id, item_id, client_attempt_id)
);
alter table attempt_replays enable row level security;
