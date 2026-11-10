"""Offline runner resilience; fake replies do not certify real golden content."""

import asyncio
import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app.content import verify_batch as batch
from app.llm.gateway import Gateway, Message, ProviderReply, Route, Routing
from app.llm.providers import HTTPProviderError
from tests.content.fakes import topic


class Provider:
    def __init__(self) -> None:
        self.calls = 0
        self.failure: HTTPProviderError | None = None
        self.fail_after = 100

    async def generate(
        self, route: Route, system: str, messages: Sequence[Message], schema: type[BaseModel] | None
    ) -> ProviderReply:
        self.calls += 1
        if self.failure and self.calls > self.fail_after:
            raise self.failure
        payload = json.loads(messages[0].content)
        assert set(payload) == {"question", "options", "chunks"}
        _, _, _, items = topic()
        item = next(i for i in items if i.prompt_vi == payload["question"])
        correct = next(n for n, o in enumerate(item.options) if o.id == item.answer_id)
        chunk = payload["chunks"][0]
        return ProviderReply(
            json.dumps(
                {
                    "supported": True,
                    "selected_option_id": f"choice-{correct}",
                    "unique_answer": True,
                    "ambiguous": False,
                    "multiple_correct": False,
                    "insufficient_evidence": False,
                    "evidence": [{"chunk_id": chunk["chunk_id"], "passage_id": "source-quote-0"}],
                    "reason": "fake test only",
                }
            ),
            10,
            5,
        )


def setup(monkeypatch: pytest.MonkeyPatch, count: int = 2) -> tuple[Provider, list[float]]:
    sources, chunks, graph, items = topic()
    monkeypatch.setattr(batch, "load_topic", lambda path: (sources, chunks, graph, items[:count]))
    provider = Provider()
    gateway = Gateway(
        Routing(
            tiers={
                "pro": {"verify": [Route(provider="gemini", model="gemini-test", family="gemini")]}
            }
        ),
        {"gemini": provider},
    )
    monkeypatch.setattr(batch, "default_gateway", lambda: gateway)
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    return provider, waits


def execute(path: Path, retries: int = 0) -> dict[str, Any]:
    return asyncio.run(batch.run(Path("unused"), path, 0, retries))


def test_single_probe_saves_audit_before_continuing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider, _ = setup(monkeypatch)
    path = tmp_path / "checkpoint.json"
    first = asyncio.run(batch.run(Path("unused"), path, 0, 0, max_items=1))
    assert provider.calls == 1
    assert first["summary"]["verified"] == 1
    assert len(first["items"]) == 1
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert next(iter(saved["items"].values()))["result"]["verification"]["evidence"]
    second = execute(path)
    assert provider.calls == 2
    assert second["summary"]["reused_verified"] == 1


def test_resume_preserves_success_and_evaluation_flips_only_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider, _ = setup(monkeypatch)
    provider.failure = HTTPProviderError(429, 30, "quota")
    provider.fail_after = 1
    path = tmp_path / "checkpoint.json"
    first = execute(path)
    assert first["summary"]["verified"] == 1
    assert first["blocked"]["kind"] == "quota"
    assert provider.calls == 2
    execute(path)
    assert provider.calls == 2  # Retry-After persists across process resumes.
    monkeypatch.setattr(time, "time", lambda: first["resume_after_epoch"] + 1)
    provider.failure = None
    second = execute(path)
    assert provider.calls == 3  # first successful item was not called again
    assert second["summary"]["verified"] == 2
    assert second["summary"]["reused_verified"] == 1
    assert second["evaluation_summary"]["wrong_blocked"] == 2
    assert second["evaluation_summary"]["wrong_allowed"] == 0
    assert second["evaluation_summary"]["correct_blocked"] == 0


def test_retry_is_finite_and_honors_retry_after(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    provider, waits = setup(monkeypatch, 1)
    provider.failure, provider.fail_after = HTTPProviderError(429, 120, "transient"), 0
    result = execute(tmp_path / "checkpoint.json", retries=2)
    assert provider.calls == 3
    assert waits == [120, 120]
    assert result["evaluation_summary"]["unfinished"] == 2
    assert result["evaluation_summary"]["wrong_blocked"] == 0
    assert result["summary"]["input_tokens"] is None


def test_changed_chunk_invalidates_resume(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    provider, _ = setup(monkeypatch, 1)
    path = tmp_path / "checkpoint.json"
    execute(path)
    sources, chunks, graph, items = topic()
    chunks[0] = chunks[0].model_copy(update={"content": chunks[0].content + " "})
    monkeypatch.setattr(batch, "load_topic", lambda path: (sources, chunks, graph, items[:1]))
    result = execute(path)
    assert provider.calls == 2
    assert result["summary"]["reused_verified"] == 0
