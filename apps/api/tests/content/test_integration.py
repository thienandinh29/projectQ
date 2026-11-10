"""Offline lane-boundary tests. Fake provider replies never certify golden quality."""

import asyncio
import json
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.config import Settings
from app.content.gateway import P3Gateway
from app.content.integration import contract_graph, contract_item_sets, pipeline_items
from app.guardrails.answerability import verify_item
from app.llm.gateway import Gateway, Message, ProviderReply, Route, Routing
from app.main import create_app
from tests.content.fakes import topic


class FakeProvider:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.routes: list[str] = []
        self.messages: list[str] = []

    async def generate(
        self,
        route: Route,
        system: str,
        messages: Sequence[Message],
        schema: type[BaseModel] | None,
    ) -> ProviderReply:
        self.routes.append(route.model)
        self.messages.extend(m.content for m in messages)
        return ProviderReply(self.reply)


@pytest.mark.parametrize("generator_family", ["gemini", "gpt"])
def test_p3_actual_completion_metadata_and_family_scope_drive_p4_gate(
    generator_family: str,
) -> None:
    _, chunks, _, items = topic()
    item = items[0].model_copy(
        update={
            "generator": items[0].generator.model_copy(
                update={"family": generator_family, "identity_source": "gateway"}
            )
        }
    )
    provider = FakeProvider(
        json.dumps(
            {
                "supported": True,
                "selected_option_id": next(
                    f"choice-{i}" for i, o in enumerate(item.options) if o.correct
                ),
                "unique_answer": True,
                "ambiguous": False,
                "multiple_correct": False,
                "insufficient_evidence": False,
                "evidence": [{"chunk_id": str(chunks[0].chunk_id), "passage_id": "source-quote-0"}],
                "reason": "Synthetic unit-test provider reply, not real verification.",
            }
        )
    )
    routing = Routing(
        tiers={
            "pro": {
                "verify": [
                    *(
                        [Route(provider="vertex", model="gemini-same-family", family="gemini")]
                        if generator_family == "gemini"
                        else []
                    ),
                    Route(provider="bedrock", model="claude-independent", family="claude"),
                ]
            }
        }
    )
    real_gateway_code = Gateway(routing, {"vertex": provider, "bedrock": provider})
    adapter = P3Gateway(real_gateway_code.complete_with_metadata)
    verified = asyncio.run(verify_item(item, chunks, adapter))
    assert verified.status == "verified"
    assert provider.routes == ["claude-independent"]
    assert verified.verification is not None and verified.verification.verifier is not None
    assert verified.verification.verifier.model == "claude-independent"
    assert len(pipeline_items([verified], chunks)) == 1
    assert "answer_id" not in provider.messages[0]
    assert "generator" not in provider.messages[0]
    # Changing the source invalidates release to P3 even if DB status still says verified.
    changed = [chunks[0].model_copy(update={"content": "Đoạn nguồn đã thay đổi."})]
    assert pipeline_items([verified], changed) == []


@pytest.mark.parametrize("slug", ["python-conditions", "fractions", "cell-basics"])
def test_p4_golden_exports_match_p1_canonical_models(slug: str) -> None:
    _, chunks, graph, items = topic(slug)
    assert len(contract_graph(graph).concepts) == 5
    assert sum(len(group.items) for group in contract_item_sets(items)) == 15
    assert pipeline_items(items, chunks) == []


def test_p2_application_mounts_all_p3_routers_without_fixture_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NoDatabasePool:
        def close(self) -> None:
            pass

    monkeypatch.setattr("app.main.create_pool", lambda url: NoDatabasePool())
    app = create_app(Settings(allow_unauthenticated_local_dev=True, _env_file=None))
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]
        for path in (
            "/topics",
            "/uploads",
            "/graph",
            "/placement/next",
            "/next-item",
            "/attempts",
            "/tutor/hint",
            "/ask",
            "/reviews/due",
            "/exam-plan",
        ):
            assert path in paths
        response = client.post(
            "/topics", json={"goal_vi": "Python", "mode": "quick", "tier": "free"}
        )
        assert response.status_code == 503
        assert "fixture" not in response.headers.get("x-nodetrail-backend", "")
        assert (
            client.get("/next-item", params={"learner_id": "u", "subject": "python"}).status_code
            == 503
        )
