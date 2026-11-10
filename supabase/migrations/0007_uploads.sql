-- P3 reserved migration (TEAM.md). P2 must merge after 0003--0006.
-- Metadata only: file bytes stay in a private Storage bucket, not Postgres.
-- No auth.uid() assumption: demo has one learner and no login; server owns access.
create table uploads (
    id             uuid primary key default gen_random_uuid(),
    source_uri     text not null check (length(btrim(source_uri)) > 0),
    filename       text,
    media_type     text not null check (media_type in (
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/html', 'text/plain', 'application/xhtml+xml'
    )),
    byte_size      bigint check (byte_size between 0 and 20000000),
    sha256         text check (sha256 ~ '^[0-9a-f]{64}$'),
    page_count     integer not null check (page_count between 0 and 200),
    text_ok        boolean not null default false,
    -- Page-numbered extracted text; source_uri is the canonical URL/private Storage URI.
    pages          jsonb not null default '[]'::jsonb
                   check (jsonb_typeof(pages) = 'array'),
    created_at     timestamptz not null default now(),
    check (jsonb_array_length(pages) = page_count)
);

alter table uploads enable row level security;
-- Deliberately no client policy. Existing server role must have BYPASSRLS or own the table.
-- Do not grant anon/authenticated SELECT; P2 serves uploads via the authenticated API.
create index uploads_created_at_idx on uploads (created_at);
