"""Import current verified checkpoint items into an existing local topic."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from app.config import get_settings
from app.content.artifacts import load_topic
from app.content.learning import graph_revision
from app.content.models import Item, item_hash
from app.content.repository import ContentUnavailable, Repository
from app.db import create_pool
from app.guardrails.answerability import is_currently_verified


def import_checkpoint(
    repo: Repository, topic: Path, checkpoint: Path, *, apply: bool = False
) -> dict[str, int | bool]:
    """Keep the existing graph/material; never infer trust from stored status alone."""
    _, authored_chunks, graph, drafts = load_topic(topic)
    state = json.loads(checkpoint.read_text(encoding="utf-8"))
    records = state.get("items", {})
    if not isinstance(records, dict):
        raise ValueError("Invalid checkpoint items")
    with repo.transaction() as conn:
        current_graph = repo.graph(conn, topic.name)
        if graph_revision(current_graph) != graph_revision(graph):
            raise ContentUnavailable("Topic graph differs from checkpoint topic")
        _, current_chunks = repo.material(conn, [chunk.chunk_id for chunk in authored_chunks])
    selected = []
    for draft in drafts:
        record = records.get(draft.id)
        if not record:
            continue
        result = Item.model_validate(record["result"])
        expected = item_hash(draft, current_chunks)
        if (
            record.get("fingerprint") == expected
            and item_hash(result, current_chunks) == expected
            and is_currently_verified(result, current_chunks)
        ):
            selected.append(result)
    if apply and selected:
        repo.save_items(topic.name, selected)
    with repo.transaction() as conn:
        visible = sum(repo.servable(conn, item.id) is not None for item in selected)
    return {
        "checkpoint_items": len(records),
        "eligible": len(selected),
        "applied": apply,
        "servable_in_db": visible,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("topic", type=Path)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--apply", action="store_true", help="Write eligible items; default is dry-run"
    )
    args = parser.parse_args()
    url = get_settings().database_url
    if urlsplit(url).hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Only local PostgreSQL is supported")
    with create_pool(url) as pool:
        repo = Repository(lambda: pool)
        repo.require_schema()
        print(json.dumps(import_checkpoint(repo, args.topic, args.checkpoint, apply=args.apply)))


if __name__ == "__main__":
    main()
