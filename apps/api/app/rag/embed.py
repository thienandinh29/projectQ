"""Text embeddings behind small protocols, so tests use a fake and never load the model.

Two shapes of the same thing: `Embedder` (sync; bulk indexing and scripts) and `AsyncEmbedder`
(the API and the worker, which must never block the event loop). In production only the TEI
container holds bge-m3; `TeiEmbedder` talks to it over HTTP and implements both.
"""

import asyncio
import importlib
import time
import unicodedata
from collections.abc import Sequence
from typing import Any, Protocol

import httpx

EMBEDDING_DIM = 1024  # must match chunks.embedding halfvec(1024)


class Embedder(Protocol):
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class AsyncEmbedder(Protocol):
    dim: int

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddingError(RuntimeError):
    """The embedding service failed or answered with something unusable."""


# TEI answers 429 when its queue is full and 503 while loading; these are worth a retry.
_RETRY_STATUSES = frozenset({429, 502, 503, 504})


class TeiEmbedder:
    """BAAI/bge-m3 through a Hugging Face Text Embeddings Inference server (`POST /embed`).

    Also works with a Hugging Face Inference Endpoint running TEI: pass its URL and `api_key`.
    Vectors come back L2-normalised (`normalize`), so cosine distance equals the index metric.
    Inputs longer than the model's limit are truncated by the server instead of rejected.
    """

    dim = EMBEDDING_DIM

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        batch_size: int = 32,  # TEI's default max client batch size
        timeout: float = 60.0,
        max_retries: int = 4,
        backoff: float = 0.5,  # seconds; doubles per retry
        client: httpx.Client | None = None,
        async_client: httpx.AsyncClient | None = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self._url = base_url.rstrip("/") + "/embed"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._batch_size = batch_size
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff = backoff
        self._client = client
        self._async_client = async_client

    # -- sync (bulk indexing) -------------------------------------------------------------------

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        client = self._client or httpx.Client(timeout=self._timeout)
        self._client = client
        out: list[list[float]] = []
        for batch in self._batches(texts):
            out.extend(self._parse(self._post_sync(client, batch), len(batch)))
        return out

    def _post_sync(self, client: httpx.Client, batch: list[str]) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = client.post(self._url, json=_body(batch), headers=self._headers)
            except httpx.TransportError as exc:
                if attempt == self._max_retries:
                    raise EmbeddingError(f"TEI unreachable: {exc}") from exc
            else:
                if response.status_code not in _RETRY_STATUSES or attempt == self._max_retries:
                    return response
            time.sleep(self._backoff * 2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    def close(self) -> None:
        if self._client is not None:
            self._client.close()

    # -- async (API and worker) -----------------------------------------------------------------

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        client = self._async_client or httpx.AsyncClient(timeout=self._timeout)
        self._async_client = client
        out: list[list[float]] = []
        for batch in self._batches(texts):
            out.extend(self._parse(await self._post_async(client, batch), len(batch)))
        return out

    async def _post_async(self, client: httpx.AsyncClient, batch: list[str]) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = await client.post(self._url, json=_body(batch), headers=self._headers)
            except httpx.TransportError as exc:
                if attempt == self._max_retries:
                    raise EmbeddingError(f"TEI unreachable: {exc}") from exc
            else:
                if response.status_code not in _RETRY_STATUSES or attempt == self._max_retries:
                    return response
            await asyncio.sleep(self._backoff * 2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()

    # -- shared ---------------------------------------------------------------------------------

    def _batches(self, texts: Sequence[str]) -> list[list[str]]:
        clean = [unicodedata.normalize("NFC", t) for t in texts]
        return [clean[i : i + self._batch_size] for i in range(0, len(clean), self._batch_size)]

    def _parse(self, response: httpx.Response, expected: int) -> list[list[float]]:
        if response.status_code != 200:
            raise EmbeddingError(f"TEI answered {response.status_code}: {response.text[:200]}")
        try:
            vectors = response.json()
        except ValueError as exc:
            raise EmbeddingError("TEI answered with invalid JSON") from exc
        if not isinstance(vectors, list) or len(vectors) != expected:
            raise EmbeddingError(f"TEI returned the wrong number of vectors (wanted {expected})")
        if any(not isinstance(v, list) or len(v) != self.dim for v in vectors):
            raise EmbeddingError(f"TEI returned vectors that are not {self.dim}-dimensional")
        return [[float(x) for x in v] for v in vectors]


def _body(batch: list[str]) -> dict[str, Any]:
    return {"inputs": batch, "normalize": True, "truncate": True}


class ThreadedEmbedder:
    """Gives a sync `Embedder` (the local model, or a test fake) the async interface."""

    def __init__(self, inner: Embedder) -> None:
        self._inner = inner
        self.dim = inner.dim

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._inner.embed, texts)


class BgeM3Embedder:
    """BAAI/bge-m3 dense vectors: multilingual, so Vietnamese questions match English text.

    Needs the optional `embed` extra (`uv sync --extra embed`). First use downloads ~2.3 GB.
    Uses an NVIDIA GPU when PyTorch can see one (see `pick_device`), otherwise the CPU.
    """

    model_name = "BAAI/bge-m3"
    dim = EMBEDDING_DIM

    def __init__(self, batch_size: int | None = None, device: str | None = None) -> None:
        # Imported here so the API and CI run without PyTorch installed.
        from sentence_transformers import SentenceTransformer

        self.device = device or pick_device()
        # A GPU digests big batches far faster; on a CPU big batches only cost memory.
        self._batch_size = batch_size or (64 if self.device.startswith("cuda") else 16)
        self._model: Any = SentenceTransformer(self.model_name, device=self.device)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            batch_size=self._batch_size,
            normalize_embeddings=True,  # unit length, so cosine distance == the HNSW index metric
            show_progress_bar=len(texts) > 64,
        )
        return [[float(x) for x in v] for v in vectors]


def pick_device() -> str:
    """ "cuda" when PyTorch can see an NVIDIA GPU, else "cpu" (also when PyTorch is not installed).

    A pip install of PyTorch on Windows is CPU-only unless the CUDA build is chosen on purpose, so a
    GPU machine can still land on "cpu": check `device` on the embedder if indexing is slow.
    """
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return "cpu"
    return "cuda" if torch.cuda.is_available() else "cpu"


def to_pgvector(vector: Sequence[float]) -> str:
    """pgvector text literal; avoids a numpy-based adapter dependency."""
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"


def make_embedder(
    backend: str = "tei", *, tei_url: str | None = None, api_key: str | None = None
) -> TeiEmbedder | BgeM3Embedder:
    """Build the embedder for `EMBEDDING_BACKEND`.

    `tei`: the TEI container (or a Hugging Face Inference Endpoint running TEI), the default.
    `local`: bge-m3 in this process; needs the `embed` extra, for a laptop without TEI.
    A managed multilingual API produces different vectors, so adding one means re-indexing the
    library; it is not implemented here.
    """
    if backend == "tei":
        if not tei_url:
            raise ValueError("EMBEDDING_BACKEND=tei needs TEI_URL")
        return TeiEmbedder(tei_url, api_key=api_key)
    if backend == "local":
        return BgeM3Embedder()
    raise ValueError(f"unknown embedding backend {backend!r}; use 'tei' or 'local'")
