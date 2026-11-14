"""The scorer's measurement core (specs/writing/step-2.3.md)."""

import itertools
import random

import pytest

from app.writing.scoring import (
    Calibration,
    band_range,
    bootstrap_interval,
    ceil_half,
    fit_isotonic,
    fit_ridge,
    floor_half,
    held_out_split,
    kfold,
    mae,
    no_band_reason,
    pearson,
    quantile,
    qwk,
    round_half,
    within_half,
)


def test_half_band_rounding_is_clipped_to_the_scale() -> None:
    assert [round_half(x) for x in (5.24, 5.25, 5.74, 5.75, -1, 9.6)] == [5.0, 5.5, 5.5, 6.0, 0, 9]
    assert (floor_half(5.9), ceil_half(5.1), floor_half(6.0), ceil_half(6.0)) == (5.5, 5.5, 6, 6)


def test_isotonic_calibration_is_monotone_and_least_squares() -> None:
    iso = fit_isotonic([1, 2, 3, 4], [5.0, 6.0, 5.5, 7.0])  # 6.0 then 5.5 violate: pooled
    assert iso.ys == (5.0, 5.75, 7.0) and iso.xs == (1, 2.5, 4)
    assert iso(0) == 5.0 and iso(10) == 7.0 and iso(1.75) == pytest.approx(5.375)
    rng = random.Random(1)
    raw = [rng.uniform(0, 1) for _ in range(200)]
    band = [4 + 4 * r + rng.gauss(0, 0.6) for r in raw]
    fitted = fit_isotonic(raw, band)
    grid = [i / 50 for i in range(51)]
    assert all(fitted(a) <= fitted(b) for a, b in itertools.pairwise(grid))
    assert all(0 <= fitted(x) <= 9 for x in (-5, 0.5, 5))
    const = fit_isotonic([1, 1, 1], [6, 6, 6])
    assert const(0) == const(5) == 6


def test_the_range_comes_from_residuals_rounded_outward() -> None:
    cal = Calibration(fit_isotonic([0, 1], [0, 9]), residual_low=-0.4, residual_high=0.6, essays=70)
    r = band_range(6.2, cal)
    assert (r.low, r.high, r.uncertain) == (5.5, 7.0, False)  # 5.8 -> 5.5, 6.8 -> 7.0
    wide = Calibration(cal.isotonic, residual_low=-1.0, residual_high=1.0, essays=70)
    assert band_range(6.2, wide).uncertain  # 5.0 to 7.5 is wider than 1.5 bands
    assert quantile([1, 2, 3, 4], 0.5) == 2.5 and quantile([3], 0.9) == 3


def test_when_no_band_is_shown() -> None:
    cal = Calibration(fit_isotonic([0, 1], [0, 9]), -0.5, 0.5, 70)
    assert no_band_reason(1, 300, cal) == "task1"
    assert no_band_reason(2, 149, cal) == "too_short"
    assert no_band_reason(2, 150, None) == "not_calibrated"
    assert no_band_reason(2, 150, cal) is None


def test_qwk_against_a_hand_computed_example() -> None:
    assert qwk([5, 6, 7], [5, 6, 7]) == 1.0
    # bands 5, 6, 7 are classes 10, 12, 14; predictions 6, 6, 7 are 12, 12, 14; k = 5 (10..14),
    # weight (i - j)^2 / 16. Observed: one disagreement (10 -> 12), weight 4/16 = 0.25.
    # Expected from the margins (rows 1, 1, 1 at 10, 12, 14; columns 2 at 12, 1 at 14; n = 3):
    # 4/16*2/3 + 16/16*1/3 + 4/16*1/3 + 4/16*2/3 = 0.75. So 1 - 0.25 / 0.75 = 2/3.
    assert qwk([5, 6, 7], [6, 6, 7]) == pytest.approx(2 / 3)
    assert qwk([6, 6], [6, 6]) is None  # no spread: undefined, not 1
    assert qwk([5.0, 6.0], [5.2, 6.2]) == 1.0  # predictions are rounded to half bands first
    with pytest.raises(ValueError):
        qwk([5], [5, 6])


def test_bootstrap_interval_is_seeded_and_brackets_the_estimate() -> None:
    rng = random.Random(2)
    ex = [round_half(rng.uniform(4, 8)) for _ in range(60)]
    pr = [e + rng.gauss(0, 0.5) for e in ex]
    point = qwk(ex, pr)
    a = bootstrap_interval(ex, pr, qwk, resamples=500, seed=7)
    assert a == bootstrap_interval(ex, pr, qwk, resamples=500, seed=7)
    assert a and point and a[0] < point < a[1]
    assert bootstrap_interval([6, 6, 6], [6, 6, 6], qwk, resamples=50) is None


def test_error_measures() -> None:
    assert mae([5, 6], [5.5, 7]) == 0.75
    # 5.4 -> 5.5 (within 0.5 of 5); 6.8 -> 7.0 and 8.0 are a full band off
    assert within_half([5, 6, 7], [5.4, 6.8, 8.0]) == 1 / 3
    assert pearson([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)
    assert pearson([1, 1], [2, 3]) is None


def test_ridge_recovers_a_linear_relation_and_shrinks_with_alpha() -> None:
    rng = random.Random(3)
    x = [[rng.uniform(100, 400), rng.uniform(0, 10)] for _ in range(80)]
    y = [3 + 0.01 * a - 0.1 * b for a, b in x]
    model = fit_ridge(x, y, alpha=1e-6)
    assert model([250, 5]) == pytest.approx(3 + 2.5 - 0.5, abs=1e-3)
    heavy = fit_ridge(x, y, alpha=1e6)
    assert abs(heavy([400, 0]) - sum(y) / len(y)) < 0.01  # shrunk to the mean
    flat = fit_ridge([[1.0, 5.0], [2.0, 5.0], [3.0, 5.0]], [4.0, 5.0, 6.0], alpha=1e-6)
    assert flat([4.0, 5.0]) == pytest.approx(7.0, abs=1e-3)  # a constant feature is harmless


def test_the_held_out_split_is_seeded_and_never_leaks_into_folds() -> None:
    ids = [f"e{i:03}" for i in range(80)]
    test = held_out_split(ids, 0.3, seed=11)
    assert len(test) == 24 and test == held_out_split(list(reversed(ids)), 0.3, seed=11)
    rest = [i for i in ids if i not in set(test)]
    folds = kfold(rest, k=5, seed=11)
    validated = [v for _, fold in folds for v in fold]
    assert sorted(validated) == sorted(rest)  # each validated exactly once
    assert not set(test) & {x for train, val in folds for x in train + val}
    assert all(not set(train) & set(val) for train, val in folds)
    with pytest.raises(ValueError):
        held_out_split(["a", "a"])
