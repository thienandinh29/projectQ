import pytest

from app.engine.bkt import (
    DEFAULT_PARAMS,
    LEAVE_THRESHOLD,
    MASTERY_THRESHOLD,
    MIN_UNAIDED_CORRECT,
    BKTParams,
    is_confirmed_mastery,
    is_mastered,
    params_with_help,
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


# --- confirmed mastery and help -----------------------------------------------------------------


def test_high_p_known_alone_is_not_confirmed_mastery() -> None:
    assert not is_confirmed_mastery(0.99, unaided_correct=MIN_UNAIDED_CORRECT - 1)
    assert is_confirmed_mastery(0.99, unaided_correct=MIN_UNAIDED_CORRECT)
    assert not is_confirmed_mastery(0.90, unaided_correct=10)


def test_confirmed_mastery_has_hysteresis() -> None:
    p = (LEAVE_THRESHOLD + MASTERY_THRESHOLD) / 2  # between the two thresholds
    assert not is_confirmed_mastery(p, unaided_correct=5)
    assert is_confirmed_mastery(p, unaided_correct=5, was_confirmed=True)
    assert not is_confirmed_mastery(LEAVE_THRESHOLD - 0.01, unaided_correct=5, was_confirmed=True)


def test_confirmed_mastery_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        is_confirmed_mastery(1.2, unaided_correct=3)
    with pytest.raises(ValueError):
        is_confirmed_mastery(0.9, unaided_correct=-1)


def test_hints_weaken_the_evidence_of_a_correct_answer() -> None:
    mcq = DEFAULT_PARAMS["mcq"]
    assert params_with_help(mcq, 0) is mcq
    gains = [update(0.3, True, params_with_help(mcq, h)) - 0.3 for h in range(4)]
    assert gains == sorted(gains, reverse=True)  # more help, smaller increase
    assert gains[3] < gains[0] / 2


def test_help_keeps_the_model_identifiable() -> None:
    for kind in ("mcq", "code"):
        for hints in range(6):
            p = params_with_help(DEFAULT_PARAMS[kind], hints)
            assert p.p_slip + p.p_guess < 1
    with pytest.raises(ValueError):
        params_with_help(DEFAULT_PARAMS["mcq"], -1)


def test_a_wrong_answer_after_help_still_lowers_p_known() -> None:
    mcq = DEFAULT_PARAMS["mcq"]
    assert posterior(0.6, False, params_with_help(mcq, 3)) < 0.6


def test_trace_reports_pending_confirmation_until_enough_unaided_evidence() -> None:
    from datetime import UTC, datetime

    from app.engine.bkt import update_traced

    mcq = DEFAULT_PARAMS["mcq"]
    now = datetime(2026, 11, 11, tzinfo=UTC)
    _, pending = update_traced(0.93, True, mcq, concept_slug="loops", now=now, unaided_correct=1)
    assert pending.rule == "bkt.correct.pending_confirmation"
    assert "cần thêm 1 câu đúng không dùng gợi ý" in pending.rule_vi
    _, done = update_traced(0.93, True, mcq, concept_slug="loops", now=now, unaided_correct=2)
    assert done.rule == "bkt.correct.mastered"
    _, legacy = update_traced(0.93, True, mcq, concept_slug="loops", now=now)
    assert legacy.rule == "bkt.correct.mastered"  # callers without counts keep the old behaviour
