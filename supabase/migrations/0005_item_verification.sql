-- P4 reserved migration. P2 reviews/merges after 0003 and 0004. Do not run on shared DBs.
-- Provenance IDs reference chunks.id (UUID); cross-row validation is done by the P4 gate.
alter table items
    add column chunk_ids uuid[] not null default '{}'::uuid[],
    add column status text not null default 'needs_review'
        check (status in ('needs_review', 'verified'));

-- Require at least one citation for verified rows. This does NOT replace the model gate.
alter table items add constraint items_verified_requires_chunks
    check (status <> 'verified' or cardinality(chunk_ids) > 0);

create index items_verified_concept_idx on items (concept_id) where status = 'verified';

-- Audit can be stored under existing items.payload.p4_verification by P2's service.
-- Invalidate stored status when question, key/options in payload, or citations change.
-- Option-row/chunk-content changes need service-level invalidation and hash validation
-- through learner_item; status alone is NOT sufficient for serving.
create function p4_invalidate_item_verification() returns trigger language plpgsql as $$
begin
    if new.prompt is distinct from old.prompt
       or new.concept_id is distinct from old.concept_id
       or new.chunk_ids is distinct from old.chunk_ids
       or (new.payload - 'p4_verification') is distinct from (old.payload - 'p4_verification') then
        new.status := 'needs_review';
        new.payload := new.payload - 'p4_verification';
    end if;
    return new;
end;
$$;

create trigger p4_item_content_changed before update on items
    for each row execute function p4_invalidate_item_verification();
