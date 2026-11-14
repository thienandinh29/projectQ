"""The band shown for an essay (specs/writing/step-2.3.md): range only, draft rule, failures."""

from pathlib import Path
from uuid import UUID

import httpx
import pytest

from app.curriculum.course import load_course
from app.services.writing import (
    BAND_DOWN_VI,
    BAND_HIDDEN_VI,
    BAND_MISMATCH_VI,
    BAND_OFF_VI,
    BAND_REASONS_VI,
    GrammarStep,
    band_for,
)
from app.writing.error_map import load_error_map
from app.writing.scorer_client import RawScore, ScorerClient
from app.writing.scoring import CalibrationIn, load_scorer_config

ROOT = Path(__file__).resolve().parents[4]
CONFIG = load_scorer_config(ROOT / "data" / "writing" / "scorer.yaml")
OWNER = UUID("00000000-0000-4000-8000-0000000e2e01")
OTHER = UUID("00000000-0000-4000-8000-000000000002")
CALIBRATED = CONFIG.model_copy(
    update={
        "calibration": CalibrationIn(
            xs=(3.0, 5.0),
            ys=(4.0, 8.0),
            residual_low=-0.4,
            residual_high=0.6,
            essays=70,
            fitted_on="2026-11-14, synthetic, for this test",
        )
    }
)


class FakeScorer(ScorerClient):
    def __init__(self, raw: float = 4.0, *, revision: str | None = None, down: bool = False):
        super().__init__("http://scorer.invalid")
        self.out = RawScore((0.0, 0.0, 0.0, 0.0, raw), CONFIG.model, revision or CONFIG.revision,
                            truncated=False)  # fmt: skip
        self.down = down

    def score(self, text: str) -> RawScore:
        if self.down:
            raise httpx.ConnectError("down")
        return self.out


def step(scorer: ScorerClient | None, config: object = CALIBRATED) -> GrammarStep:
    return GrammarStep(
        nlp=None,
        annotator=None,
        error_map=load_error_map(ROOT / "data" / "writing" / "error-map.yaml"),
        course=load_course(ROOT / "data" / "courses" / "english-ielts.yaml"),
        client=None,
        draft_learners=frozenset({OWNER}),
        scorer=scorer,
        scorer_config=config,  # type: ignore[arg-type]
    )


def test_a_calibrated_band_is_a_range_never_a_point() -> None:
    score, why = band_for("essay", 2, 260, OWNER, step(FakeScorer(4.0)))
    # raw 4.0 -> 6.0 on the calibration; 6.0 - 0.4 = 5.6 -> 5.5; 6.0 + 0.6 = 6.6 -> 7.0
    assert why is None and score is not None
    assert (score["band_low"], score["band_high"], score["uncertain"]) == (5.5, 7.0, False)
    assert score["status"] == "draft" and "band" not in score  # no point estimate anywhere


@pytest.mark.parametrize(
    ("task", "words", "learner", "scorer", "config", "why"),
    [
        (2, 260, OWNER, None, CALIBRATED, BAND_OFF_VI),
        (2, 260, OTHER, FakeScorer(), CALIBRATED, BAND_HIDDEN_VI),  # draft: owner only
        (1, 260, OWNER, FakeScorer(), CALIBRATED, BAND_REASONS_VI["task1"]),
        (2, 149, OWNER, FakeScorer(), CALIBRATED, BAND_REASONS_VI["too_short"]),
        (2, 260, OWNER, FakeScorer(), CONFIG, BAND_REASONS_VI["not_calibrated"]),
        (2, 260, OWNER, FakeScorer(down=True), CALIBRATED, BAND_DOWN_VI),
        (2, 260, OWNER, FakeScorer(revision="f" * 40), CALIBRATED, BAND_MISMATCH_VI),
    ],
)
def test_when_there_is_no_band_the_learner_is_told_why(
    task: int, words: int, learner: UUID, scorer: ScorerClient | None, config: object, why: str
) -> None:
    assert band_for("essay", task, words, learner, step(scorer, config)) == (None, why)


def test_a_validated_scorer_is_shown_to_everyone() -> None:
    validated = CALIBRATED.model_copy(update={"status": "validated"})
    score, _ = band_for("essay", 2, 260, OTHER, step(FakeScorer(4.0), validated))
    assert score is not None and score["status"] == "validated"


def test_the_committed_config_pins_the_model_and_has_no_calibration_yet() -> None:
    assert CONFIG.revision == "8d8d0193ec4cfcbc9c780fc6e71810dca7ee41f6" and CONFIG.output == 4
    assert CONFIG.status == "draft" and CONFIG.calibration is None
    with pytest.raises(ValueError, match="non-decreasing"):
        CalibrationIn(xs=(1, 2), ys=(6, 5), residual_low=0, residual_high=0, essays=10,
                      fitted_on="x")  # fmt: skip
