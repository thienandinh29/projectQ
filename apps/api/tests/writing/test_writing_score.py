"""The owner's scorer evaluation on synthetic essays (specs/writing/step-2.3.md)."""

import random
import shutil
from pathlib import Path

import pytest

from app.evalkit import writing_score as ws
from app.writing.scoring import held_out_split, load_scorer_config

ROOT = Path(__file__).resolve().parents[4]


def synthetic(n: int = 60, seed: int = 5) -> tuple[list[ws.Essay], dict[str, float],
                                                  dict[str, list[float]]]:  # fmt: skip
    """Essays whose raw model output tracks the band (with noise) and whose length does not."""
    rng = random.Random(seed)
    essays, raw, feats = [], {}, {}
    for i in range(n):
        band = rng.choice([4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5])
        eid = f"e{i:03}"
        essays.append(ws.Essay(eid, f"Essay {i}.\n\nSecond paragraph. Ends here.", band))
        raw[eid] = 0.5 * band + rng.gauss(0, 0.15)
        feats[eid] = [rng.uniform(250, 350), 15.0, 1.3, 4.0, rng.uniform(0, 5)]
    return essays, raw, feats


def test_develop_compares_the_model_with_baselines_on_development_essays_only() -> None:
    essays, raw, feats = synthetic()
    test_ids = set(held_out_split([e.id for e in essays], 0.3, seed=1))
    report, cal = ws.develop(essays, raw, feats, test_ids)
    assert report["essays"] == 42 and cal.essays == 42
    model, const = report["methods"]["model"], report["methods"]["constant"]
    assert model["qwk"] > 0.7 and const["qwk"] in (0.0, None)  # the constant cannot rank
    assert model["mae"] < const["mae"]
    assert model["qwk_interval"][0] < model["qwk"] < model["qwk_interval"][1]
    assert cal.residual_low <= 0 <= cal.residual_high
    assert 0.6 <= report["range"]["covers_examiner_band"] <= 1.0
    assert sum(report["band_counts"].values()) == 42
    leaked = {e.id: 99.0 for e in essays if e.id in test_ids}  # test raw scores must be unused
    assert ws.develop(essays, raw | leaked, feats, test_ids)[0] == report
    with pytest.raises(ValueError, match="too few"):
        ws.develop(essays[:9], raw, feats, set())


def test_robustness_counts_edits_that_move_the_band_more_than_half() -> None:
    texts = {"a": "One. Two.\n\nThree.", "b": "Single paragraph only"}
    report = ws.robustness(texts, lambda t: 6.0 + (1.0 if "  " in t else 0.0))
    spaces = report["double_spaces_after_sentences"]
    assert spaces == {"essays": 1, "max_move": 1.0, "over_half_band": 1}  # b has no ". "
    assert report["first_two_paragraphs_merged"]["over_half_band"] == 0


def test_final_test_reports_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    essays, raw, feats = synthetic(seed=9)
    test_ids = set(held_out_split([e.id for e in essays], 0.3, seed=2))
    _, cal = ws.develop(essays, raw, feats, test_ids)
    config = load_scorer_config(ROOT / "data" / "writing" / "scorer.yaml").model_copy(
        update={"calibration": cal}
    )
    by_text = {e.text + e.id: raw[e.id] for e in essays}
    tagged = [ws.Essay(e.id, e.text + e.id, e.band) for e in essays]
    report = ws.final_test(tagged, lambda t: by_text.get(t, 3.0), feats, test_ids, config)
    assert report["essays"] == 18 and report["methods"]["model"]["qwk"] > 0.6
    # edited texts are unknown to the fake model (3.0): every perturbation moves the band
    assert not report["gate"]["met"]


def test_the_split_file_and_the_calibration_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ws, "EVALS", tmp_path)
    essays, raw, feats = synthetic()
    with pytest.raises(SystemExit, match="develop"):
        ws._test_ids(essays, create=False)
    first = ws._test_ids(essays, create=True)
    assert len(first) == 18 and ws._test_ids(essays, create=False) == first  # comment ignored
    yaml_copy = tmp_path / "scorer.yaml"
    shutil.copy(ROOT / "data" / "writing" / "scorer.yaml", yaml_copy)
    _, cal = ws.develop(essays, raw, feats, first)
    ws.write_calibration(cal, yaml_copy)
    text = yaml_copy.read_text(encoding="utf-8")
    assert text.startswith("# The band scorer") and "calibration: null" not in text
    loaded = load_scorer_config(yaml_copy).calibration
    assert loaded is not None and loaded.essays == 42
    ws.write_calibration(cal, yaml_copy)  # idempotent: replaces, never appends
    assert yaml_copy.read_text(encoding="utf-8").count("calibration:") == 1


def test_bad_bands_and_public_paths_are_refused(tmp_path: Path) -> None:
    bad = tmp_path / "essays.jsonl"
    bad.write_text('{"id": "a", "text": "x", "band": 6.3}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="not an IELTS band"):
        ws.load_essays(bad)
    assert ws.main(["develop", str(bad), "--scorer-url", "http://x"]) == 2  # not in private/
