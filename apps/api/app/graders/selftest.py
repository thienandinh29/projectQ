"""Grader self-test: every code objective's tests must tell right from wrong (specs/code-sandbox).

For each code objective in the course files: the reference solution must pass every test and each
known-wrong solution must fail at least one. A course whose tests cannot separate them is refused.
Solutions run in the real sandbox through the runner, never in this process.

Usage, from apps/api, with a runner listening (runner/README.md):
    uv run python -m app.graders.selftest ../../data/courses --runner-url http://127.0.0.1:8090
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.curriculum.course import load_course
from app.graders.code import grade, run_request
from app.graders.runner_client import RunnerClient


@dataclass(frozen=True)
class Check:
    course: str
    objective: str
    solution: str  # "reference" or "wrong[i]"
    ok: bool
    detail: str


async def check_courses(folder: Path, client: RunnerClient) -> list[Check]:
    checks: list[Check] = []
    for path in sorted(folder.glob("*.yaml")):
        course = load_course(path)
        for o in course.objectives:
            if o.code is None:
                continue
            ref = grade(o, await client.run(run_request(o, o.code.reference)))
            checks.append(Check(course.slug, o.id, "reference", ref.correct, ref.message_vi))
            for i, wrong in enumerate(o.code.wrong):
                g = grade(o, await client.run(run_request(o, wrong)))
                checks.append(Check(course.slug, o.id, f"wrong[{i}]", not g.correct, g.message_vi))
    return checks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("courses", type=Path)
    parser.add_argument("--runner-url", default="http://127.0.0.1:8090")
    args = parser.parse_args(argv)
    client = RunnerClient(args.runner_url, os.environ.get("RUNNER_TOKEN", ""))
    checks = asyncio.run(check_courses(args.courses, client))
    for c in checks:
        print(f"{'ok  ' if c.ok else 'FAIL'} {c.course}/{c.objective} {c.solution}: {c.detail}")
    failed = [c for c in checks if not c.ok]
    print(
        f"self-test {'FAILED' if failed else 'passed'}: {len(checks)} checks, {len(failed)} failed"
    )
    return 1 if failed or not checks else 0


if __name__ == "__main__":
    sys.exit(main())
