import json

import psycopg
import pytest
from pydantic import ValidationError

from app.uploads.metadata import prepare_metadata
from app.uploads.reader import Document, Page


def test_upload_metadata_round_trip_assigns_storage_provenance() -> None:
    document = Document("", (Page(1, "Nguồn"),), True)
    metadata = prepare_metadata(
        document,
        source_uri="private/uploads/a.pdf",
        media_type="application/pdf",
        filename="a.pdf",
        body=b"pdf bytes",
    )
    assert metadata.document().source_uri == "private/uploads/a.pdf"
    assert metadata.byte_size == 9 and metadata.sha256 and len(metadata.sha256) == 64
    assert metadata.document().pages == document.pages


def test_blank_storage_uri_rejected() -> None:
    with pytest.raises(ValidationError):
        prepare_metadata(Document("", (), False), source_uri=" ", media_type="application/pdf")


def test_upload_migration_persists_metadata_and_enables_rls(database_url: str) -> None:
    metadata = prepare_metadata(
        Document("", (Page(1, "Nguồn"),), True),
        source_uri="private/uploads/test.pdf",
        media_type="application/pdf",
    )
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "insert into uploads (id, source_uri, media_type, page_count, text_ok, pages)"
            " values (%s, %s, %s, %s, %s, %s::jsonb)",
            (
                metadata.id,
                metadata.source_uri,
                metadata.media_type,
                metadata.page_count,
                metadata.text_ok,
                json.dumps([p.model_dump() for p in metadata.pages]),
            ),
        )
        row = conn.execute(
            "select source_uri, page_count from uploads where id = %s", (metadata.id,)
        ).fetchone()
        assert row == (metadata.source_uri, 1)
        conn.execute("set local role pg_read_all_data")
        # This built-in role can read tables, but does not bypass row policies.
        assert conn.execute("select count(*) from uploads").fetchone() == (0,)
        assert conn.execute(
            "select relrowsecurity from pg_class where oid = 'uploads'::regclass"
        ).fetchone() == (True,)
        conn.rollback()


def test_upload_migration_rejects_inconsistent_page_count(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "insert into uploads (source_uri, media_type, page_count, pages)"
                " values ('private/u.pdf', 'application/pdf', 2, '[]'::jsonb)"
            )
        conn.rollback()
