"""Export typed essay errors as a sheet for the owner's mapping check (specs/writing/step-2.2.md).

    uv run python -m app.writing.export_errors --learner <uuid> \\
        --out ../../data/private/writing/errors.csv

One row per error ERRANT typed. The owner fills `correct_node` with the hidden node the error
really is evidence about, or leaves it empty when no node fits; `app.evalkit.writing_map` scores
the filled sheet. The sheet quotes essay sentences, so it belongs in `data/private/` (git-ignored).
"""

import argparse
import csv
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import psycopg

from app.config import get_settings

COLUMNS = ("essay_id", "issue_id", "sentence", "text", "suggestion", "errant_type", "node",
           "correct_node", "note")  # fmt: skip


def rows(essays: Iterable[tuple[Any, dict[str, Any]]]) -> list[dict[str, str]]:
    out = []
    for essay_id, result in essays:
        for issue in (result.get("grammar") or {}).get("issues", []):
            if not issue.get("errant_type"):
                continue  # untyped errors cannot be mapped, so they are not part of the check
            out.append(
                {
                    "essay_id": str(essay_id),
                    "issue_id": str(issue["id"]),
                    "sentence": issue["sentence"],
                    "text": issue["text"],
                    "suggestion": issue["suggestion"] or "",
                    "errant_type": issue["errant_type"],
                    "node": issue["node"] or "",
                    "correct_node": "",
                    "note": "",
                }
            )
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--learner", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if "private" not in args.out.parts:
        print("refusing: the sheet quotes essays; write it under data/private/", file=sys.stderr)
        return 2
    with psycopg.connect(get_settings().database_url) as conn:
        essays = conn.execute(
            "select id, result from essays where learner_id=%s and status='done' "
            "and (result->>'version')::int >= 2 order by submitted_at",
            (args.learner,),
        ).fetchall()
    sheet = rows((e[0], e[1]) for e in essays)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sheet)
    print(f"{len(sheet)} errors from {len(essays)} essays -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
