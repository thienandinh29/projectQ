"""Intervals and agreement, checked against values worked out independently."""

import pytest

from app.evalkit.stats import clopper_pearson, cohen_kappa, rate


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [
        (15, 15, 0.78, 1.0),  # the model-test plan quotes ~78%
        (14, 15, 0.68, 0.998),
        (20, 20, 0.83, 1.0),
        (36, 36, 0.90, 1.0),  # the planted-item target: 36 caught is the least that shows 90%
        (0, 50, 0.0, 0.071),  # no bad of 50 served: cannot rule out ~7%
        (0, 73, 0.0, 0.049),  # ... and 73 is what shows under 5%
        (1, 40, 0.0006, 0.132),
    ],
)
def test_clopper_pearson_matches_known_values(k: int, n: int, low: float, high: float) -> None:
    got_low, got_high = clopper_pearson(k, n)
    assert got_low == pytest.approx(low, abs=0.006)
    assert got_high == pytest.approx(high, abs=0.006)


def test_interval_contains_the_point_and_narrows_with_more_data() -> None:
    small = clopper_pearson(5, 10)
    big = clopper_pearson(50, 100)
    assert small[0] < 0.5 < small[1] and big[0] < 0.5 < big[1]
    assert (big[1] - big[0]) < (small[1] - small[0])


def test_interval_is_symmetric_around_a_half() -> None:
    low, high = clopper_pearson(3, 10)
    mirror_low, mirror_high = clopper_pearson(7, 10)
    assert (low, high) == pytest.approx((1 - mirror_high, 1 - mirror_low))


@pytest.mark.parametrize(("k", "n"), [(1, 0), (-1, 5), (6, 5)])
def test_bad_arguments_are_rejected(k: int, n: int) -> None:
    with pytest.raises(ValueError):
        clopper_pearson(k, n)


def test_rate_reads_like_a_sentence_and_handles_nothing_to_measure() -> None:
    assert str(rate(36, 36)) == "36/36 = 100% (95%: 90% to 100%)"
    nothing = rate(0, 0)
    assert nothing.point is None and "n/a" in str(nothing)
    with pytest.raises(ValueError):
        rate(1, 0)


def test_kappa_perfect_chance_and_a_worked_example() -> None:
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == pytest.approx(1.0)
    # po = 0.75; both say y half the time and n half the time -> pe = 0.5 -> kappa 0.5
    assert cohen_kappa(list("yynn"), list("ynnn")) == pytest.approx(0.5)
    # po = 0.5; the second labeler always says y, so pe = 0.5 too: no agreement beyond chance
    assert cohen_kappa(list("yynn"), list("yyyy")) == pytest.approx(0.0)


def test_kappa_undefined_cases() -> None:
    assert cohen_kappa([], []) is None
    assert (
        cohen_kappa(["good"] * 5, ["good"] * 5) is None
    )  # one class only: nothing to agree beyond
    with pytest.raises(ValueError):
        cohen_kappa(["a"], ["a", "b"])
