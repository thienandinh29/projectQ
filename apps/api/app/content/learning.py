"""P4 learning boundaries; no API contract, storage, provider or engine replacement."""

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from fsrs.card import CardDict

from app.content.models import Chunk, Graph, Item, Source, digest
from app.engine import srs
from app.engine.trace import DecisionTrace
from app.guardrails.answerability import is_currently_verified
from app.tutor.hints import Citation

GraphConfirmation = Callable[[str, str, str], bool]


def first_lesson_graph(graph: Graph, limit: int) -> Graph:
    """Keep a small prerequisite-closed lesson, rather than an entire subject map."""
    if limit < 1:
        raise ValueError("lesson concept limit must be positive")
    selected: list[str] = []
    while len(selected) < min(limit, len(graph.concepts)):
        next_concept = next(
            c
            for c in graph.concepts
            if c.slug not in selected
            and all(e.prerequisite in selected for e in graph.edges if e.to == c.slug)
        )
        selected.append(next_concept.slug)
    return Graph(
        concepts=[c for c in graph.concepts if c.slug in selected],
        edges=[e for e in graph.edges if e.prerequisite in selected and e.to in selected],
    )


def graph_revision(graph: Graph) -> str:
    return digest(graph.model_dump(mode="json", by_alias=True))


def graph_confirmed(
    confirmation: GraphConfirmation | None, learner: str, subject: str, graph: Graph
) -> bool:
    """Confirmation is per learner and graph revision, never a content audit."""
    if confirmation is None:
        return False
    return confirmation(learner, subject, graph_revision(graph)) is True


def teaching_chunks(chunks: list[Chunk], structural_ids: set[UUID]) -> list[Chunk]:
    """Caller-declared outlines/unverified notes are structure, not teaching evidence.

    No keyword heuristic can establish that a document contains sufficient material.
    Remaining chunks are candidates only; answerability still has to pass.
    """
    if not structural_ids <= {chunk.chunk_id for chunk in chunks}:
        raise ValueError("unknown structural chunk")
    material = [chunk for chunk in chunks if chunk.chunk_id not in structural_ids]
    if not material:
        raise ValueError("supporting instructional material is missing")
    return material


def missing_material(graph: Graph, chunks: list[Chunk], structural_ids: set[UUID]) -> list[str]:
    """Reference coverage, not semantic verification or learner confirmation."""
    if not structural_ids <= {chunk.chunk_id for chunk in chunks}:
        raise ValueError("unknown structural chunk")
    available = {chunk.chunk_id for chunk in chunks} - structural_ids
    return [c.slug for c in graph.concepts if not set(c.chunk_ids) & available]


class SubmittedFeedback:
    """Internal P4 handoff object. P3 owns any future HTTP feedback DTO."""

    def __init__(
        self,
        *,
        correct: bool,
        correct_answer_vi: str,
        explanation_vi: str,
        misconception_signal_vi: str | None,
        citations: list[Citation],
    ) -> None:
        self.correct = correct
        self.correct_answer_vi = correct_answer_vi
        self.explanation_vi = explanation_vi
        self.misconception_signal_vi = misconception_signal_vi
        self.citations = citations


def submitted_feedback(
    item: Item, chunks: list[Chunk], sources: list[Source], chosen_id: str, *, submitted: bool
) -> SubmittedFeedback | None:
    """Call only after the service has accepted submission, never from hint routes.

    Use verifier-cited source evidence instead of presenting an unchecked generated
    explanation as approved. This helper neither grades code nor updates mastery.
    """
    if not submitted or not is_currently_verified(item, chunks):
        return None
    selected = next((option for option in item.options if option.id == chosen_id), None)
    if selected is None:
        raise ValueError("unknown chosen option")
    audit = item.verification
    assert audit is not None
    lookup = {source.source_id: source for source in sources}
    cited = {e.chunk_id for e in audit.evidence}
    citations = []
    for chunk in chunks:
        if chunk.chunk_id not in cited:
            continue
        source = lookup.get(chunk.source_id)
        if source is None or not source.model_ingestion_allowed:
            return None
        citations.append(
            Citation(
                title=source.title,
                section=chunk.section,
                url=source.url,
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                page=chunk.page,
            )
        )
    if not citations:
        return None
    misconception = next(
        (m.description_vi for m in item.misconceptions if m.slug == selected.misconception), None
    )
    return SubmittedFeedback(
        correct=selected.correct,
        correct_answer_vi=next(option.label for option in item.options if option.correct),
        explanation_vi="Căn cứ để đối chiếu trong nguồn:\n"
        + "\n".join(e.quote for e in audit.evidence),
        misconception_signal_vi=(
            "Lựa chọn này có thể gợi ý một hiểu nhầm cần kiểm tra thêm: " + misconception
            if misconception
            else None
        ),
        citations=citations,
    )


def attempt_review(
    state: CardDict | None,
    correct: bool,
    mastered: bool,
    now: datetime,
    *,
    concept: str,
    item_id: str,
    hints_used: int = 0,
) -> tuple[srs.ReviewResult, DecisionTrace] | None:
    """Wrong answers may seed existing concept review without declaring mastery.

    This is the existing FSRS concept card, not a notes/flashcard subsystem.
    """
    if state is None and correct and not mastered:
        return None
    return srs.review_traced(
        state if state is not None else srs.new_card(now).state,
        correct,
        now,
        concept_slug=concept,
        item_id=item_id,
        hints_used=hints_used,
    )
