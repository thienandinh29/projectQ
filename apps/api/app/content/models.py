"""Validated P4 artifacts, with TEAM-compatible graph/item exports."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Source(Record):
    source_id: str = Field(min_length=1)
    title: str
    author: str
    publisher: str
    version: str
    url: str = Field(pattern=r"^(https://|storage://|supabase://)")
    section: str
    license: str
    accessed_at: str
    location_type: str = "web_section"
    page: int | None = None
    attribution: str
    model_ingestion_allowed: bool = False


class SourceSet(Record):
    topic: str
    sources: list[Source]


class Chunk(Record):
    chunk_id: UUID
    source_id: str
    section: str
    page: int | None = None
    content: str = Field(min_length=1)
    representation: Literal["agent_paraphrase_vi", "verbatim", "paraphrase_vi"]
    license: str


class Concept(Record):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name_vi: str
    name_en: str
    description_vi: str
    sources: list[str] = Field(min_length=1)
    chunk_ids: list[UUID] = Field(min_length=1)


class Edge(Record):
    prerequisite: str = Field(alias="from")
    to: str
    chunk_ids: list[UUID] = Field(min_length=1)
    rationale_vi: str
    evidence_kind: Literal["source_explicit", "pedagogical_inference"]


class Graph(Record):
    concepts: list[Concept] = Field(min_length=1)
    edges: list[Edge]

    @model_validator(mode="after")
    def valid_dag(self) -> "Graph":
        slugs = [c.slug for c in self.concepts]
        names = [c.name_vi.casefold().strip() for c in self.concepts]
        if len(set(slugs)) != len(slugs) or len(set(names)) != len(names):
            raise ValueError("duplicate concepts")
        pairs = [(e.prerequisite, e.to) for e in self.edges]
        if len(set(pairs)) != len(pairs):
            raise ValueError("duplicate edges")
        pending = set(slugs)
        if any(a not in pending or b not in pending for a, b in pairs):
            raise ValueError("unknown edge endpoint")
        while pending:
            roots = {n for n in pending if not any(b == n and a in pending for a, b in pairs)}
            if not roots:
                raise ValueError("prerequisite cycle")
            pending -= roots
        return self

    def team_payload(self) -> dict[str, object]:
        return {
            "concepts": [c.model_dump(exclude={"chunk_ids"}) for c in self.concepts],
            "edges": [{"from": e.prerequisite, "to": e.to} for e in self.edges],
        }


class ModelIdentity(Record):
    provider: str
    model: str
    family: str | None
    identity_source: Literal["gateway", "agent_session", "unavailable"]


class HumanReview(Record):
    status: Literal["pending", "approved", "rejected"] = "pending"
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def require_reviewer(self) -> "HumanReview":
        if self.status != "pending" and (not self.reviewer or not self.reviewed_at):
            raise ValueError("human decisions require reviewer and timestamp")
        return self


class Misconception(Record):
    slug: str
    description_vi: str = Field(min_length=1)


class Option(Record):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    correct: bool
    misconception: str | None = None


class Evidence(Record):
    chunk_id: UUID
    quote: str = Field(min_length=1)


class Verification(Record):
    status: Literal["verified", "needs_review"]
    reason: str
    content_hash: str
    generator: ModelIdentity
    verifier: ModelIdentity | None = None
    prompt_version: str
    checked_at: datetime
    evidence: list[Evidence] = Field(default_factory=list)


class Item(Record):
    id: str
    kind: Literal["mcq"] = "mcq"
    concept: str
    prompt_vi: str = Field(min_length=1)
    difficulty: float = Field(ge=0, le=1)
    source: str
    source_ids: list[str] = Field(min_length=1)
    chunk_ids: list[UUID] = Field(min_length=1)
    options: list[Option] = Field(min_length=2)
    answer_id: str
    explanation_vi: str = Field(min_length=1)
    misconceptions: list[Misconception]
    status: Literal["verified", "needs_review"] = "needs_review"
    generator: ModelIdentity
    verification: Verification | None = None
    verification_history: list[Verification] = Field(default_factory=list)
    human_review: HumanReview = Field(default_factory=HumanReview)

    @model_validator(mode="after")
    def consistent_options(self) -> "Item":
        ids = [o.id for o in self.options]
        labels = [o.label.casefold().strip() for o in self.options]
        if len(set(ids)) != len(ids) or len(set(labels)) != len(labels):
            raise ValueError("duplicate option IDs or labels")
        correct = [o for o in self.options if o.correct]
        if len(correct) != 1 or correct[0].id != self.answer_id:
            raise ValueError("exactly one correct option must match answer_id")
        misconceptions = {m.slug for m in self.misconceptions}
        if len(misconceptions) != len(self.misconceptions):
            raise ValueError("duplicate misconceptions")
        for option in self.options:
            if option.correct and option.misconception is not None:
                raise ValueError("correct option cannot carry a misconception")
            if not option.correct and option.misconception not in misconceptions:
                raise ValueError("distractor must reference a misconception")
        if len(set(self.chunk_ids)) != len(self.chunk_ids):
            raise ValueError("duplicate chunk citations")
        return self


def digest(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_references(
    chunks: list[Chunk], sources: list[Source], graph: Graph | None = None
) -> None:
    ids = {c.chunk_id for c in chunks}
    source_ids = {s.source_id for s in sources}
    if len(ids) != len(chunks) or len(source_ids) != len(sources):
        raise ValueError("duplicate source/chunk IDs")
    if any(c.source_id not in source_ids for c in chunks):
        raise ValueError("unknown chunk source")
    if graph:
        urls = {s.url for s in sources}
        for concept in graph.concepts:
            if not set(concept.chunk_ids) <= ids or not set(concept.sources) <= urls:
                raise ValueError("unknown graph citation")
        if any(not set(e.chunk_ids) <= ids for e in graph.edges):
            raise ValueError("unknown edge citation")


def cited_chunks(item: Item, chunks: list[Chunk]) -> list[Chunk]:
    lookup = {c.chunk_id: c for c in chunks}
    if len(lookup) != len(chunks) or not set(item.chunk_ids) <= lookup.keys():
        raise ValueError("missing or duplicate chunk")
    cited = [lookup[cid] for cid in item.chunk_ids]
    if {c.source_id for c in cited} != set(item.source_ids):
        raise ValueError("source_ids must match cited chunks")
    return cited


def item_hash(item: Item, chunks: list[Chunk]) -> str:
    return digest(
        {
            "item": item.model_dump(
                mode="json",
                exclude={"status", "verification", "verification_history", "human_review"},
            ),
            "chunks": [c.model_dump(mode="json") for c in cited_chunks(item, chunks)],
        }
    )
