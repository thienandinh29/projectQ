"""Read/write P4 JSON artifacts. JSON files with .yaml are valid YAML 1.2."""

import json
from pathlib import Path

from pydantic import BaseModel

from app.content.models import Chunk, Graph, Item, Source, SourceSet
from app.content.pipeline import validate_items


def read_jsonl[T: BaseModel](path: Path, schema: type[T]) -> list[T]:
    return [
        schema.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[Item]) -> None:
    path.write_text("".join(row.model_dump_json() + "\n" for row in rows), encoding="utf-8")


def load_topic(path: Path) -> tuple[list[Source], list[Chunk], Graph, list[Item]]:
    source_set = SourceSet.model_validate_json((path / "sources.yaml").read_text(encoding="utf-8"))
    chunks = read_jsonl(path / "chunks.jsonl", Chunk)
    graph = Graph.model_validate_json((path / "graph.yaml").read_text(encoding="utf-8"))
    items = read_jsonl(path / "items.jsonl", Item)
    validate_items(items, chunks, source_set.sources, graph)
    return source_set.sources, chunks, graph, items
