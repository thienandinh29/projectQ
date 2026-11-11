"""Ground truth computed from a figure's data: the facts a learner's answer is graded against.

A judge (code or a calibrated LLM) receives these facts, never the rendered image: vision models
read charts unreliably, and the facts are exact by construction. Texts are in English because the
first course that needs them (IELTS Academic Writing Task 1) is assessed in English.
"""

from dataclasses import dataclass

from app.curriculum.figures import ChartFigure, DiagramFigure, MapFigure, ProcessFigure

# Overall change smaller than this share of the series' range counts as "roughly stable".
STABLE_SHARE = 0.05


@dataclass(frozen=True)
class Fact:
    kind: str  # e.g. "max", "min", "overall_change", "largest_step", "ranking", "share"
    series: str | None
    category: str | None
    value: float | None
    text: str


def _fmt(v: float, unit: str) -> str:
    number = f"{v:g}"
    return f"{number}{unit}" if unit in {"%", "°C"} else f"{number} {unit}".rstrip()


def chart_facts(chart: ChartFigure) -> list[Fact]:
    """Key features: extremes, overall change, largest step, final ranking, pie shares."""
    u, cats, facts = chart.unit, chart.categories, []
    if chart.chart_type == "pie":
        values = chart.series[0].values
        total = sum(values)
        for cat, v in sorted(zip(cats, values, strict=True), key=lambda cv: -cv[1]):
            share = 100 * v / total if total else 0.0
            facts.append(
                Fact("share", None, cat, round(share, 1), f"{cat}: {share:.1f}% of the total")
            )
        return facts

    for s in chart.series:
        vals = s.values
        hi = max(range(len(vals)), key=lambda i: (vals[i], -i))
        lo = min(range(len(vals)), key=lambda i: (vals[i], i))
        facts.append(
            Fact(
                "max",
                s.name,
                cats[hi],
                vals[hi],
                f"{s.name} peaks at {_fmt(vals[hi], u)} in {cats[hi]}",
            )
        )
        facts.append(
            Fact(
                "min",
                s.name,
                cats[lo],
                vals[lo],
                f"{s.name} is lowest at {_fmt(vals[lo], u)} in {cats[lo]}",
            )
        )
        if len(vals) >= 2:
            change = vals[-1] - vals[0]
            spread = max(vals) - min(vals)
            if spread == 0 or abs(change) <= STABLE_SHARE * spread:
                direction = "stays roughly stable"
            else:
                direction = "rises" if change > 0 else "falls"
            facts.append(
                Fact(
                    "overall_change",
                    s.name,
                    None,
                    change,
                    f"{s.name} {direction} from {_fmt(vals[0], u)} ({cats[0]}) "
                    f"to {_fmt(vals[-1], u)} ({cats[-1]})",
                )
            )
            steps = [(vals[i + 1] - vals[i], i) for i in range(len(vals) - 1)]
            step, i = max(steps, key=lambda d: (abs(d[0]), -d[1]))
            if step != 0:
                verb = "rise" if step > 0 else "fall"
                facts.append(
                    Fact(
                        "largest_step",
                        s.name,
                        cats[i + 1],
                        step,
                        f"{s.name}'s largest {verb} is {_fmt(abs(step), u)}, "
                        f"between {cats[i]} and {cats[i + 1]}",
                    )
                )
    if len(chart.series) > 1:
        last = len(cats) - 1
        order = sorted(chart.series, key=lambda s: (-s.values[last], s.name))
        ranking = ", ".join(f"{s.name} ({_fmt(s.values[last], u)})" for s in order)
        facts.append(Fact("ranking", None, cats[last], None, f"In {cats[last]}: {ranking}"))
    return facts


@dataclass(frozen=True)
class MapChange:
    kind: str  # "added" | "removed" | "moved" | "resized" | "relabelled" | "retyped"
    feature_id: str
    text: str


def map_changes(m: MapFigure) -> list[MapChange]:
    """What changed between the two scenes; features are matched by id."""
    before = {f.id: f for f in m.before}
    after = {f.id: f for f in m.after}
    changes: list[MapChange] = []
    for fid, f in before.items():
        if fid not in after:
            changes.append(MapChange("removed", fid, f"The {f.label} was removed"))
    for fid, a in after.items():
        b = before.get(fid)
        if b is None:
            changes.append(MapChange("added", fid, f"A {a.label} was added"))
            continue
        if a.type != b.type:
            changes.append(
                MapChange("retyped", fid, f"The {b.label} became {a.type.replace('_', ' ')}")
            )
        if a.label != b.label:
            changes.append(MapChange("relabelled", fid, f"The {b.label} became the {a.label}"))
        if (a.x, a.y) != (b.x, b.y):
            changes.append(MapChange("moved", fid, f"The {a.label} was moved"))
        if (a.w, a.h) != (b.w, b.h):
            bigger = a.w * a.h > b.w * b.h
            changes.append(
                MapChange(
                    "resized", fid, f"The {a.label} was {'enlarged' if bigger else 'reduced'}"
                )
            )
    return changes


def process_steps(p: ProcessFigure) -> list[str]:
    steps = [f"Step {i}: {s}" for i, s in enumerate(p.steps, start=1)]
    if p.cyclic:
        steps.append(f"The process then returns to step 1 ({p.steps[0]})")
    return steps


@dataclass(frozen=True)
class DiagramFacts:
    roots: tuple[str, ...]  # nodes nothing points to (directed only)
    leaves: tuple[str, ...]  # nodes that point to nothing (directed only)
    edges: tuple[tuple[str, str], ...]


def diagram_facts(d: DiagramFigure) -> DiagramFacts:
    ids = [n.id for n in d.nodes]
    edges = tuple((e.source, e.target) for e in d.edges)
    if not d.directed:
        return DiagramFacts((), (), edges)
    targets = {t for _, t in edges}
    sources = {s for s, _ in edges}
    return DiagramFacts(
        tuple(n for n in ids if n not in targets), tuple(n for n in ids if n not in sources), edges
    )
