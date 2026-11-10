import asyncio

import pytest

from app.llm.gateway import Gateway, ProviderError
from app.llm.smoke import configuration, probe, probe_pair
from tests.llm.test_gateway import Fake, routes


def test_configuration_never_reveals_environment_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-for-logs")
    report = configuration(routes())
    assert report and all(row["model_configured"] for row in report)
    assert "not-for-logs" not in str(report)


def test_provider_probe_does_not_hide_failure_with_fallback() -> None:
    fake = Fake(['{"text_vi":"Kết nối thành công."}'])
    report = asyncio.run(probe(Gateway(routes(), {"vertex": fake}), "vertex", "free", "items"))
    assert report["provider"] == "vertex" and report["status"] == "ok"
    assert fake.models == ["gemini-test"]


def test_default_live_pair_requires_independent_verification_and_records_each_call() -> None:
    fake = Fake(['{"text_vi":"Generated"}', '{"text_vi":"Independent"}'])
    report = asyncio.run(probe_pair(Gateway(routes(), {"vertex": fake, "bedrock": fake}), "free"))
    assert report["status"] == "ok" and report["generator_answer_excluded"]
    assert report["generator"]["family"] != report["verifier"]["family"]
    assert len(report["attempts"]) == len(report["successful_calls"]) == 2
    assert report["attempts"][0]["input_tokens"] == 10
    assert all(a["latency_ms"] >= 0 for a in report["successful_calls"])


def test_pair_failure_keeps_attempt_errors() -> None:
    fake = Fake([ProviderError("key_missing")])
    report = asyncio.run(probe_pair(Gateway(routes(), {"vertex": fake}), "free"))
    assert report["status"] == "failed"
    assert report["attempts"][0]["error_code"] == "key_missing"


def test_live_cli_defaults_to_the_pair_not_single_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from app.llm.smoke import main

    called: list[str] = []

    async def pair(gateway: Gateway, tier: str) -> dict[str, str]:
        called.append(tier)
        return {"status": "ok"}

    monkeypatch.setattr("sys.argv", ["smoke", "--live"])
    monkeypatch.setattr(
        "app.config.get_settings", lambda: SimpleNamespace(export_worker_environment=lambda: None)
    )
    monkeypatch.setattr("app.llm.smoke.default_gateway", lambda: Gateway(routes(), {}))
    monkeypatch.setattr("app.llm.smoke.probe_pair", pair)
    main()
    assert called == ["free"]
