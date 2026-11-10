import asyncio
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.llm.gateway import Message, ProviderError, Route
from app.llm.providers import (
    BedrockAdapter,
    DeepSeekAdapter,
    GeminiAdapter,
    OpenRouterAdapter,
    VertexAdapter,
)
from tests.llm.test_gateway import Answer


def test_vertex_payload_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("VERTEX_LOCATION", "global")
    captured: dict[str, Any] = {}

    async def post(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured.update(url=url, token=token, payload=payload)
        return {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2},
        }

    with (
        patch("app.llm.providers._post", post),
        patch.object(VertexAdapter, "_token", return_value="fake"),
    ):
        reply = asyncio.run(
            VertexAdapter().generate(
                Route(provider="vertex", model="gemini-test", family="gemini"),
                "system",
                [Message(role="user", content="q"), Message(role="assistant", content="a")],
                None,
            )
        )
    assert captured["url"].startswith("https://aiplatform.googleapis.com/v1/projects/test-project/")
    assert captured["payload"]["contents"][1]["role"] == "model"
    assert reply.text == "ok" and reply.input_tokens == 4


def test_openrouter_truncation_is_not_a_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")

    async def post(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}

    with patch("app.llm.providers._post", post), pytest.raises(ProviderError, match="incomplete"):
        asyncio.run(
            OpenRouterAdapter().generate(
                Route(provider="openrouter", model="anthropic/claude-test", family="claude"),
                "s",
                [Message(role="user", content="q")],
                None,
            )
        )


def test_bedrock_converse_payload_and_client_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_REGION", "ap-southeast-1")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    client = MagicMock()
    client.converse.return_value = {
        "stopReason": "end_turn",
        "output": {"message": {"content": [{"text": "ok"}]}},
        "usage": {"inputTokens": 3, "outputTokens": 1},
    }
    session = MagicMock()
    session.client.return_value = client
    boto3 = SimpleNamespace(Session=MagicMock(return_value=session))
    config = SimpleNamespace(Config=MagicMock(return_value="fake-config"))
    with patch("app.llm.providers.importlib.import_module", side_effect=[boto3, config]):
        reply = asyncio.run(
            BedrockAdapter().generate(
                Route(provider="bedrock", model="claude-test", family="claude"),
                "system",
                [Message(role="user", content="question")],
                None,
            )
        )
    assert reply.text == "ok" and reply.input_tokens == 3
    client.converse.assert_called_once_with(
        modelId="claude-test",
        system=[{"text": "system"}],
        messages=[{"role": "user", "content": [{"text": "question"}]}],
        inferenceConfig={"maxTokens": 4096},
    )
    client.close.assert_called_once()


def test_deepseek_json_payload_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-private-key")
    captured: dict[str, Any] = {}

    async def post(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        captured.update(url=url, token=token, payload=payload)
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"count":3}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        }

    with patch("app.llm.providers._post", post):
        reply = asyncio.run(
            DeepSeekAdapter().generate(
                Route(provider="deepseek", model="deepseek-flash", family="deepseek"),
                "Return JSON",
                [Message(role="user", content="q")],
                Answer,
            )
        )
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["token"] == "fake-private-key"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert '"count"' in captured["payload"]["messages"][0]["content"]
    assert reply.text == '{"count":3}' and reply.input_tokens == 12 and reply.output_tokens == 5


@pytest.mark.parametrize(
    "data,reason",
    [
        ({"choices": [{"finish_reason": "length"}]}, "incomplete"),
        ({"choices": []}, "invalid"),
        ({"choices": [{"finish_reason": "stop", "message": {"content": None}}]}, "invalid"),
    ],
)
def test_deepseek_bad_responses_fail(
    monkeypatch: pytest.MonkeyPatch, data: dict[str, Any], reason: str
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")

    async def post(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return data

    with patch("app.llm.providers._post", post), pytest.raises(ProviderError, match=reason):
        asyncio.run(
            DeepSeekAdapter().generate(
                Route(provider="deepseek", model="deepseek-flash", family="deepseek"),
                "s",
                [Message(role="user", content="q")],
                None,
            )
        )


def test_deepseek_missing_key_does_not_call_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with (
        patch("app.llm.providers._post") as post,
        pytest.raises(ProviderError, match="key_missing"),
    ):
        asyncio.run(
            DeepSeekAdapter().generate(
                Route(provider="deepseek", model="deepseek-flash", family="deepseek"),
                "s",
                [Message(role="user", content="q")],
                None,
            )
        )
    post.assert_not_called()


def test_gemini_key_header_payload_and_thinking_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "private-gemini-test")
    captured: dict[str, Any] = {}
    client_type = httpx.AsyncClient

    def handle(request: httpx.Request) -> httpx.Response:
        import json

        captured.update(
            url=str(request.url), headers=request.headers, payload=json.loads(request.content)
        )
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"thought": True, "text": "internal summary"},
                                {"text": '{"count":3}'},
                            ]
                        },
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 4,
                    "thoughtsTokenCount": 7,
                },
            },
        )

    with patch(
        "app.llm.providers.httpx.AsyncClient",
        side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handle), **kw),
    ):
        reply = asyncio.run(
            GeminiAdapter().generate(
                Route(provider="gemini", model="gemini-test", family="gemini"),
                "Return JSON",
                [Message(role="user", content="q"), Message(role="assistant", content="a")],
                Answer,
            )
        )
    assert captured["headers"]["x-goog-api-key"] == "private-gemini-test"
    assert "authorization" not in captured["headers"]
    assert "private-gemini-test" not in captured["url"] and "?" not in captured["url"]
    assert captured["payload"]["contents"][1]["role"] == "model"
    assert captured["payload"]["generationConfig"]["responseMimeType"] == "application/json"
    assert reply.text == '{"count":3}' and reply.input_tokens == 10 and reply.output_tokens == 11


