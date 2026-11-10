"""Prerequisite DAG helpers and root-cause tracing (contract: TEAM.md, "Python interfaces").

Pure: a `Graph` is built once from the Knowledge Graph contract and never changes. Graphs are small
(< ~100 concepts), so plain dicts and BFS are enough; no graph library.

Edge direction everywhere: prerequisite -> concept. A concept's *ancestors* are everything that must
be learned before it; *descendants* are everything that builds on it.
"""

from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from app.engine.bkt import DEFAULT_PARAMS, MASTERY_THRESHOLD
from app.engine.trace import Alternative, DecisionTrace, Evidence, fmt_p
from app.schemas import KnowledgeGraph

# p_known for a concept with no mastery row yet: the BKT prior, i.e. "probably not known".
UNSEEN_P_KNOWN = DEFAULT_PARAMS["mcq"].p_init
# A prerequisite counts as a gap when it is probably not known. This is deliberately far below
# MASTERY_THRESHOLD: placement marks known concepts at 0.85, and those must not be sent back to.
WEAK_THRESHOLD = 0.5


@dataclass(frozen=True)
class Graph:
    order: tuple[str, ...]  # topological: every prerequisite before the concepts that need it
    parents: Mapping[str, tuple[str, ...]]  # direct prerequisites
    children: Mapping[str, tuple[str, ...]]  # concepts that directly need this one
    depth: Mapping[str, int]  # longest prerequisite chain below the concept; roots are 0
    names_vi: Mapping[str, str]

    @classmethod
    def from_edges(
        cls,
        slugs: Iterable[str],
        edges: Iterable[tuple[str, str]],
        names_vi: Mapping[str, str] | None = None,
    ) -> "Graph":
        nodes = sorted(set(slugs))
        known = set(nodes)
        parents: dict[str, set[str]] = {n: set() for n in nodes}
        children: dict[str, set[str]] = {n: set() for n in nodes}
        for a, b in edges:
            if a not in known or b not in known:
                raise ValueError(f"edge {a} -> {b} uses an unknown concept")
            if a == b:
                raise ValueError(f"self-loop on {a}")
            parents[b].add(a)
            children[a].add(b)

        # Kahn's algorithm, always taking the smallest slug, so the order is deterministic.
        indegree = {n: len(parents[n]) for n in nodes}
        ready = sorted(n for n in nodes if indegree[n] == 0)
        order: list[str] = []
        depth: dict[str, int] = {}
        while ready:
            n = ready.pop(0)
            order.append(n)
            depth[n] = max((depth[p] + 1 for p in parents[n]), default=0)
            for c in sorted(children[n]):
                indegree[c] -= 1
                if indegree[c] == 0:
                    ready.append(c)
            ready.sort()
        if len(order) != len(nodes):
            stuck = sorted(n for n in nodes if n not in depth)
            raise ValueError(f"prerequisite cycle among: {', '.join(stuck)}")

        return cls(
            order=tuple(order),
            parents=MappingProxyType({n: tuple(sorted(parents[n])) for n in nodes}),
            children=MappingProxyType({n: tuple(sorted(children[n])) for n in nodes}),
            depth=MappingProxyType(depth),
            names_vi=MappingProxyType(dict(names_vi or {})),
        )

    @classmethod
    def from_contract(cls, kg: KnowledgeGraph) -> "Graph":
        return cls.from_edges(
            (c.slug for c in kg.concepts),
            ((e.from_, e.to) for e in kg.edges),
            {c.slug: c.name_vi for c in kg.concepts},
        )

    def __contains__(self, slug: object) -> bool:
        return slug in self.parents

    def __len__(self) -> int:
        return len(self.order)

    def name_vi(self, slug: str) -> str:
        return self.names_vi.get(slug, slug)

    def roots(self) -> tuple[str, ...]:
        """Concepts with no prerequisites."""
        return tuple(n for n in self.order if not self.parents[n])

    def leaves(self) -> tuple[str, ...]:
        """Concepts nothing else builds on (the most advanced goals)."""
        return tuple(n for n in self.order if not self.children[n])

    def ancestors(self, slug: str) -> dict[str, int]:
        """Every prerequisite of `slug` (transitively) -> hops to it on the shortest path."""
        return self._walk(slug, self.parents)

    def descendants(self, slug: str) -> dict[str, int]:
        """Every concept that builds on `slug` (transitively) -> hops on the shortest path."""
        return self._walk(slug, self.children)

    def _walk(self, slug: str, step: Mapping[str, tuple[str, ...]]) -> dict[str, int]:
        self._require(slug)
        hops: dict[str, int] = {}
        queue = deque([(slug, 0)])
        while queue:
            node, d = queue.popleft()
            for nxt in step[node]:
                if nxt not in hops:
                    hops[nxt] = d + 1
                    queue.append((nxt, d + 1))
        return hops

    def _require(self, slug: str) -> None:
        if slug not in self.parents:
            raise KeyError(f"unknown concept {slug!r}")


