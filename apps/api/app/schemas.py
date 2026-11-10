"""Contracts shared by every lane (TEAM.md, "Contracts"). Owner: P1. Draft at H1, frozen at H3.

Three groups:
  1. Knowledge Graph and Items: the YAML fixtures / golden topics P4 writes (and the DB rows
     they load into).
  2. Retrieval: `Citation`, returned by `app.rag.retrieve.search`.
  3. API: request and response bodies for every route in the TEAM.md API table.

Changing a shape here changes a contract: only P1, announced at a checkpoint. Additive optional
fields are the only change allowed after H3.
"""

import re
from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.engine.trace import DecisionTrace

__all__ = ["DecisionTrace"]  # re-exported so routes import every contract from one module

Slug = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=1, max_length=80)
Probability = Field(ge=0.0, le=1.0)

Mode = Literal["quick", "deep"]  # Nhanh | Nghiên cứu sâu
Tier = Literal["free", "pro"]
ItemKind = Literal["mcq"]  # demo scope: MCQ only ("code" exists in the DB for later)
ItemStatus = Literal["verified", "needs_review"]


class _Contract(BaseModel):
    # Unknown keys are errors: a typo in a fixture or a request must fail loudly, not vanish.
    model_config = ConfigDict(extra="forbid", validate_by_name=True, serialize_by_alias=True)


# ---------------------------------------------------------------------------------------------
# 1. Knowledge Graph (P4 writes, P1 + P5 read)
# ---------------------------------------------------------------------------------------------


class Concept(_Contract):
    slug: str = Slug  # kebab-case, unique per subject
    name_vi: str = Field(min_length=1)
    name_en: str = Field(min_length=1)
    description_vi: str = ""
    sources: list[str] = Field(min_length=1)  # source_uri of the pages the concept comes from


class Edge(_Contract):
    """prerequisite -> concept: `from_` must be learned before `to`."""

    from_: str = Field(alias="from")
    to: str


class KnowledgeGraph(_Contract):
    concepts: list[Concept] = Field(min_length=1)
    edges: list[Edge] = []

    @model_validator(mode="after")
    def _check_dag(self) -> Self:
        slugs = [c.slug for c in self.concepts]
        if len(set(slugs)) != len(slugs):
            raise ValueError("concept slugs must be unique")
        known = set(slugs)
        for e in self.edges:
            if e.from_ not in known or e.to not in known:
                raise ValueError(f"edge {e.from_} -> {e.to} uses an unknown concept")
            if e.from_ == e.to:
                raise ValueError(f"self-loop on {e.to}")
        if len({(e.from_, e.to) for e in self.edges}) != len(self.edges):
            raise ValueError("duplicate edge")
        _reject_cycles(known, [(e.from_, e.to) for e in self.edges])
        return self


def _reject_cycles(nodes: set[str], edges: list[tuple[str, str]]) -> None:
    """Kahn's algorithm: if a topological order does not cover every node, there is a cycle."""
    indegree = dict.fromkeys(nodes, 0)
    children: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        children[a].append(b)
        indegree[b] += 1
    ready = [n for n, d in indegree.items() if d == 0]
    seen = 0
    while ready:
        n = ready.pop()
        seen += 1
        for c in children[n]:
            indegree[c] -= 1
            if indegree[c] == 0:
                ready.append(c)
    if seen != len(nodes):
        stuck = sorted(n for n, d in indegree.items() if d > 0)
        raise ValueError(f"prerequisite cycle among: {', '.join(stuck)}")


# ---------------------------------------------------------------------------------------------
# 1b. Items (P4 writes, P1 + P3 read) — one YAML file per concept
# ---------------------------------------------------------------------------------------------


class Misconception(_Contract):
    slug: str = Slug
    description_vi: str = Field(min_length=1)


class Option(_Contract):
    label: str = Field(min_length=1)
    correct: bool
    misconception: str | None = None  # required on every wrong option


class Item(_Contract):
    id: str = Field(min_length=1)  # stable fixture id, e.g. "plr-001"
    kind: ItemKind = "mcq"
    prompt_vi: str = Field(min_length=1)
    difficulty: float = Probability
    source: str  # source_uri of the page the item is based on
    chunk_ids: list[str] = Field(
        min_length=1
    )  # generator's citations; the verifier sees only these
    status: ItemStatus = "needs_review"  # only "verified" items are ever served
    options: list[Option] = Field(min_length=2)

    @model_validator(mode="after")
    def _check_options(self) -> Self:
        if sum(o.correct for o in self.options) != 1:
            raise ValueError(f"item {self.id}: exactly one option must be correct")
        for o in self.options:
            if o.correct and o.misconception is not None:
                raise ValueError(f"item {self.id}: the correct option has no misconception")
            if not o.correct and o.misconception is None:
                raise ValueError(f"item {self.id}: wrong option {o.label!r} needs a misconception")
        if len({o.label for o in self.options}) != len(self.options):
            raise ValueError(f"item {self.id}: option labels must be distinct")
        return self


