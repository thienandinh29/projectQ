import pytest

from app.engine.bkt import (
    DEFAULT_PARAMS,
    BKTParams,
    is_mastered,
    posterior,
    predict_correct,
    update,
)

P = BKTParams(p_init=0.2, p_transit=0.1, p_slip=0.1, p_guess=0.25)
GRID = [i / 20 for i in range(21)]  # 0.0, 0.05, ..., 1.0


def test_posterior_correct_matches_hand_calculation() -> None:
    # known = 0.5 * 0.9 = 0.45; unknown = 0.5 * 0.25 = 0.125 -> 0.45 / 0.575
    assert posterior(0.5, True, P) == pytest.approx(0.45 / 0.575)


def test_posterior_wrong_matches_hand_calculation() -> None:
    # known = 0.5 * 0.1 = 0.05; unknown = 0.5 * 0.75 = 0.375 -> 0.05 / 0.425
    assert posterior(0.5, False, P) == pytest.approx(0.05 / 0.425)


def test_update_applies_transit_after_evidence() -> None:
    post = 0.45 / 0.575
    assert update(0.5, True, P) == pytest.approx(post + (1 - post) * 0.1)


def test_predict_correct() -> None:
    assert predict_correct(0.5, P) == pytest.approx(0.5 * 0.9 + 0.5 * 0.25)


@pytest.mark.parametrize("p", GRID)
def test_evidence_moves_belief_in_the_right_direction(p: float) -> None:
    assert posterior(p, True, P) >= p
    assert posterior(p, False, P) <= p


@pytest.mark.parametrize("p", GRID)
def test_correct_always_beats_wrong(p: float) -> None:
    assert update(p, True, P) >= update(p, False, P)


@pytest.mark.parametrize("p", GRID)
@pytest.mark.parametrize("correct", [True, False])
def test_update_stays_a_probability(p: float, correct: bool) -> None:
    assert 0.0 <= update(p, correct, P) <= 1.0


@pytest.mark.parametrize("kind", ["mcq", "code"])
def test_repeated_correct_answers_reach_mastery(kind: str) -> None:
    params = DEFAULT_PARAMS[kind]  # type: ignore[index]
    p = params.p_init
    for _ in range(10):
        p = update(p, True, params)
    assert is_mastered(p)


def test_code_success_is_stronger_evidence_than_mcq_success() -> None:
    # Guessing a passing program is far less likely than guessing an MCQ option.
    p = 0.3
    assert posterior(p, True, DEFAULT_PARAMS["code"]) > posterior(p, True, DEFAULT_PARAMS["mcq"])


def test_a_lucky_guess_does_not_grant_mastery() -> None:
    p = update(DEFAULT_PARAMS["mcq"].p_init, True, DEFAULT_PARAMS["mcq"])
    assert not is_mastered(p)


def test_impossible_evidence_keeps_belief() -> None:
    certain = BKTParams(p_init=0.5, p_transit=0.0, p_slip=0.0, p_guess=0.25)
    assert posterior(1.0, False, certain) == 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"p_init": -0.1, "p_transit": 0.1, "p_slip": 0.1, "p_guess": 0.2},
        {"p_init": 0.2, "p_transit": 1.5, "p_slip": 0.1, "p_guess": 0.2},
        {"p_init": 0.2, "p_transit": 0.1, "p_slip": 0.6, "p_guess": 0.5},
    ],
)
def test_invalid_params_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        BKTParams(**kwargs)


@pytest.mark.parametrize("bad", [-0.01, 1.01])
def test_invalid_probability_rejected(bad: float) -> None:
    with pytest.raises(ValueError):
        update(bad, True, P)
