"""P4 boundaries for P1 contracts and P3's pipeline/HTTP ports; no fake trust flags."""

from app.api.tutor import Citation as TutorCitation
from app.api.tutor import VerifiedText
from app.content.models import Chunk, Graph, Item, Source, validate_references
from app.graders.mcq import Item as GraderItem
from app.guardrails.answerability import is_currently_verified
from app.research.pipeline import GraphDraft
from app.schemas import Item as ContractItem
from app.schemas import ItemSet, KnowledgeGraph
from app.tutor.hints import Hint


def contract_graph(graph: Graph) -> KnowledgeGraph:
    return KnowledgeGraph.model_validate(graph.team_payload())


def contract_item(item: Item) -> ContractItem:
    """Internal fixture export. This is NOT a learner-safe response or a trust gate."""
    return ContractItem.model_validate(
        {
            "id": item.id,
            "kind": item.kind,
            "prompt_vi": item.prompt_vi,
            "difficulty": item.difficulty,
            "source": item.source,
            "chunk_ids": [str(cid) for cid in item.chunk_ids],
            "status": item.status,
            "options": [o.model_dump(exclude={"id"}) for o in item.options],
        }
    )


def contract_item_sets(items: list[Item]) -> list[ItemSet]:
    sets = []
    for concept in sorted({item.concept for item in items}):
        group = [item for item in items if item.concept == concept]
        misconceptions = {m.slug: m for item in group for m in item.misconceptions}
        sets.append(
            ItemSet.model_validate(
                {
                    "concept": concept,
                    "misconceptions": [m.model_dump() for m in misconceptions.values()],
                    "items": [contract_item(item).model_dump() for item in group],
                }
            )
        )
    return sets


def pipeline_graph(
    subject_slug: str, graph: Graph, chunks: list[Chunk], sources: list[Source]
) -> GraphDraft:
    validate_references(chunks, sources, graph)
    # supported here means structurally/source-reference validated, NOT human approval.
    return GraphDraft.model_validate(
        {
            "subject_slug": subject_slug,
            "graph": contract_graph(graph).model_dump(mode="json", by_alias=True),
            "supported": True,
        }
    )


def pipeline_items(items: list[Item], chunks: list[Chunk]) -> list[GraderItem]:
    """The only P4->P3 item release boundary: recheck current audit before conversion."""
    return [
        GraderItem.model_validate(contract_item(item).model_dump())
        for item in items
        if is_currently_verified(item, chunks)
    ]


def tutor_text(hint: Hint | None) -> VerifiedText:
    if hint is None:
        return VerifiedText(
            text_vi="Chưa có gợi ý đã được kiểm chứng.", citations=[], supported=False
        )
    return VerifiedText(
        text_vi=hint.hint_vi,
        citations=[
            TutorCitation(title=c.title, section=c.section, url=c.url) for c in hint.citations
        ],
        supported=True,
    )