@pytest.mark.parametrize("status", [400, 403, 429, 503])
def test_gemini_http_errors_hide_credentials(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "private-gemini-test")
    client_type = httpx.AsyncClient

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": "private-gemini-test"}})

    with (
        patch(
            "app.llm.providers.httpx.AsyncClient",
            side_effect=lambda **kw: client_type(transport=httpx.MockTransport(handle), **kw),
        ),
        pytest.raises(ProviderError, match=f"http_{status}") as error,
    ):
        asyncio.run(
            GeminiAdapter().generate(
                Route(provider="gemini", model="gemini-test", family="gemini"),
                "s",
                [Message(role="user", content="q")],
                None,
            )
        )
    assert "private-gemini-test" not in str(error.value)
    assert error.value.retryable == (status in (429, 503))


@pytest.mark.parametrize(
    "data,reason",
    [
        ({"candidates": [{"finishReason": "MAX_TOKENS"}]}, "incomplete"),
        ({"candidates": []}, "invalid"),
    ],
)
def test_gemini_invalid_or_truncated_output(
    monkeypatch: pytest.MonkeyPatch, data: dict[str, Any], reason: str
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "fake")

    async def post(
        url: str, token: str, payload: dict[str, Any], *, api_key: bool = False
    ) -> dict[str, Any]:
        assert api_key
        return data

    with patch("app.llm.providers._post", post), pytest.raises(ProviderError, match=reason):
        asyncio.run(
            GeminiAdapter().generate(
                Route(provider="gemini", model="gemini-test", family="gemini"),
                "s",
                [Message(role="user", content="q")],
                None,
            )
        )


def test_gemini_missing_key_does_not_call_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with (
        patch("app.llm.providers._post") as post,
        pytest.raises(ProviderError, match="key_missing"),
    ):
        asyncio.run(
            GeminiAdapter().generate(
                Route(provider="gemini", model="gemini-test", family="gemini"),
                "s",
                [Message(role="user", content="q")],
                None,
            )
        )
    post.assert_not_called()


@pytest.mark.parametrize("provider", ["deepseek", "gemini"])
def test_real_adapter_truncation_is_non_retryable(
    monkeypatch: pytest.MonkeyPatch, provider: Literal["deepseek", "gemini"]
) -> None:
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", "fake")

    async def post(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return (
            {
                "choices": [{"finish_reason": "length"}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 4096},
            }
            if provider == "deepseek"
            else {
                "candidates": [{"finishReason": "MAX_TOKENS"}],
                "usageMetadata": {
                    "promptTokenCount": 9,
                    "candidatesTokenCount": 4090,
                    "thoughtsTokenCount": 6,
                },
            }
        )

    adapter = DeepSeekAdapter() if provider == "deepseek" else GeminiAdapter()
    with patch("app.llm.providers._post", post), pytest.raises(ProviderError) as error:
        asyncio.run(
            adapter.generate(
                Route(provider=provider, model=f"{provider}-test", family=provider),
                "s",
                [Message(role="user", content="q")],
                None,
            )
        )
    assert not error.value.retryable
    assert error.value.reply is not None
    assert (error.value.reply.input_tokens, error.value.reply.output_tokens) == (9, 4096)


def test_graph_budget_and_gemini_thinking_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.llm.gateway import Gateway, Routing, generation_limits, verification_scope

    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    payloads: list[dict[str, Any]] = []

    async def post(url: str, token: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        payloads.append(payload)
        if "deepseek" in url:
            return {"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}]}
        return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "ok"}]}}]}

    gateway = Gateway(
        Routing(
            tiers={
                "free": {
                    "graph": [Route(provider="deepseek", model="deepseek-test", family="deepseek")],
                    "items": [Route(provider="deepseek", model="deepseek-test", family="deepseek")],
                    "verify": [Route(provider="gemini", model="gemini-3.8-flash", family="gemini")],
                }
            }
        ),
        {"deepseek": DeepSeekAdapter(), "gemini": GeminiAdapter()},
    )

    async def run() -> None:
        await gateway.complete("graph", "free", "s", [{"role": "user", "content": "q"}])
        await gateway.complete("items", "free", "s", [{"role": "user", "content": "q"}])
        with verification_scope("deepseek"):
            await gateway.complete("verify", "free", "s", [{"role": "user", "content": "q"}])
        assert generation_limits().max_tokens == 4096

    with patch("app.llm.providers._post", post):
        asyncio.run(run())
    assert payloads[0]["max_tokens"] == 16384
    assert payloads[1]["max_tokens"] == 16384
    assert payloads[2]["generationConfig"] == {
        "maxOutputTokens": 8192,
        "thinkingConfig": {"thinkingLevel": "LOW"},
    }


def test_deepseek_long_multibyte_context_is_rejected_before_paid_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake")
    with (
        patch("app.llm.providers._post") as post,
        pytest.raises(ProviderError, match="context_budget_exceeded") as error,
    ):
        asyncio.run(
            DeepSeekAdapter().generate(
                Route(provider="deepseek", model="deepseek-flash", family="deepseek"),
                "s",
                [Message(role="user", content="ọ" * 400_000)],
                None,
            )
        )
    assert not error.value.retryable
    post.assert_not_called()
