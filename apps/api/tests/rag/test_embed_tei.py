"""TeiEmbedder against a fake TEI server: request shape, batching, retries, bad responses."""

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from app.rag.embed import (
    EMBEDDING_DIM,
    EmbeddingError,
    TeiEmbedder,
    ThreadedEmbedder,
    make_embedder,
)
from tests.rag.fixtures import FakeEmbedder

Handler = Callable[[httpx.Request], httpx.Response]


def _vectors(n: int, dim: int = EMBEDDING_DIM) -> list[list[float]]:
    return [[float(i)] * dim for i in range(n)]


def _server(calls: list[httpx.Request], status: int = 200) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        inputs = json.loads(request.content)["inputs"]
        return httpx.Response(status, json=_vectors(len(inputs)))

    return handle


def _embedder(handler: Handler, **kwargs: object) -> TeiEmbedder:
    transport = httpx.MockTransport(handler)
    return TeiEmbedder(
        "http://tei:80/",
        backoff=0,
        client=httpx.Client(transport=transport),
        async_client=httpx.AsyncClient(transport=transport),
        **kwargs,  # type: ignore[arg-type]
    )


def test_request_shape_and_sync_result() -> None:
    calls: list[httpx.Request] = []
    out = _embedder(_server(calls)).embed(["xin chào", "hello"])
    assert len(out) == 2 and len(out[0]) == EMBEDDING_DIM
    (request,) = calls
    assert str(request.url) == "http://tei/embed"  # trailing slash tolerated, default port dropped
    assert json.loads(request.content) == {
        "inputs": ["xin chào", "hello"],
        "normalize": True,
        "truncate": True,
    }


def test_async_matches_sync() -> None:
    calls: list[httpx.Request] = []
    emb = _embedder(_server(calls))
    assert asyncio.run(emb.aembed(["a", "b", "c"])) == emb.embed(["a", "b", "c"])


def test_texts_are_nfc_normalised_before_sending() -> None:
    calls: list[httpx.Request] = []
    decomposed = "Việt"  # "Việt" as base letters + combining marks
    _embedder(_server(calls)).embed([decomposed])
    assert json.loads(calls[0].content)["inputs"] == ["Việt"]


def test_large_input_is_split_into_batches_in_order() -> None:
    calls: list[httpx.Request] = []
    out = asyncio.run(_embedder(_server(calls), batch_size=4).aembed([str(i) for i in range(10)]))
    assert [len(json.loads(c.content)["inputs"]) for c in calls] == [4, 4, 2]
    assert len(out) == 10


def test_empty_input_makes_no_request() -> None:
    calls: list[httpx.Request] = []
    emb = _embedder(_server(calls))
    assert emb.embed([]) == [] and asyncio.run(emb.aembed([])) == []
    assert calls == []


def test_api_key_is_sent_as_a_bearer_token() -> None:
    calls: list[httpx.Request] = []
    _embedder(_server(calls), api_key="secret").embed(["x"])
    assert calls[0].headers["authorization"] == "Bearer secret"
    calls.clear()
    _embedder(_server(calls)).embed(["x"])
    assert "authorization" not in calls[0].headers


@pytest.mark.parametrize("use_async", [False, True])
def test_busy_server_is_retried_then_succeeds(use_async: bool) -> None:
    statuses = iter([429, 503, 200])
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        return _server(calls, next(statuses))(request)

    emb = _embedder(handle)
    out = asyncio.run(emb.aembed(["x"])) if use_async else emb.embed(["x"])
    assert len(out) == 1 and len(calls) == 3


@pytest.mark.parametrize("use_async", [False, True])
def test_gives_up_after_max_retries(use_async: bool) -> None:
    calls: list[httpx.Request] = []
    emb = _embedder(_server(calls, 503), max_retries=2)
    with pytest.raises(EmbeddingError, match="503"):
        asyncio.run(emb.aembed(["x"])) if use_async else emb.embed(["x"])
    assert len(calls) == 3  # first try + 2 retries


def test_client_error_is_not_retried() -> None:
    calls: list[httpx.Request] = []
    with pytest.raises(EmbeddingError, match="413"):
        _embedder(_server(calls, 413)).embed(["x"])
    assert len(calls) == 1


def test_connection_failure_becomes_embedding_error() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(EmbeddingError, match="unreachable"):
        _embedder(down, max_retries=1).embed(["x"])
    with pytest.raises(EmbeddingError, match="unreachable"):
        asyncio.run(_embedder(down, max_retries=1).aembed(["x"]))


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "nope"},  # not a list
        _vectors(1),  # wrong count for 2 inputs
        _vectors(2, dim=768),  # wrong dimension (a different model: needs a re-index)
    ],
)
def test_unusable_responses_are_rejected(payload: object) -> None:
    emb = _embedder(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(EmbeddingError):
        emb.embed(["a", "b"])


def test_invalid_json_is_rejected() -> None:
    emb = _embedder(lambda request: httpx.Response(200, content=b"<html>"))
    with pytest.raises(EmbeddingError, match="invalid JSON"):
        emb.embed(["a"])


def test_threaded_embedder_gives_a_sync_embedder_the_async_interface() -> None:
    fake = FakeEmbedder()
    wrapped = ThreadedEmbedder(fake)
    assert wrapped.dim == fake.dim
    assert asyncio.run(wrapped.aembed(["x"])) == fake.embed(["x"])


def test_make_embedder_picks_the_backend() -> None:
    assert isinstance(make_embedder("tei", tei_url="http://tei"), TeiEmbedder)
    with pytest.raises(ValueError, match="TEI_URL"):
        make_embedder("tei")
    with pytest.raises(ValueError, match="unknown embedding backend"):
        make_embedder("openai")
