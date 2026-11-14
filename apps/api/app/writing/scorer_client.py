"""Client for the band model service (scorer/, specs/writing/step-2.3.md)."""

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class RawScore:
    raw: tuple[float, ...]
    model: str
    revision: str
    truncated: bool


class ScorerClient:
    def __init__(self, url: str, *, timeout: float = 30.0) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout

    def score(self, text: str) -> RawScore:
        response = httpx.post(f"{self.url}/score", json={"text": text}, timeout=self.timeout)
        response.raise_for_status()
        d = response.json()
        return RawScore(
            raw=tuple(float(x) for x in d["raw"]),
            model=str(d["model"]),
            revision=str(d["revision"]),
            truncated=bool(d["truncated"]),
        )