class ItemSet(_Contract):
    concept: str = Slug
    misconceptions: list[Misconception] = []
    items: list[Item] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_misconceptions(self) -> Self:
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("item ids must be unique within an ItemSet")
        defined = {m.slug for m in self.misconceptions}
        for item in self.items:
            for o in item.options:
                if o.misconception is not None and o.misconception not in defined:
                    raise ValueError(f"item {item.id}: unknown misconception {o.misconception!r}")
        return self


# ---------------------------------------------------------------------------------------------
# 2. Retrieval (P1) — `app.rag.retrieve.search(query, subject, k=5) -> list[Citation]`
# ---------------------------------------------------------------------------------------------


class Citation(_Contract):
    """One retrieved chunk with everything needed to cite it and open the original page."""

    chunk_id: str
    source_title: str
    publisher: str | None = None
    license: str
    chapter: str | None = None
    section: str | None = None
    source_uri: str  # web URL, or the Supabase Storage path of an uploaded file
    page: int | None = None  # PDF page; None for web sources
    content: str
    score: float  # cosine similarity in [-1, 1], higher is closer


class CitationRef(_Contract):
    """What the web app shows under a hint or answer."""

    title: str
    section: str | None = None
    url: str
    page: int | None = None  # opens the right page of an uploaded PDF


# ---------------------------------------------------------------------------------------------
# 2b. Library documents (P3's readers write, P1's chunker reads): a book or upload as blocks
# ---------------------------------------------------------------------------------------------

BlockKind = Literal["text", "exercise", "glossary"]  # same kinds as `chunks.kind`

# "ND" (NoDerivatives) licences are not allowed for source material (SPEC.md).
_ND_LICENSE = re.compile(r"(?i)(?:^|[\s\-/(])ND(?:$|[\s\-/)])|no\s*derivativ")


class DocBlock(_Contract):
    """One passage in reading order. Readers emit blocks; the chunker merges and splits them."""

    chapter_no: int | None = None  # None when the source has no numbered chapters (an upload)
    chapter: str = Field(min_length=1)
    section: str = Field(min_length=1)  # heading path, e.g. "Boolean Expressions > Exercises"
    kind: BlockKind = "text"
    text: str  # blank text is allowed and dropped by the chunker, so readers need not filter
    source_uri: str = Field(min_length=1)  # page URL with anchor, or the Supabase Storage path
    page: int | None = Field(default=None, ge=1)  # 1-based PDF page; None for web sources


class ParsedDocument(_Contract):
    blocks: list[DocBlock] = Field(min_length=1)


class SourceMeta(_Contract):
    """Who a book is and what it may be used for; written next to its document (`source.json`)."""

    subject_slug: str = Slug
    subject_name_vi: str = Field(min_length=1)
    subject_name_en: str = Field(min_length=1)
    title: str = Field(min_length=1)
    author: str | None = None
    license: str = Field(min_length=1)
    url: str | None = None
    version: str = "unknown"  # e.g. the upstream commit or edition the text was taken from

    @model_validator(mode="after")
    def _no_nd_license(self) -> Self:
        if _ND_LICENSE.search(self.license):
            raise ValueError(f"licence {self.license!r} is NoDerivatives (ND); not allowed")
        return self


# ---------------------------------------------------------------------------------------------
# 3. API (TEAM.md, "API"). `item` sent to the web never contains the answer.
# ---------------------------------------------------------------------------------------------

TopicStatus = Literal["queued", "researching", "indexing", "graph", "items", "ready", "failed"]
TrailKind = Literal["search", "read", "select"]


class PublicOption(_Contract):
    label: str


class PublicItem(_Contract):
    id: str
    kind: ItemKind
    prompt_vi: str
    options: list[PublicOption]


# POST /learners
class LearnerCreate(_Contract):
    display_name: str = Field(min_length=1, max_length=80)


class LearnerCreated(_Contract):
    learner_id: str


# POST /topics
class TopicCreate(_Contract):
    goal_vi: str | None = Field(default=None, min_length=1, max_length=500)
    upload_id: str | None = None
    mode: Mode
    tier: Tier

    @model_validator(mode="after")
    def _goal_or_upload(self) -> Self:
        if self.goal_vi is None and self.upload_id is None:
            raise ValueError("give goal_vi, upload_id, or both")
        return self


class TopicCreated(_Contract):
    topic_id: str
    cached: bool


# GET /topics/{id} and each SSE `state` event of GET /topics/{id}/events
class TopicSource(_Contract):
    title: str
    publisher: str
    url: str
    license: str


class TrailEvent(_Contract):
    at: datetime
    kind: TrailKind
    text_vi: str
    url: str | None = None
    code: str | None = Field(default=None, exclude_if=lambda value: value is None)
    outcome: Literal["started", "rejected", "failed"] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    stage: str | None = Field(default=None, exclude_if=lambda value: value is None)
    action_vi: str | None = Field(default=None, exclude_if=lambda value: value is None)
    elapsed_seconds: str | None = Field(default=None, exclude_if=lambda value: value is None)


class SourceRejection(_Contract):
    code: str
    url: str | None = None
    message_vi: str


