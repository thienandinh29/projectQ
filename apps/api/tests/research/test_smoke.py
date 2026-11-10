import asyncio
import json
from collections.abc import Sequence

import pytest
from pydantic import BaseModel

from app.llm.gateway import Gateway, Message, ProviderError, ProviderReply, Route, Routing
from app.research.pipeline import PreparedChunk
from app.research.smoke import blind_input, run
from app.schemas import Item, ItemSet


def material() -> list[PreparedChunk]:
    return [
        PreparedChunk(
            id="c1",
            text="A program is a sequence of instructions.",
            source_uri="https://books.example/chapter",
        )
    ]


def generated() -> ItemSet:
    return ItemSet.model_validate(
        {
            "concept": "program",
            "misconceptions": [{"slug": "data", "description_vi": "Data"}],
            "items": [
                {
                    "id": f"q{i}",
                    "prompt_vi": "Program?",
                    "source": material()[0].source_uri,
                    "chunk_ids": ["c1"],
                    "difficulty": 0.3,
                    "options": [
                        {"label": "Instructions", "correct": True},
                        {"label": "Data", "correct": False, "misconception": "data"},
                    ],
                }
                for i in range(2)
            ],
        }
    )


class Adapter:
    def __init__(self, replies: list[str | Exception]) -> None:
        self.replies = replies
        self.inputs: list[list[Message]] = []

    async def generate(
        self, route: Route, system: str, messages: Sequence[Message], schema: type[BaseModel] | None
    ) -> ProviderReply:
        self.inputs.append(list(messages))
        value = self.replies.pop(0)
        if isinstance(value, Exception):
            raise value
        return ProviderReply(value, 10, 5)


def gateway(generator: Adapter, verifier: Adapter) -> Gateway:
    route = Route(provider="deepseek", model="deepseek-test", family="deepseek")
    return Gateway(
        Routing(
            tiers={
                "free": {
                    "graph": [route],
                    "items": [route],
                    "verify": [Route(provider="gemini", model="gemini-test", family="gemini")],
                }
            }
        ),
        {"deepseek": generator, "gemini": verifier},
    )


def graph() -> str:
    return json.dumps(
        {
            "concepts": [
                {
                    "slug": "program",
                    "name_vi": "Program",
                    "name_en": "Program",
                    "sources": [material()[0].source_uri],
                }
            ],
            "edges": [],
        }
    )


def test_preflight_never_calls_models() -> None:
    gen, verify = Adapter([]), Adapter([])
    report = asyncio.run(run(material(), "goal", "free", gateway=gateway(gen, verify)))
    assert report["status"] == "preflight_only" and report["attempts"] == []
    assert gen.inputs == verify.inputs == []


def test_blind_input_has_no_generator_answer_or_status() -> None:
    item: Item = generated().items[0]
    payload = blind_input(item, material())
    assert payload["options"] == ["Instructions", "Data"]
    assert set(payload) == {"question_vi", "options", "sources"}
    assert all(
        key not in json.dumps(payload) for key in ("correct", "misconception", "needs_review")
    )


@pytest.mark.parametrize("accepted", [True, False])
def test_canonical_smoke_does_not_publish_even_if_blind_answer_matches(accepted: bool) -> None:
    gen = Adapter([graph(), generated().model_dump_json()])
    verdict = json.dumps(
        {
            "answer": 0 if accepted else 1,
            "supported": True,
            "reason_vi": "Source",
            "chunk_ids": ["c1"],
        }
    )
    verify = Adapter([verdict, verdict])
    report = asyncio.run(run(material(), "goal", "free", live=True, gateway=gateway(gen, verify)))
    assert report["status"] == ("ok" if accepted else "verifier_rejected")
    assert report["published_items"] == 0
    assert all(item["status"] == "needs_review" for item in report["items"]["items"])
    assert report["input_tokens"] == 40 and report["output_tokens"] == 20
    assert [a["route"]["family"] for a in report["attempts"]] == [
        "deepseek",
        "deepseek",
        "gemini",
        "gemini",
    ]
    assert all(
        "correct" not in json.dumps([m.model_dump() for m in request]) for request in verify.inputs
    )


def test_foreign_item_citation_stops_before_verifier() -> None:
    items = generated()
    items.items[0].chunk_ids = ["foreign"]
    gen, verify = Adapter([graph(), items.model_dump_json()]), Adapter([])
    report = asyncio.run(run(material(), "goal", "free", live=True, gateway=gateway(gen, verify)))
    assert report["status"] == "failed" and report["error_type"] == "ValueError"
    assert verify.inputs == []


def test_provider_failure_is_incomplete_and_sanitized() -> None:
    gen, verify = Adapter([ProviderError("key_missing")]), Adapter([])
    report = asyncio.run(run(material(), "goal", "free", live=True, gateway=gateway(gen, verify)))
    assert report["status"] == "failed" and report["error_type"] == "GatewayError"
    assert report["attempts"][0]["status"] == "provider_error"
    assert report["published_items"] == 0 and verify.inputs == []
