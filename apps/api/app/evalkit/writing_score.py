"""The owner's evaluation of the band scorer (specs/writing/step-2.3.md; gate: QWK >= 0.7).

Runs where the private essays are (`data/private/writing/essays.jsonl`, never committed):

    uv run python -m app.evalkit.writing_score develop ../../data/private/writing/essays.jsonl \\
        --scorer-url http://localhost:8020 [--languagetool-url http://localhost:8010] \\
        [--write-calibration]
    uv run python -m app.evalkit.writing_score test ../../data/private/writing/essays.jsonl \\
        --scorer-url http://localhost:8020 [--again "why the test set is scored again"]

`develop` sets aside the 30% test split on its first run (seeded; evals/writing/test-ids.txt),
cross-validates the model, the constant and the feature baselines on the other 70%, and writes
evals/writing/develop-report.json; with --write-calibration it stores the calibration in
data/writing/scorer.yaml. `test` scores the held-out essays once (a second run needs --again with a
reason, which is recorded) and checks robustness; it writes evals/writing/score-report.json.
Only metrics are written; essay texts never leave data/private/.
"""

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.writing.scoring import (
    CalibrationIn,
    Ridge,
    ScorerConfig,
    band_range,
    bootstrap_interval,
    fit_isotonic,
    fit_ridge,
    held_out_split,
    kfold,
    load_scorer_config,
    mae,
    pearson,
    quantile,
    qwk,
    round_half,
    within_half,
)

ROOT = Path(__file__).resolve().parents[4]
EVALS = ROOT / "evals" / "writing"
SCORER_YAML = ROOT / "data" / "writing" / "scorer.yaml"
SEED = 20261114
GATE_QWK = 0.7
ROBUST_MAX_MOVE = 0.5
FEATURES = ("words", "avg_sentence_words", "clauses_per_sentence", "linking_groups_used",
            "errors_per_100_words")  # fmt: skip


@dataclass(frozen=True)
class Essay:
    id: str
    text: str
    band: float


def load_essays(path: Path) -> list[Essay]:
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        d = json.loads(line)
        band = float(d["band"])
        if band * 2 != int(band * 2) or not 0 <= band <= 9:
            raise ValueError(f"line {n}: band {band} is not an IELTS band")
        out.append(Essay(str(d["id"]), str(d["text"]), band))
    if len({e.id for e in out}) != len(out):
        raise ValueError("essay ids must be unique")
    return out


# --- the core, pure: everything below takes numbers, not services --------------------------


def method_metrics(
    examiner: Sequence[float], predicted: Sequence[float], words: Sequence[float], seed: int
) -> dict[str, Any]:
    return {
        "qwk": qwk(examiner, predicted),
        "qwk_interval": bootstrap_interval(examiner, predicted, qwk, seed=seed),
        "mae": round(mae(examiner, predicted), 4),
        "within_half_band": round(within_half(examiner, predicted), 4),
        "length_correlation": pearson(predicted, words),
    }


def develop(
    essays: Sequence[Essay],
    raw: dict[str, float],
    features: dict[str, list[float]],
    test_ids: set[str],
    *,
    seed: int = SEED,
    k: int = 5,
) -> tuple[dict[str, Any], CalibrationIn]:
    """Cross-validated comparison on the development essays, and the calibration to keep."""
    dev = [e for e in essays if e.id not in test_ids]
    if len(dev) < 2 * k:
        raise ValueError(f"{len(dev)} development essays: too few for {k}-fold cross-validation")
    band = {e.id: e.band for e in dev}
    preds: dict[str, dict[str, float]] = {"model": {}, "constant": {}, "features": {}}
    for train, val in kfold([e.id for e in dev], k=k, seed=seed):
        iso = fit_isotonic([raw[i] for i in train], [band[i] for i in train])
        mean = sum(band[i] for i in train) / len(train)
        ridge = fit_ridge([features[i] for i in train], [band[i] for i in train])
        for i in val:
            preds["model"][i] = iso(raw[i])
            preds["constant"][i] = mean
            preds["features"][i] = ridge(features[i])
    ids = [e.id for e in dev]
    examiner = [band[i] for i in ids]
    words = [features[i][0] for i in ids]
    residuals = [band[i] - preds["model"][i] for i in ids]
    calibration = CalibrationIn(
        xs=(iso := fit_isotonic([raw[i] for i in ids], examiner)).xs,
        ys=iso.ys,
        residual_low=min(0.0, quantile(residuals, 0.10)),
        residual_high=max(0.0, quantile(residuals, 0.90)),
        essays=len(ids),
        fitted_on=f"{datetime.now(UTC).date()}, {len(ids)} development essays, {k}-fold",
    )
    cal = calibration.build()
    ranges = [band_range(preds["model"][i], cal) for i in ids]
    report = {
        "phase": "develop",
        "essays": len(ids),
        "band_counts": dict(sorted(_counts(examiner).items())),
        "examiner_length_correlation": pearson(examiner, words),
        "methods": {
            m: method_metrics(examiner, [p[i] for i in ids], words, seed) for m, p in preds.items()
        },
        "range": {
            "residual_low": calibration.residual_low,
            "residual_high": calibration.residual_high,
            "covers_examiner_band": round(
                sum(r.low <= b <= r.high for r, b in zip(ranges, examiner, strict=True)) / len(ids),
                4,
            ),
            "shown_as_uncertain": round(sum(r.uncertain for r in ranges) / len(ids), 4),
        },
        "note": "Cross-validated on the development essays only; the test essays were not used.",
    }
    return report, calibration


