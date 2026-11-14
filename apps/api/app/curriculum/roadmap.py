"""Build the engine's `Roadmap` from a course with milestones and hidden nodes.

Spec: specs/level-test.
"""

from app.curriculum.course import CourseSpec, concept_edges
from app.engine.graph import Graph
from app.engine.milestones import Roadmap


def build_roadmap(course: CourseSpec) -> Roadmap:
    milestones = course.milestones()
    if not milestones:
        raise ValueError(f"{course.slug} has no milestones")
    missing = [m.slug for m in milestones if m.level is None]
    if missing:
        raise ValueError(f"milestones need a level: {', '.join(missing)}")
    names = {c.slug: c.name_vi for c in course.concepts}
    graph = Graph.from_edges(
        [c.slug for c in course.concepts], concept_edges(course.concepts), names
    )
    hidden = {
        m.slug: tuple(n for n in graph.order if n in {h.slug for h in course.hidden_nodes(m.slug)})
        for m in milestones
    }
    empty = [m for m, nodes in hidden.items() if not nodes]
    if empty:
        raise ValueError(f"milestones without hidden nodes: {', '.join(empty)}")
    return Roadmap(
        graph=graph,
        milestones=Graph.from_edges([m.slug for m in milestones], course.milestone_edges(), names),
        hidden=hidden,
        level={m.slug: str(m.level) for m in milestones},
    )
