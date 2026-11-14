"""POST /score {text} -> {raw, model, revision, tokens, truncated}; GET /health.

    SCORER_MODEL=... SCORER_REVISION=<commit> SCORER_WEIGHTS_SHA256=... \
        python -m nodetrail_scorer.server

The weights are downloaded once into SCORER_CACHE (a volume) and checked against the pin; the
service refuses to start without a pin or on a mismatch. Reachable only inside the compose network.
"""

import os
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from nodetrail_scorer.model import Model, Pin, Prediction, fetch

MAX_CHARS = 14_000  # the API accepts 12,000 characters; a little room for NFC differences


class ScoreIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=MAX_CHARS)


class ScoreOut(BaseModel):
    raw: list[float]
    model: str
    revision: str
    tokens: int
    truncated: bool


def create_app(pin: Pin, predict: Callable[[str], Prediction]) -> FastAPI:
    app = FastAPI(title="NodeTrail scorer", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "model": pin.model, "revision": pin.revision}

    @app.post("/score")
    def score(body: ScoreIn) -> ScoreOut:
        p = predict(body.text)
        return ScoreOut(raw=p.raw, model=pin.model, revision=pin.revision, tokens=p.tokens,
                        truncated=p.truncated)  # fmt: skip

    return app


def main() -> None:
    import uvicorn

    pin = Pin.from_env()
    model = Model(fetch(pin, Path(os.environ.get("SCORER_CACHE", "/models"))))
    uvicorn.run(create_app(pin, model), host=os.environ.get("SCORER_HOST", "127.0.0.1"),
                port=int(os.environ.get("SCORER_PORT", "8020")))  # fmt: skip


if __name__ == "__main__":
    main()
