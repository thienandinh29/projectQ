-- Manual rollback for P2 only; intentionally outside supabase/migrations/*.sql.
-- Apply in a transaction and only after dependent application changes are rolled back.
drop trigger if exists p4_item_content_changed on items;
drop function if exists p4_invalidate_item_verification();
drop index if exists items_verified_concept_idx;
alter table items drop constraint if exists items_verified_requires_chunks;
alter table items drop column if exists status;
alter table items drop column if exists chunk_ids;
delete from schema_migrations where name = '0005_item_verification.sql';
