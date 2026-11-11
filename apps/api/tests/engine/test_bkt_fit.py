"""EM fitting of BKT parameters: correctness against brute force, recovery, held-out gains."""

import itertools
import math
import random

import pytest

from app.engine.bkt import DEFAULT_PARAMS, BKTParams
from app.engine.bkt_fit import (
    GUESS_MAX,
    SLIP_MAX,
    _auc,
    fit,
    log_likelihood,
    predictions,
    score,
    simulate,
)

TRUE = BKTParams(p_init=0.3, p_transit=0.15, p_slip=0.08, p_guess=0.2)


def brute_force_likelihood(p: BKTParams, seq: list[bool]) -> float:
    """Sum over every hidden path (known can only start or switch on, never off)."""
    total = 0.0
    for path in itertools.product([False, True], repeat=len(seq)):
        if any(a and not b for a, b in itertools.pairwise(path)):
            continue
        prob = p.p_init if path[0] else 1 - p.p_init
        for a, b in itertools.pairwise(path):
            if not a:
                prob *= p.p_transit if b else 1 - p.p_transit
        for known, obs in zip(path, seq, strict=True):
            pc = 1 - p.p_slip if known else p.p_guess
            prob *= pc if obs else 1 - pc
        total += prob
    return total


@pytest.mark.parametrize(
    "seq",
    [[True], [False], [False, True, True], [True, False, False, True], [False] * 5 + [True] * 2],
)
def test_forward_backward_likelihood_matches_brute_force(seq: list[bool]) -> None:
    assert log_likelihood(TRUE, [seq]) == pytest.approx(math.log(brute_force_likelihood(TRUE, seq)))


@pytest.mark.parametrize(
    "true",
    [TRUE, BKTParams(p_init=0.1, p_transit=0.25, p_slip=0.15, p_guess=0.3)],
)
def test_fit_recovers_parameters_from_simulated_answers(true: BKTParams) -> None:
    data = simulate(true, 1500, 10, random.Random(7))
    got = fit(data, starts=2).params
    assert got.p_init == pytest.approx(true.p_init, abs=0.05)
    assert got.p_transit == pytest.approx(true.p_transit, abs=0.04)
    assert got.p_slip == pytest.approx(true.p_slip, abs=0.04)
    assert got.p_guess == pytest.approx(true.p_guess, abs=0.04)


def test_fit_beats_the_defaults_on_held_out_learners() -> None:
    train = simulate(TRUE, 1500, 10, random.Random(1))
    held = simulate(TRUE, 800, 10, random.Random(2))
    fitted = score(fit(train, starts=2).params, held)
    default = score(DEFAULT_PARAMS["mcq"], held)
    assert fitted.log_loss < default.log_loss
    assert fitted.brier < default.brier


def test_fit_stays_inside_the_bounds_and_converges() -> None:
    result = fit(simulate(TRUE, 300, 6, random.Random(3)), starts=2)
    p = result.params
    assert p.p_slip <= SLIP_MAX and p.p_guess <= GUESS_MAX and p.p_slip + p.p_guess < 1
    assert result.converged and result.observations == 1800


def test_fit_is_repeatable_and_rejects_empty_data() -> None:
    data = simulate(TRUE, 200, 6, random.Random(4))
    assert fit(data, seed=9) == fit(data, seed=9)
    with pytest.raises(ValueError):
        fit([[], []])


def test_predictions_use_only_earlier_answers() -> None:
    first = predictions(TRUE, [True, True, False])
    second = predictions(TRUE, [True, True, True])
    assert first[:3] == second[:3]  # the third answer cannot change the third prediction
    assert first[0] == pytest.approx(TRUE.p_init * 0.92 + 0.7 * 0.2)


def test_auc_handles_ties_and_degenerate_sets() -> None:
    assert _auc([(0.9, True), (0.1, False)]) == 1.0
    assert _auc([(0.5, True), (0.5, False)]) == 0.5
    assert _auc([(0.3, True), (0.7, True)]) is None
