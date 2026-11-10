-- Chunk provenance for citations. Notebook sources have no pages, so cite chapter + section + URL.

alter table sources add column version text;  -- e.g. upstream git commit the text was taken from

alter table chunks
    add column chunk_index integer not null,
    add column chapter_no  integer,
    add column section     text,
    add column kind        text not null default 'text' check (kind in ('text', 'exercise', 'glossary')),
    add column url         text,
    add constraint chunks_source_index_key unique (source_id, chunk_index);

-- One row per book per subject, so re-ingesting (even a newer version) updates in place.
alter table sources add constraint sources_subject_title_key unique (subject_id, title);