def robustness(texts: dict[str, str], predict: Callable[[str], float]) -> dict[str, Any]:
    """How far small edits move the rounded band; the gate allows at most half a band."""
    moves: dict[str, list[float]] = {}
    for name, edit in PERTURBATIONS.items():
        out = []
        for text in texts.values():
            changed = edit(text)
            if changed != text:
                out.append(abs(round_half(predict(changed)) - round_half(predict(text))))
        moves[name] = out
    return {
        name: {
            "essays": len(m),
            "max_move": max(m, default=None),
            "over_half_band": sum(x > ROBUST_MAX_MOVE for x in m),
        }
        for name, m in moves.items()
    }


def _double_spaces(text: str) -> str:
    return re.sub(r"([.!?]) (?=\S)", r"\1  ", text)


def _merge_first_paragraphs(text: str) -> str:
    parts = re.split(r"\n\s*\n", text.strip(), maxsplit=1)
    return text if len(parts) < 2 else parts[0] + " " + parts[1]


PERTURBATIONS: dict[str, Callable[[str], str]] = {
    "double_spaces_after_sentences": _double_spaces,
    "first_two_paragraphs_merged": _merge_first_paragraphs,
}


def _counts(bands: Sequence[float]) -> dict[str, int]:
    out: dict[str, int] = {}
    for b in bands:
        out[f"{b:.1f}"] = out.get(f"{b:.1f}", 0) + 1
    return out


# --- input and output ----------------------------------------------------------------------


def _test_ids(essays: Sequence[Essay], create: bool) -> set[str]:
    path = EVALS / "test-ids.txt"
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        ids = {x.strip() for x in lines if x.strip() and not x.startswith("#")}
        unknown = ids - {e.id for e in essays}
        if unknown:
            raise SystemExit(f"test-ids.txt names essays not in the file: {sorted(unknown)[:5]}")
        return ids
    if not create:
        raise SystemExit("no test split yet: run `develop` first")
    held = held_out_split([e.id for e in essays], 0.3, seed=SEED)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Held-out test essays (seed {SEED}, 30%), set aside before any tuning.\n"
        + "\n".join(held)
        + "\n",
        encoding="utf-8",
    )
    return set(held)


def _raw_scores(
    essays: Sequence[Essay], url: str, config: ScorerConfig, cache: Path
) -> Callable[[str], float]:
    """Raw model output per text, cached per model revision (the cache stays in data/private)."""
    from app.writing.scorer_client import ScorerClient

    client = ScorerClient(url)
    store: dict[str, float] = {}
    if cache.exists():
        store = json.loads(cache.read_text(encoding="utf-8"))

    def raw(text: str) -> float:
        key = f"{config.revision}:{hashlib.sha256(text.encode()).hexdigest()}"
        if key not in store:
            got = client.score(text)
            if (got.model, got.revision) != (config.model, config.revision):
                raise SystemExit(f"the service runs {got.model}@{got.revision}, not the pin")
            store[key] = got.raw[config.output]
            cache.write_text(json.dumps(store), encoding="utf-8")
        return store[key]

    return raw


def _features(essays: Sequence[Essay], languagetool_url: str) -> dict[str, list[float]]:
    from app.services.writing import load_grammar_step
    from app.writing.analysis import analyse, load_linking_words
    from app.writing.grammar import analyse_grammar, complexity

    writing = ROOT / "data" / "writing"
    step = load_grammar_step(writing, ROOT / "data" / "courses", languagetool_url)
    linking = load_linking_words(writing / "linking-words.yaml")
    out = {}
    for e in essays:
        sents = [s for s in step.nlp(e.text).sents if s.text.strip()]
        a = analyse(e.text, 2, linking, sentence_texts=[s.text for s in sents])
        errors = 0.0
        if step.client is not None:
            g = analyse_grammar(e.text, step.client.matches(e.text), step.nlp, step.annotator,
                                step.error_map)  # fmt: skip
            errors = 100 * len(g.issues) / max(1, a.words)
        out[e.id] = [float(a.words), a.avg_sentence_words,
                     complexity(sents).clauses_per_sentence, float(a.linking_groups_used),
                     errors]  # fmt: skip
    return out


