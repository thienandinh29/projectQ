import psycopg
import pytest

from app.migrate import apply_migrations

EXPECTED_TABLES = {
    "learners",
    "subjects",
    "sources",
    "chunks",
    "concepts",
    "concept_edges",
    "concept_sources",
    "misconceptions",
    "items",
    "item_options",
    "attempts",
    "mastery",
    "review_cards",
}


def test_all_tables_exist(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        rows = conn.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        ).fetchall()
    assert {r[0] for r in rows} >= EXPECTED_TABLES


def test_vector_extension_installed(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        row = conn.execute("select 1 from pg_extension where extname = 'vector'").fetchone()
    assert row is not None


def test_migrations_are_idempotent(database_url: str) -> None:
    assert apply_migrations(database_url) == []


def test_concept_edge_rejects_self_loop(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        subject_id = conn.execute(
            "insert into subjects (slug, name_vi, name_en)"
            " values ('t-selfloop', 'Thử', 'Test') returning id"
        ).fetchone()
        assert subject_id is not None
        concept_id = conn.execute(
            "insert into concepts (subject_id, slug, name_vi, name_en)"
            " values (%s, 'loops', 'Vòng lặp', 'Loops') returning id",
            (subject_id[0],),
        ).fetchone()
        assert concept_id is not None
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "insert into concept_edges (prerequisite_id, concept_id) values (%s, %s)",
                (concept_id[0], concept_id[0]),
            )
        conn.rollback()


def test_correct_option_cannot_have_misconception(database_url: str) -> None:
    with psycopg.connect(database_url) as conn:
        subject_id = conn.execute(
            "insert into subjects (slug, name_vi, name_en)"
            " values ('t-option', 'Thử', 'Test') returning id"
        ).fetchone()
        assert subject_id is not None
        concept_id = conn.execute(
            "insert into concepts (subject_id, slug, name_vi, name_en)"
            " values (%s, 'cond', 'Điều kiện', 'Conditions') returning id",
            (subject_id[0],),
        ).fetchone()
        assert concept_id is not None
        mis_id = conn.execute(
            "insert into misconceptions (concept_id, description_vi)"
            " values (%s, 'Nhầm = với ==') returning id",
            (concept_id[0],),
        ).fetchone()
        item_id = conn.execute(
            "insert into items (concept_id, kind, prompt) values (%s, 'mcq', 'q') returning id",
            (concept_id[0],),
        ).fetchone()
        assert mis_id is not None and item_id is not None
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "insert into item_options (item_id, label, is_correct, misconception_id,position)"
                " values (%s, 'A', true, %s,0)",
                (item_id[0], mis_id[0]),
            )
        conn.rollback()