class TopicFailure(_Contract):
    stage: str
    code: str
    message_vi: str
    action_vi: str
    rejected_sources: list[SourceRejection] = []


class TopicState(_Contract):
    status: TopicStatus
    step_vi: str
    progress: float = Probability
    subject_slug: str | None = None
    graph_ready: bool
    items_ready: bool
    sources: list[TopicSource] = []
    trail: list[TrailEvent] = []
    failure: TopicFailure | None = Field(default=None, exclude_if=lambda value: value is None)


# GET /topics/cached
class CachedTopic(_Contract):
    subject_slug: str
    name_vi: str


class CachedTopics(_Contract):
    topics: list[CachedTopic]


# POST /uploads (multipart file, or this JSON body for a link)
class UploadLink(_Contract):
    url: str


class UploadCreated(_Contract):
    upload_id: str
    pages: int = Field(ge=0)
    text_ok: bool  # False: scanned or unreadable; the web asks for another file


# GET /graph?learner_id=&subject=
class GraphNode(_Contract):
    slug: str
    name_vi: str
    p_known: float = Probability
    mastered: bool


class GraphView(_Contract):
    nodes: list[GraphNode]
    edges: list[Edge]


# GET /graph/review?subject= and POST /graph/confirm (specs/graph-confirmation-contract/).
# Identity comes from the learner session cookie (`nodetrail_learner`), never from the body.
GRAPH_REVISION_PATTERN = r"^[a-f0-9]{64}$"  # sha256 of the generated map, set by the backend


class GraphReview(_Contract):
    learner_id: UUID
    subject: str
    graph_revision: str = Field(pattern=GRAPH_REVISION_PATTERN)
    graph: KnowledgeGraph  # the generated concepts and prerequisite edges, before any mastery
    confirmed: bool  # True only when this exact revision is already confirmed


class GraphConfirm(_Contract):
    subject: str = Field(min_length=1, max_length=80)
    graph_revision: str = Field(
        pattern=GRAPH_REVISION_PATTERN
    )  # the revision the learner was shown


class GraphConfirmed(_Contract):
    learner_id: UUID
    subject: str
    graph_revision: str = Field(pattern=GRAPH_REVISION_PATTERN)
    confirmed: Literal[True] = True


# GET /topics/{topic_id}/metrics (specs/topic-metrics/): what the demo dashboard shows for one topic
class TopicMetrics(_Contract):
    topic_id: str
    elapsed_seconds: float | None = Field(
        default=None, ge=0
    )  # wall time of the build; None = unknown
    cost_usd: float | None = Field(
        default=None, ge=0
    )  # measured model-call cost; None = unknown, never estimated
    items_generated: int = Field(ge=0)
    items_verified: int = Field(ge=0)
    items_dropped: int = Field(ge=0)  # failed verification, so never served

    @model_validator(mode="after")
    def _counts_fit(self) -> Self:
        if self.items_verified + self.items_dropped > self.items_generated:
            raise ValueError("verified plus dropped items cannot exceed generated items")
        return self


# POST /placement/next
class PlacementRequest(_Contract):
    learner_id: str
    subject: str


class PlacementStep(_Contract):
    item: PublicItem | None
    done: bool
    gap_slug: str | None = None
    trace: DecisionTrace


# GET /next-item?learner_id=&subject=
class NextItem(_Contract):
    item: PublicItem
    reason_vi: str


# POST /attempts
class AttemptCreate(_Contract):
    client_attempt_id: UUID | None = Field(default=None, exclude_if=lambda value: value is None)
    learner_id: str
    item_id: str
    answer: int = Field(ge=0)  # index into the item's `options`, in the order they were sent
    hints_used: int = Field(default=0, ge=0)


class Remediation(_Contract):
    concept_slug: str
    reason_vi: str


class AttemptResult(_Contract):
    correct: bool
    misconception_vi: str | None = None
    p_known: float = Probability
    mastered: bool
    remediation: Remediation | None = None
    traces: list[DecisionTrace]


# POST /tutor/hint
class HintRequest(_Contract):
    learner_id: str
    item_id: str
    level: int = Field(ge=1, le=4)  # hint ladder rung; higher = more specific, never the answer
    last_answer: int | None = Field(default=None, ge=0)
    tier: Tier


class HintResponse(_Contract):
    hint_vi: str
    citations: list[CitationRef] = Field(min_length=1)  # no citation, no hint


# POST /ask
class AskRequest(_Contract):
    question: str = Field(min_length=1, max_length=1000)
    subject: str
    tier: Tier


class AskResponse(_Contract):
    answer_vi: str
    citations: list[CitationRef]


# GET /reviews/due?learner_id=
class DueCard(_Contract):
    concept_slug: str
    due_at: datetime


class DueReviews(_Contract):
    cards: list[DueCard]


# POST /exam-plan
class ExamPlanRequest(_Contract):
    learner_id: str
    subject: str
    exam_date: date


class ExamDay(_Contract):
    date: date
    concept_slugs: list[str]
    minutes: int = Field(ge=0)


class ExamPlan(_Contract):
    days: list[ExamDay]
