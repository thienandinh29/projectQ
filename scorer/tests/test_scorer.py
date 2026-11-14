"""The scorer service with a tiny random model built offline (no download, no real weights)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nodetrail_scorer.model import MAX_TOKENS, Model, Pin, sha256, verify
from nodetrail_scorer.server import create_app


@pytest.fixture(scope="module")
def tiny(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from tokenizers import ByteLevelBPETokenizer
    from transformers import (
        PreTrainedTokenizerFast,
        RobertaConfig,
        RobertaForSequenceClassification,
    )

    path = tmp_path_factory.mktemp("tiny")
    bpe = ByteLevelBPETokenizer()
    bpe.train_from_iterator(["Cities are crowded. However, buses help."] * 20, vocab_size=300,
                            special_tokens=["<s>", "<pad>", "</s>", "<unk>"])  # fmt: skip
    tok = PreTrainedTokenizerFast(
        tokenizer_object=bpe._tokenizer,
        bos_token="<s>",
        eos_token="</s>",
        pad_token="<pad>",
        unk_token="<unk>",
    )
    tok.save_pretrained(path)
    sizes: dict[str, Any] = {
        "vocab_size": len(tok),
        "hidden_size": 32,
        "num_hidden_layers": 1,
        "num_attention_heads": 2,
        "intermediate_size": 64,
        "num_labels": 5,
        "max_position_embeddings": MAX_TOKENS + 4,
        "problem_type": "regression",
    }
    config = RobertaConfig(**sizes)
    RobertaForSequenceClassification(config).save_pretrained(path, safe_serialization=True)
    return path


def test_the_model_returns_raw_outputs_and_reports_truncation(tiny: Path) -> None:
    model = Model(tiny)
    short = model("Cities are crowded. However, buses help.")
    assert len(short.raw) == 5 and not short.truncated and short.tokens < 50
    assert model("Cities are crowded. However, buses help.").raw == short.raw  # deterministic
    long = model("buses help " * 400)
    assert long.truncated and long.tokens > MAX_TOKENS


def test_the_weights_must_match_the_pin(tiny: Path) -> None:
    verify(tiny, sha256(tiny / "model.safetensors"))
    with pytest.raises(SystemExit, match="does not match"):
        verify(tiny, "0" * 64)


def test_a_pin_needs_every_field_and_a_full_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCORER_MODEL", "org/model")
    monkeypatch.setenv("SCORER_REVISION", "main")
    monkeypatch.setenv("SCORER_WEIGHTS_SHA256", "x")
    with pytest.raises(SystemExit, match="full commit"):
        Pin.from_env()
    monkeypatch.delenv("SCORER_WEIGHTS_SHA256")
    with pytest.raises(SystemExit, match="SCORER_WEIGHTS_SHA256"):
        Pin.from_env()


def test_routes(tiny: Path) -> None:
    pin = Pin("org/model", "a" * 40, "b" * 64)
    client = TestClient(create_app(pin, Model(tiny)))
    assert client.get("/health").json()["revision"] == "a" * 40
    r = client.post("/score", json={"text": "Buses help."})
    assert r.status_code == 200 and len(r.json()["raw"]) == 5 and r.json()["model"] == "org/model"
    assert client.post("/score", json={"text": ""}).status_code == 422
    assert client.post("/score", json={"text": "x", "extra": 1}).status_code == 422
