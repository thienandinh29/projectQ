"""Local-only P4 golden import/verification demo. No production database migrations."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql

from app.content.artifacts import load_topic, write_jsonl
from app.content.gateway import P3Gateway
from app.content.pipeline import require_model_permission
from app.content.repository import Repository
from app.db import create_pool
from app.guardrails.answerability import verify_item
from app.llm.gateway import load_routing
from app.llm.smoke import configuration
from app.migrate import apply_migrations


def local_only(url: str, *, admin: bool = False) -> None:
    parsed = urlsplit(url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Only local PostgreSQL is allowed by the demo command")
    if not admin and not parsed.path.removeprefix("/").startswith("nodetrail_test_"):
        raise ValueError("Use a dedicated nodetrail_test_* database")


def install_schema(url: str) -> None:
    local_only(url)
    apply_migrations(url)


async def run(args: argparse.Namespace) -> None:
    url = os.environ.get("DATABASE_URL", "")
    if args.command == "prepare-local":
        admin_url = os.environ.get(
            "TEST_DATABASE_ADMIN_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
        )
        local_only(admin_url, admin=True)
        name = "nodetrail_test_p4_" + uuid4().hex[:10]
        with psycopg.connect(admin_url, autocommit=True, connect_timeout=2) as conn:
            conn.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
        url = admin_url.rsplit("/", 1)[0] + "/" + name
        install_schema(url)
        print(
            json.dumps(
                {
                    "created_database_name": name,
                    "schema_applied": True,
                    "note": "Set DATABASE_URL locally; credentials are not printed.",
                }
            )
        )
        return
    if args.command == "environment":
        routes = configuration(load_routing())
        print(
            json.dumps(
                {
                    "database_url_present": bool(url),
                    "configured_routes": sum(row["model_configured"] is True for row in routes),
                    "root_env_read": False,
                    "real_calls": 0,
                }
            )
        )
        return
    local_only(url)
    sources, chunks, graph, items = load_topic(args.topic)
    with create_pool(url) as pool:
        repo = Repository(lambda: pool)
        repo.require_schema()
        subject = args.topic.name
        repo.save_material(subject, sources, chunks)
        repo.save_graph(subject, graph)
        if args.command == "verify-golden":
            require_model_permission(sources)
            gateway = P3Gateway()
            items = [await verify_item(item, chunks, gateway, tier=args.tier) for item in items]
            write_jsonl(args.output, items)
        repo.save_items(subject, items)
        with repo.transaction() as conn:
            visible = [key for key in repo.item_ids(conn, subject) if repo.current(conn, key)]
        print(
            json.dumps(
                {
                    "subject": subject,
                    "input_items": len(items),
                    "servable": len(visible),
                    "mode": "golden_import_then_gateway_verification"
                    if args.command == "verify-golden"
                    else "golden_import_without_verification",
                }
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("environment")
    sub.add_parser("prepare-local")
    for name in ("import-golden", "verify-golden"):
        command = sub.add_parser(name)
        command.add_argument("topic", type=Path)
        command.add_argument("--tier", choices=("free", "pro"), default="pro")
        if name == "verify-golden":
            command.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (psycopg.Error, ValueError, RuntimeError) as exc:
        # Deliberately no DSN, provider response or secret-bearing exception string.
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
