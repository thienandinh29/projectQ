"""P4 CLI: validate, preview, generate, verify, metrics. No DB writes."""

import argparse
import asyncio
import json
from pathlib import Path

from app.content.artifacts import load_topic, read_jsonl, write_json, write_jsonl
from app.content.gateway import P3Gateway
from app.content.models import Chunk, SourceSet, validate_references
from app.content.pipeline import generate_graph, generate_items, require_model_permission
from app.guardrails.answerability import learner_item, verify_item
from app.guardrails.metrics import HumanLabel, Prediction, evaluate


async def run(args: argparse.Namespace) -> None:
    if args.command == "metrics":
        report = evaluate(
            read_jsonl(args.labels, HumanLabel), read_jsonl(args.predictions, Prediction)
        )
        write_json(args.output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    if args.command == "generate":
        source_set = SourceSet.model_validate_json(args.sources.read_text(encoding="utf-8"))
        chunks = read_jsonl(args.chunks, Chunk)
        validate_references(chunks, source_set.sources)
        gateway = P3Gateway()
        graph = await generate_graph(chunks, source_set.sources, gateway, tier=args.tier)
        items = await generate_items(
            graph, chunks, source_set.sources, gateway, count=args.count, tier=args.tier
        )
        # Only validated artifacts are saved; caller must supply an existing output directory.
        write_json(args.output / "graph.yaml", graph.model_dump(mode="json", by_alias=True))
        write_jsonl(args.output / "items.jsonl", items)
        return
    sources, chunks, graph, items = load_topic(args.topic)
    if args.command == "validate":
        print(
            json.dumps(
                {
                    "valid": True,
                    "sources": len(sources),
                    "chunks": len(chunks),
                    "concepts": len(graph.concepts),
                    "items": len(items),
                    "servable": sum(learner_item(i, chunks) is not None for i in items),
                    "human_approved": sum(i.human_review.status == "approved" for i in items),
                }
            )
        )
    elif args.command == "preview":
        visible = [payload for i in items if (payload := learner_item(i, chunks)) is not None]
        print(
            json.dumps(
                {"items": visible, "blocked": len(items) - len(visible)},
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "verify":
        require_model_permission(sources)
        gateway = P3Gateway()
        verified = [await verify_item(i, chunks, gateway, tier=args.tier) for i in items]
        write_jsonl(args.output, verified)
        print(
            json.dumps(
                {
                    "verified": sum(i.status == "verified" for i in verified),
                    "needs_review": sum(i.status == "needs_review" for i in verified),
                }
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "preview", "verify"):
        command = sub.add_parser(name)
        command.add_argument("topic", type=Path)
        if name == "verify":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--tier", choices=("free", "pro"), default="pro")
    generate = sub.add_parser("generate")
    generate.add_argument("--sources", type=Path, required=True)
    generate.add_argument("--chunks", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--count", type=int, default=15)
    generate.add_argument("--tier", choices=("free", "pro"), default="pro")
    metrics = sub.add_parser("metrics")
    metrics.add_argument("--labels", type=Path, required=True)
    metrics.add_argument("--predictions", type=Path, required=True)
    metrics.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
