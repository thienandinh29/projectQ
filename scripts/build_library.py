"""Run from apps/api: uv run python ../../scripts/build_library.py --help."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))

from app.research.library import (  # noqa: E402
    Manifest,
    audit_export,
    audit_query_labels,
    download_book,
    export_library,
    load_manifest,
)
from app.research.reader import SafeReader, SourceError, load_allowlist  # noqa: E402


async def run(
    manifest: Path,
    output: Path,
    selected: list[str],
    *,
    jobs: int = 2,
    max_pages: int | None = None,
    report_path: Path | None = None,
    export_only: bool = False,
    audit_only: bool = False,
    queries: Path | None = None,
) -> int:
    books = load_manifest(manifest).books
    if selected:
        unknown = set(selected) - {book.slug for book in books}
        if unknown:
            raise ValueError("Unknown book selection: " + ", ".join(sorted(unknown)))
        books = [book for book in books if book.slug in selected]
    if not 1 <= jobs <= 4 or (max_pages is not None and not 1 <= max_pages <= 1000):
        raise ValueError("jobs must be 1..4 and max_pages must be 1..1000")
    if queries and not audit_only:
        raise ValueError("--queries requires --audit-only")
    if audit_only:
        if queries:
            if len(books) != 1:
                raise ValueError("Query audit requires exactly one --book")
            report = await asyncio.to_thread(audit_query_labels, output / books[0].slug, queries)
            result = {"generated_at": datetime.now(UTC).isoformat(), **report}
            if report_path:
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            print(
                json.dumps(
                    {
                        "queries": report["total_queries"],
                        "all_snippets_present": report["all_snippets_present"],
                    }
                )
            )
            return int(
                not report["all_snippets_present"]
                or report["expected_sections"] != report["expected_sections_confirmed"]
            )
        reports = [await asyncio.to_thread(audit_export, book, output) for book in books]
        result = {"generated_at": datetime.now(UTC).isoformat(), "books": reports}
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(json.dumps({"books": [{"book": r["book"], "status": r["status"]} for r in reports]}))
        return int(any(report["status"] != "pass" for report in reports))
    if export_only:
        reports = await asyncio.to_thread(export_library, Manifest(books=books), output)
        result = {"generated_at": datetime.now(UTC).isoformat(), "books": reports}
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        print(json.dumps(result), flush=True)
        return int(any(not report["accepted_pages"] for report in reports))
    semaphore = asyncio.Semaphore(jobs)
    reader = SafeReader(allowlist=load_allowlist())

    async def acquire(index: int) -> dict[str, object]:
        book = books[index]
        if max_pages is not None:
            book = book.model_copy(update={"max_pages": max_pages})
        async with semaphore:
            print(json.dumps({"book": book.slug, "status": "started"}), flush=True)
            try:
                report = await download_book(book, output, reader)
            except (SourceError, ValueError) as exc:
                report = {"book": book.slug, "complete": False, "error": str(exc)}
            print(json.dumps(report), flush=True)
            return report

    reports = await asyncio.gather(*(acquire(index) for index in range(len(books))))
    failed = any(not report["complete"] for report in reports)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "manifest": str(manifest),
                    "complete": not failed,
                    "books": reports,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return int(failed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download approved licensed textbooks; never index."
    )
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/sources/library.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "data/raw/library")
    parser.add_argument("--book", action="append", default=[])
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--queries", type=Path, help="P1 eval YAML; with --audit-only, checks label existence only"
    )
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Measure exported P1 chunk sizes, order, labels and provenance; no network",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Recheck local pages; export P1 source/document pairs and index.jsonl without network",
    )
    args = parser.parse_args()
    raise SystemExit(
        asyncio.run(
            run(
                args.manifest,
                args.output,
                args.book,
                jobs=args.jobs,
                max_pages=args.max_pages,
                report_path=args.report,
                export_only=args.export_only,
                audit_only=args.audit_only,
                queries=args.queries,
            )
        )
    )


if __name__ == "__main__":
    main()
