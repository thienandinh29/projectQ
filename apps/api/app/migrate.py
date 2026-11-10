"""Apply SQL files in supabase/migrations in name order, once each.

Usage: uv run python -m app.migrate
"""

from pathlib import Path

import psycopg

from app.config import REPO_ROOT, get_settings

MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def apply_migrations(database_url: str, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Return the names of migrations applied by this call."""
    applied: list[str] = []
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "create table if not exists schema_migrations ("
            " name text primary key, applied_at timestamptz not null default now())"
        )
        done = {row[0] for row in conn.execute("select name from schema_migrations")}
        for path in sorted(migrations_dir.glob("*.sql")):
            if path.name in done:
                continue
            # Each migration runs in its own transaction so a failure leaves no half-applied file.
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8").encode())
                conn.execute("insert into schema_migrations (name) values (%s)", (path.name,))
            applied.append(path.name)
    return applied


if __name__ == "__main__":
    names = apply_migrations(get_settings().database_url)
    print("Applied:", ", ".join(names) if names else "nothing (up to date)")
