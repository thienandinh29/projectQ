"""Checkpoint handoff guards with real SQL; verifier replies are test fixtures."""

import asyncio
import json
from pathlib import Path

from app.content.import_checkpoint import import_checkpoint
from app.content.models import item_hash
from app.content.repository import Repository
from app.db import create_pool
from app.guardrails.answerability import verify_item
from tests.content.fakes import ROOT, FakeGateway, topic


def test_import_rechecks_audit_current_content_and_retry(database_url: str, tmp_path: Path) -> None:
    sources, chunks, graph, drafts = topic()
    fake = FakeGateway()
    result = asyncio.run(verify_item(drafts[0], chunks, fake))
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "items": {
                    drafts[0].id: {
                        "fingerprint": item_hash(drafts[0], chunks),
                        "result": result.model_dump(mode="json"),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    folder = ROOT / "data/golden/python-conditions"
    with create_pool(database_url) as pool:
        repo = Repository(lambda: pool)
        repo.save_material(folder.name, sources, chunks)
        repo.save_graph(folder.name, graph)
        dry = import_checkpoint(repo, folder, checkpoint)
        assert dry == {"checkpoint_items": 1, "eligible": 1, "applied": False, "servable_in_db": 0}
        first = import_checkpoint(repo, folder, checkpoint, apply=True)
        assert first["servable_in_db"] == 1
        assert import_checkpoint(repo, folder, checkpoint, apply=True) == first
        with repo.transaction() as conn:
            assert conn.execute("select count(*) from items").fetchone() == (1,)
            conn.execute(
                "update chunks set content=content||' changed' where id=%s",
                (drafts[0].chunk_ids[0],),
            )
        stale = import_checkpoint(repo, folder, checkpoint, apply=True)
        assert stale["eligible"] == 0 and stale["servable_in_db"] == 0
        with repo.transaction() as conn:
            assert repo.servable(conn, drafts[0].id) is None


def test_verified_status_without_audit_is_not_imported(database_url: str, tmp_path: Path) -> None:
    sources, chunks, graph, drafts = topic("fractions")
    forged = drafts[0].model_copy(update={"status": "verified", "verification": None})
    checkpoint = tmp_path / "untrusted.json"
    checkpoint.write_text(
        json.dumps(
            {
                "items": {
                    forged.id: {
                        "fingerprint": item_hash(forged, chunks),
                        "result": forged.model_dump(mode="json"),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with create_pool(database_url) as pool:
        repo = Repository(lambda: pool)
        repo.save_material("fractions", sources, chunks)
        repo.save_graph("fractions", graph)
        result = import_checkpoint(repo, ROOT / "data/golden/fractions", checkpoint, apply=True)
        assert result["eligible"] == 0
