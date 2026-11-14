"""Loading the pinned model and running it. Raw output only: calibration lives in the API."""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_TOKENS = 512
WEIGHTS = "model.safetensors"
FILES = ["config.json", WEIGHTS, "vocab.json", "merges.txt", "tokenizer.json",
         "tokenizer_config.json", "special_tokens_map.json"]  # fmt: skip


@dataclass(frozen=True)
class Pin:
    """What is loaded: a repository at one commit, with the weights' SHA-256 checked."""

    model: str
    revision: str
    weights_sha256: str

    @classmethod
    def from_env(cls) -> "Pin":
        values = {k: os.environ.get(f"SCORER_{k.upper()}", "").strip()
                  for k in ("model", "revision", "weights_sha256")}  # fmt: skip
        missing = [k for k, v in values.items() if not v]
        if missing:
            raise SystemExit(f"scorer: set SCORER_{', SCORER_'.join(m.upper() for m in missing)}")
        if len(values["revision"]) != 40:
            raise SystemExit("scorer: SCORER_REVISION must be a full commit hash, not a branch")
        return cls(**values)


@dataclass(frozen=True)
class Prediction:
    raw: list[float]
    tokens: int
    truncated: bool


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(pin: Pin, cache: Path) -> Path:
    """Download the pinned files once (Hugging Face caches by commit) and check the weights."""
    # Plain HTTPS downloads: the Xet protocol needs more hosts and gains nothing for one file.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import snapshot_download

    path = Path(snapshot_download(pin.model, revision=pin.revision, cache_dir=cache,
                                  allow_patterns=FILES))  # fmt: skip
    verify(path, pin.weights_sha256)
    return path


def verify(path: Path, expected: str) -> None:
    got = sha256(path / WEIGHTS)
    if got != expected:
        raise SystemExit(f"scorer: weights SHA-256 {got} does not match the pin {expected}")


class Model:
    def __init__(self, path: Path) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
        self._torch = torch
        self.tokenizer: Any = AutoTokenizer.from_pretrained(path)
        self.model: Any = AutoModelForSequenceClassification.from_pretrained(
            path, use_safetensors=True
        ).eval()

    def __call__(self, text: str) -> Prediction:
        full = self.tokenizer(text, truncation=False)["input_ids"]
        encoded = self.tokenizer(text, truncation=True, max_length=MAX_TOKENS, return_tensors="pt")
        with self._torch.no_grad():
            logits = self.model(**encoded).logits[0]
        return Prediction(
            raw=[float(x) for x in logits.tolist()],
            tokens=len(full),
            truncated=len(full) > MAX_TOKENS,
        )
