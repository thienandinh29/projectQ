"""Check a course file and show its concept graph by level (specs/english-course).

Reports every problem at once, so a hand-written graph can be fixed in one pass:

    uv run python -m app.curriculum.check ../../data/courses/english-ielts.yaml
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import ValidationError

from app.curriculum.course import LEVELS, Concept, CourseSpec, level_inversions
from app.engine.graph import Graph


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    order: list[Concept] = field(default_factory=list)  # learning order, when the graph is valid

    @property
    def ok(self) -> bool:
        return not self.problems


def _concepts(raw: dict[str, Any], report: Report) -> list[Concept]:
    concepts = []
    for i, item in enumerate(raw.get("concepts") or []):
        try:
            concepts.append(Concept.model_validate(item))
        except ValidationError as exc:
            where = item.get("slug", f"#{i + 1}") if isinstance(item, dict) else f"#{i + 1}"
            for err in exc.errors():
                loc = ".".join(str(x) for x in err["loc"])
                report.problems.append(f"concept {where}: {loc}: {err['msg']}")
    return concepts


def check_course(path: Path) -> Report:
    report = Report()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        report.problems.append(f"cannot read {path}: {exc}")
        return report
    if not isinstance(raw, dict):
        report.problems.append("the file is not a YAML mapping")
        return report
    concepts = _concepts(raw, report)
    slugs = [c.slug for c in concepts]
    seen: set[str] = set()
    for s in slugs:
        if s in seen:
            report.problems.append(f"duplicate concept slug {s}")
        seen.add(s)
    edges = []
    for c in concepts:
        for p in c.prerequisites:
            if p in seen:
                edges.append((p, c.slug))
            else:
                report.problems.append(f"concept {c.slug}: unknown prerequisite {p}")
    report.problems.extend(level_inversions(tuple(concepts)))
    by_slug = {c.slug: c for c in concepts}
    try:
        graph = Graph.from_edges(sorted(seen), edges)
        report.order = [by_slug[s] for s in graph.order]
    except ValueError as exc:  # a cycle or a self-loop
        report.problems.append(f"prerequisites: {exc}")
    missing_level = [c.slug for c in concepts if c.level is None]
    if missing_level and len(missing_level) < len(concepts):
        report.warnings.append(f"concepts without a level: {', '.join(missing_level)}")
    practised = {o.get("concept") for o in raw.get("objectives") or [] if isinstance(o, dict)}
    unpractised = [s for s in slugs if s not in practised]
    if unpractised:
        report.warnings.append(f"concepts no objective practises yet: {', '.join(unpractised)}")
    if not report.problems:
        try:  # everything else the course format requires (modalities, rubrics, objectives)
            CourseSpec.model_validate(raw)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(x) for x in err["loc"]) or "course"
                report.problems.append(f"{loc}: {err['msg']}")
    return report


def render(report: Report) -> str:
    lines = []
    if report.order:
        by_level: dict[str, list[Concept]] = {}
        for c in report.order:
            by_level.setdefault(c.level or "no level", []).append(c)
        for level in [*LEVELS, "no level"]:
            if level not in by_level:
                continue
            lines.append(f"{level} ({len(by_level[level])})")
            for c in by_level[level]:
                needs = f"  needs: {', '.join(c.prerequisites)}" if c.prerequisites else ""
                lines.append(f"  {c.slug}: {c.name_en} / {c.name_vi}{needs}")
        lines.append(f"{len(report.order)} concepts")
    lines += [f"warning: {w}" for w in report.warnings]
    lines += [f"problem: {p}" for p in report.problems]
    lines.append("OK" if report.ok else f"{len(report.problems)} problem(s)")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("course", type=Path)
    report = check_course(parser.parse_args(argv).course)
    print(render(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