def root_cause(
    graph: Graph,
    mastery: Mapping[str, float],
    failed_slug: str,
    *,
    now: datetime,
    item_id: str | None = None,
    misconception: str | None = None,
    threshold: float = WEAK_THRESHOLD,
) -> tuple[str, DecisionTrace]:
    """Where to remediate after a wrong answer on `failed_slug`.

    Candidates are the failed concept's prerequisites (transitively) that are probably not known
    (`p_known` below `threshold`, `WEAK_THRESHOLD` by default; not "not yet mastered").
    The weakest wins (lowest p_known); a tie goes to the deeper foundation (lower depth, closer to
    a root), then to the nearest one, then slug order. No weak prerequisite -> the failed concept
    itself: the foundations hold, so the learner practises this concept again.
    Concepts without a mastery entry count as `UNSEEN_P_KNOWN`.
    """
    hops = graph.ancestors(failed_slug)

    def p(slug: str) -> float:
        return mastery.get(slug, UNSEEN_P_KNOWN)

    def key(slug: str) -> tuple[float, int, int, str]:
        # Rounded so float noise (0.30000000000000004) never decides a tie.
        return (round(p(slug), 6), graph.depth[slug], hops[slug], slug)

    weak = sorted((s for s in hops if p(s) < threshold), key=key)
    failed_name = graph.name_vi(failed_slug)

    if weak:
        chosen = weak[0]
        rule = "root_cause.lowest_p_known"
        rule_vi = (
            f"Sai ở «{failed_name}» → quay lại kiến thức nền «{graph.name_vi(chosen)}», "
            f"phần yếu nhất (khả năng đã nắm vững {fmt_p(p(chosen))})"
        )
    else:
        chosen = failed_slug
        rule = "root_cause.no_weak_prerequisite"
        rule_vi = (
            f"Sai ở «{failed_name}», nhưng các kiến thức nền đều đã vững → "
            f"luyện tập thêm chính «{failed_name}»"
        )

    alternatives = [
        Alternative(
            concept_slug=s, p_known=p(s), why_not_vi=_why_not(graph, s, chosen, p, hops, threshold)
        )
        for s in sorted(hops, key=key)
        if s != chosen
    ]
    if chosen != failed_slug:
        alternatives.insert(
            0,
            Alternative(
                concept_slug=failed_slug,
                p_known=p(failed_slug),
                why_not_vi="Cần củng cố kiến thức nền yếu hơn trước khi luyện lại bài này",
            ),
        )

    trace = DecisionTrace(
        kind="root_cause",
        concept_slug=chosen,
        at=now,
        prior=p(chosen),
        evidence=Evidence(item_id=item_id, correct=False, misconception=misconception),
        rule=rule,
        rule_vi=rule_vi,
        alternatives=alternatives,
    )
    return chosen, trace


def _why_not(
    graph: Graph,
    slug: str,
    chosen: str,
    p: Callable[[str], float],
    hops: Mapping[str, int],
    threshold: float,
) -> str:
    chosen_name = graph.name_vi(chosen)
    if p(slug) >= MASTERY_THRESHOLD:
        return f"Đã nắm vững ({fmt_p(p(slug))})"
    if p(slug) >= threshold:
        return f"Tương đối vững ({fmt_p(p(slug))}), chưa cần củng cố"
    if round(p(slug), 6) > round(p(chosen), 6):
        return f"Vững hơn «{chosen_name}» ({fmt_p(p(slug))} so với {fmt_p(p(chosen))})"
    if graph.depth[slug] > graph.depth[chosen]:
        return f"Cùng mức, nhưng «{chosen_name}» là nền tảng sâu hơn nên học trước"
    if hops.get(slug, 0) > hops.get(chosen, 0):
        return f"Cùng mức, nhưng «{chosen_name}» gần bài vừa sai hơn"
    return f"Cùng mức với «{chosen_name}»; chọn một phần để bắt đầu"
