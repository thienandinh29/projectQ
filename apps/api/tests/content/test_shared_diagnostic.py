import asyncio
import json
from pathlib import Path

import pytest

from app.content.artifacts import load_topic
from app.content.models import digest
from app.content.shared_diagnostic import MANIFEST, diagnose
from app.guardrails.answerability import SYSTEM, Verdict, blind_request
from app.llm.gateway import Message, Route
from app.llm.providers import _gemini_payload, _thinking_config, diagnostic_transport_timeout


def test_manifest_preserves_exact_shared_v2_diagnostic_request() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    _, chunks, _, items = load_topic(Path("../../data/golden/python-conditions"))
    payload = blind_request(items[0], chunks).model_dump(
        mode="json", exclude={"chunks": {"__all__": {"evidence_options"}}}
    )
    assert set(payload) == {"question", "options", "chunks"}
    assert all(set(o) == {"id", "label"} for o in payload["options"])
    route = Route(provider="gemini", family="gemini", model=manifest["model"])
    body = _gemini_payload(
        SYSTEM, [Message(role="user", content=json.dumps(payload, ensure_ascii=False))], Verdict
    )
    _thinking_config(body, route)
    assert manifest["request"] == body
    assert (
        digest({"provider": "gemini", "version": "v1beta", "model": route.model, "request": body})
        == manifest["request_fingerprint"]
    )


def test_existing_diagnostic_refuses_repeat_without_network(tmp_path: Path) -> None:
    output = tmp_path / "record.json"
    output.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing another attempt"):
        asyncio.run(diagnose(output))


def test_v3_request_refuses_frozen_v2_manifest_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_network(*args: object, **kwargs: object) -> None:
        pytest.fail("Changed shared request must be rejected before network access")

    monkeypatch.setattr("app.content.shared_diagnostic.httpx.AsyncClient", unexpected_network)
    with pytest.raises(ValueError, match="Shared input/model differs"):
        asyncio.run(diagnose(tmp_path / "new.json"))


def test_diagnostic_timeout_requires_explicit_bounded_scope() -> None:
    from app.llm.providers import _diagnostic_timeout

    assert _diagnostic_timeout.get() == 30
    with diagnostic_transport_timeout(90):
        assert _diagnostic_timeout.get() == 90
    assert _diagnostic_timeout.get() == 30
    with pytest.raises(ValueError), diagnostic_transport_timeout(91):
        pytest.fail("must not enter an unbounded diagnostic")
