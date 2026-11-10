"""Fake gateway for unit tests ONLY; it provides no evidence of real-model quality."""

from pathlib import Path

from pydantic import BaseModel

from app.content.artifacts import load_topic
from app.content.gateway import ModelReply
from app.content.models import Chunk, Graph, Item, ModelIdentity, Source

ROOT = Path(__file__).resolve().parents[4]


def topic(
    slug: str = "python-conditions",
) -> tuple[list[Source], list[Chunk], Graph, list[Item]]:
    return load_topic(ROOT / "data/golden" / slug)


class FakeGateway:
    def __init__(self) -> None:
        _, self.chunks, _, items = topic()
        self.item = items[0]
        self.calls: list[dict[str, object]] = []
        self.family: str | None = "claude"
        self.error: Exception | None = None
        self.overrides: dict[str, object] = {}

    async def generate(
        self,
        *,
        task: str,
        tier: str,
        system: str,
        payload: dict[str, object],
        schema: type[BaseModel],
        exclude_family: str | None = None,
    ) -> ModelReply:
        self.calls.append({"task": task, "system": system, "payload": payload, "schema": schema})
        if self.error:
            raise self.error
        evidence = [{"chunk_id": str(self.chunks[0].chunk_id), "quote": self.chunks[0].content}]
        family = self.family
        if task == "verify_item":
            content = {
                "supported": True,
                "selected_option_id": next(
                    f"choice-{i}" for i, o in enumerate(self.item.options) if o.correct
                ),
                "unique_answer": True,
                "ambiguous": False,
                "multiple_correct": False,
                "insufficient_evidence": False,
                "evidence": evidence,
                "reason": "test only",
            }
        elif task == "generate_hint":
            content = {
                "hint_vi": "Hãy xác định phép toán rồi đối chiếu quy tắc trong nguồn.",
                "chunk_ids": [str(self.chunks[0].chunk_id)],
            }
            family = "gemini"
        elif task == "verify_hint":
            content = {
                "correct": True,
                "supported": True,
                "citations_valid": True,
                "relevant_to_history": True,
                "clear_vietnamese": True,
                "level_appropriate": True,
                "no_answer_leak": True,
                "no_elimination": True,
                "evidence": evidence,
                "reason": "test only",
            }
        else:
            raise ValueError(f"unexpected fake task {task}")
        content.update(self.overrides)
        return ModelReply(
            content=content,
            identity=ModelIdentity(
                provider="fake-test-provider",
                model="fake-model",
                family=family,
                identity_source="gateway",
            ),
        )