def write_calibration(calibration: CalibrationIn, path: Path = SCORER_YAML) -> None:
    """Replace the `calibration:` block (the last key) and keep the file's comments."""
    text = path.read_text(encoding="utf-8")
    head = text[: text.index("\ncalibration:") + 1]
    c = calibration.model_dump()
    block = (
        "calibration:\n"
        f"  xs: {json.dumps([round(x, 6) for x in c['xs']])}\n"
        f"  ys: {json.dumps([round(y, 6) for y in c['ys']])}\n"
        f"  residual_low: {round(c['residual_low'], 4)}\n"
        f"  residual_high: {round(c['residual_high'], 4)}\n"
        f"  essays: {c['essays']}\n"
        f"  fitted_on: {json.dumps(c['fitted_on'])}\n"
    )
    path.write_text(head + block, encoding="utf-8")
    load_scorer_config(path)  # refuse to leave a file the worker cannot read


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("phase", choices=["develop", "test"])
    parser.add_argument("essays", type=Path)
    parser.add_argument("--scorer-url", required=True)
    parser.add_argument("--languagetool-url", default="")
    parser.add_argument("--write-calibration", action="store_true")
    parser.add_argument("--again", default="", help="why the test set is scored again")
    args = parser.parse_args(argv)
    if "private" not in args.essays.resolve().parts:
        print("refusing: the essays belong in data/private/", file=sys.stderr)
        return 2
    essays = load_essays(args.essays)
    config = load_scorer_config(SCORER_YAML)
    raw = _raw_scores(essays, args.scorer_url, config, args.essays.parent / "raw-cache.json")
    test_ids = _test_ids(essays, create=args.phase == "develop")
    features = _features(essays, args.languagetool_url)
    feature_note = "" if args.languagetool_url else " (no LanguageTool: errors feature is 0)"
    if args.phase == "develop":
        report, calibration = develop(essays, {e.id: raw(e.text) for e in essays}, features,
                                      test_ids)  # fmt: skip
        report["features"] = list(FEATURES)
        report["note"] += feature_note
        _write(EVALS / "develop-report.json", report)
        if args.write_calibration:
            write_calibration(calibration)
        print(json.dumps(report["methods"], indent=2))
        return 0
    path = EVALS / "score-report.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if previous and not args.again:
        print("refusing: the test set was scored on "
              f"{previous['scored_at']}; pass --again with a reason", file=sys.stderr)  # fmt: skip
        return 2
    if config.calibration is None:
        print("refusing: no calibration in data/writing/scorer.yaml (run develop first)",
              file=sys.stderr)  # fmt: skip
        return 2
    report = final_test(essays, raw, features, test_ids, config)
    report["features"] = list(FEATURES)
    report["scored_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    report["again"] = [*(previous or {}).get("again", []), args.again] if args.again else []
    _write(path, report)
    print(json.dumps({k: report[k] for k in ("methods", "robustness", "gate")}, indent=2))
    return 0


def final_test(
    essays: Sequence[Essay],
    raw: Callable[[str], float],
    features: dict[str, list[float]],
    test_ids: set[str],
    config: ScorerConfig,
) -> dict[str, Any]:
    assert config.calibration is not None
    cal = config.calibration.build()
    dev = [e for e in essays if e.id not in test_ids]
    test = [e for e in essays if e.id in test_ids]
    ridge: Ridge = fit_ridge([features[e.id] for e in dev], [e.band for e in dev])
    mean = sum(e.band for e in dev) / len(dev)
    examiner = [e.band for e in test]
    words = [features[e.id][0] for e in test]
    model = [cal.isotonic(raw(e.text)) for e in test]
    methods = {
        "model": method_metrics(examiner, model, words, SEED),
        "constant": method_metrics(examiner, [mean] * len(test), words, SEED),
        "features": method_metrics(examiner, [ridge(features[e.id]) for e in test], words, SEED),
    }
    robust = robustness({e.id: e.text for e in test}, lambda t: cal.isotonic(raw(t)))
    q = methods["model"]["qwk"]
    met = q is not None and q >= GATE_QWK and all(r["over_half_band"] == 0 for r in robust.values())
    return {
        "phase": "test",
        "essays": len(test),
        "band_counts": dict(sorted(_counts(examiner).items())),
        "methods": methods,
        "robustness": robust,
        "gate": {"qwk_needed": GATE_QWK, "met": met},
        "note": "Scored once on the held-out essays; a spelling-fix perturbation is not run yet.",
    }


def _write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
