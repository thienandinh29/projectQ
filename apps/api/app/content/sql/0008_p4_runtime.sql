-- ADDITIVE PROPOSAL for P2 review after 0007. Not automatically applied.
-- 0005 is immutable; this closes its option/chunk invalidation gaps.
alter table subjects add column p4_graph jsonb;
alter table sources add column p4_metadata jsonb not null default '{}'::jsonb;
alter table chunks add column p4_metadata jsonb not null default '{}'::jsonb;
alter table misconceptions add column slug text;
alter table misconceptions add constraint misconceptions_concept_slug_key unique(concept_id,slug);
alter table items add column external_id text unique;
alter table items add column p4_revision bigint not null default 0;
alter table item_options add column position integer;
with ordered as (
    select id, row_number() over(partition by item_id order by id)-1 as n from item_options
) update item_options o set position=ordered.n from ordered where o.id=ordered.id;
alter table item_options alter column position set not null;
alter table item_options add constraint item_options_position_key unique(item_id,position);
alter table item_options add constraint item_options_position_nonnegative check(position>=0);
alter table topic_jobs add column if not exists mode text not null default 'quick' check(mode in ('quick','deep'));
alter table topic_jobs add column if not exists upload_id uuid references uploads(id);

create table p4_verification_history (
    id uuid primary key default gen_random_uuid(),
    item_id uuid references items(id) on delete set null,
    external_id text,
    kind text not null check(kind in ('item','hint','invalidation')),
    at timestamptz not null default now(),
    record jsonb not null
);
alter table p4_verification_history enable row level security;
create table p4_hint_cache (
    item_id uuid not null references items(id) on delete cascade,
    learner_id uuid not null references learners(id) on delete cascade,
    cache_key text primary key,
    item_hash text not null,
    level integer not null,
    attempt jsonb not null,
    created_at timestamptz not null default now(),
    invalidated_at timestamptz
);
alter table p4_hint_cache enable row level security;
create table p4_learning_sessions (
    learner_id uuid not null references learners(id) on delete cascade,
    subject_id uuid not null references subjects(id) on delete cascade,
    placement_complete boolean not null default false,
    phase text not null default 'placement',
    pending_item uuid references items(id) on delete set null,
    remediation_origin text,
    primary key(learner_id,subject_id)
);
alter table p4_learning_sessions enable row level security;

create or replace function p4_invalidate_item_verification() returns trigger language plpgsql as $$
begin
    if new.prompt is distinct from old.prompt
       or new.concept_id is distinct from old.concept_id
       or new.kind is distinct from old.kind
       or new.difficulty is distinct from old.difficulty
       or new.external_id is distinct from old.external_id
       or new.chunk_ids is distinct from old.chunk_ids
       or (new.payload - 'p4_verification') is distinct from (old.payload - 'p4_verification') then
        new.status := 'needs_review';
        new.p4_revision := old.p4_revision + 1;
    end if;
    -- Retain old audit in payload/history; never silently delete it as 0005 did.
    if new.status='needs_review' and old.status='verified' then
        new.p4_revision := greatest(new.p4_revision,old.p4_revision+1);
    end if;
    return new;
end;
$$;
create function p4_record_item_audit() returns trigger language plpgsql as $$
begin
    if new.status='needs_review' and old.status='verified' then
        insert into p4_verification_history(item_id,external_id,kind,record)
          values(new.id,new.external_id,'invalidation',jsonb_build_object(
            'revision',new.p4_revision,'previous_audit',old.payload->'p4_verification'));
    end if;
    if new.payload->'p4_verification' is distinct from old.payload->'p4_verification'
       and new.payload->'p4_verification' is not null then
        insert into p4_verification_history(item_id,external_id,kind,record)
          values(new.id,new.external_id,'item',new.payload->'p4_verification');
    end if;
    if new.p4_revision<>old.p4_revision or new.status='needs_review' then
        update p4_hint_cache set invalidated_at=coalesce(invalidated_at,now()) where item_id=new.id;
        update topic_jobs set items_ready=false,
            status=case when status='ready' then 'failed' else status end,
            step_vi='Nội dung đã đổi; cần kiểm chứng lại'
          where subject_slug=(select s.slug from concepts c join subjects s on s.id=c.subject_id
                              where c.id=new.concept_id) and status='ready';
    end if;
    return new;
end;
$$;
create trigger p4_record_audit after update on items for each row execute function p4_record_item_audit();

create function p4_option_changed() returns trigger language plpgsql as $$
begin
    if TG_OP<>'INSERT' then
        update items set status='needs_review',p4_revision=p4_revision+1 where id=old.item_id;
    end if;
    if TG_OP<>'DELETE' then
        update items set status='needs_review',p4_revision=p4_revision+1 where id=new.item_id;
    end if;
    return null;
end;
$$;
create trigger p4_option_changed after insert or update or delete on item_options
    for each row execute function p4_option_changed();

create function p4_chunk_changed() returns trigger language plpgsql as $$
begin
    if TG_OP='DELETE' or new is distinct from old then
        update items set status='needs_review',p4_revision=p4_revision+1 where old.id=any(chunk_ids);
    end if;
    return null;
end;
$$;
create trigger p4_chunk_changed after update or delete on chunks for each row execute function p4_chunk_changed();
create function p4_source_changed() returns trigger language plpgsql as $$
begin
    if new is distinct from old then
        update items i set status='needs_review',p4_revision=p4_revision+1
          where exists(select 1 from chunks c where c.source_id=new.id and c.id=any(i.chunk_ids));
    end if;
    return null;
end;
$$;
create trigger p4_source_changed after update on sources for each row execute function p4_source_changed();
create function p4_concept_citation_changed() returns trigger language plpgsql as $$
begin
    if TG_OP<>'INSERT' then
        update items set status='needs_review',p4_revision=p4_revision+1 where concept_id=old.concept_id;
    end if;
    if TG_OP<>'DELETE' then
        update items set status='needs_review',p4_revision=p4_revision+1 where concept_id=new.concept_id;
    end if;
    return null;
end;
$$;
create trigger p4_concept_citation_changed after insert or update or delete on concept_sources
    for each row execute function p4_concept_citation_changed();
create function p4_misconception_changed() returns trigger language plpgsql as $$
begin
    update items i set status='needs_review',p4_revision=p4_revision+1
      where exists(select 1 from item_options o where o.item_id=i.id and o.misconception_id=old.id);
    return null;
end;
$$;
create trigger p4_misconception_changed after update or delete on misconceptions
    for each row execute function p4_misconception_changed();
