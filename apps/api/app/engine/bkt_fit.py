"""Fitting BKT parameters from answer sequences (expectation-maximisation, Baum-Welch).

BKT is a two-state hidden Markov model per learner and concept: the hidden state is "unknown" or
"known", an answer is correct with probability `p_guess` (unknown) or `1 - p_slip` (known), and an
unknown concept becomes known after a practice opportunity with probability `p_transit` (no
forgetting). Given many ordered answer sequences for one concept (or one item kind), EM finds the
parameters that make those sequences most likely.

Limits that matter in practice:
  - BKT is not always identifiable: different parameter sets can fit the same data about equally
    well. Bounds (`SLIP_MAX`, `GUESS_MAX`, the default `p_slip + p_guess < 1`) keep the fit in the
    meaningful region, and a fit is only trusted after it beats the defaults on held-out sequences
    (`compare_on_held_out`).
  - EM finds a local optimum; `fit` runs several starts and keeps the best likelihood.
Pure: no database, no clock, seeded randomness only.
"""

import math
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.engine.bkt import BKTParams

Sequence_ = Sequence[bool]  # one learner's answers on one concept, oldest first

SLIP_MAX = 0.3
GUESS_MAX = 0.5
EPS = 1e-6


def _clip(x: float, low: float, high: float) -> float:
    return min(max(x, low), high)


def _bounded(p_init: float, p_transit: float, p_slip: float, p_guess: float) -> BKTParams:
    p_slip = _clip(p_slip, EPS, SLIP_MAX)
    p_guess = _clip(p_guess, EPS, min(GUESS_MAX, 1 - p_slip - EPS))
    return BKTParams(
        p_init=_clip(p_init, EPS, 1 - EPS),
        p_transit=_clip(p_transit, EPS, 1 - EPS),
        p_slip=p_slip,
        p_guess=p_guess,
    )


def _emit(params: BKTParams, correct: bool) -> tuple[float, float]:
    """P(observation | unknown), P(observation | known)."""
    if correct:
        return params.p_guess, 1 - params.p_slip
    return 1 - params.p_guess, params.p_slip


def _forward_backward(
    params: BKTParams, seq: Sequence_
) -> tuple[list[tuple[float, float]], list[float], float]:
    """Posteriors P(state_t | all answers), P(unknown_t -> known_{t+1} | all), and log P(seq)."""
    n = len(seq)
    t_ = params.p_transit
    alpha: list[tuple[float, float]] = []
    scale: list[float] = []
    prev = (1 - params.p_init, params.p_init)
    for i, obs in enumerate(seq):
        if i > 0:
            prev = (prev[0] * (1 - t_), prev[0] * t_ + prev[1])
        eu, ek = _emit(params, obs)
        a = (prev[0] * eu, prev[1] * ek)
        c = a[0] + a[1]
        scale.append(c)
        prev = (a[0] / c, a[1] / c)
        alpha.append(prev)
    beta: list[tuple[float, float]] = [(1.0, 1.0)] * n
    for i in range(n - 2, -1, -1):
        eu, ek = _emit(params, seq[i + 1])
        bu, bk = beta[i + 1]
        beta[i] = (
            ((1 - t_) * eu * bu + t_ * ek * bk) / scale[i + 1],
            (ek * bk) / scale[i + 1],
        )
    gamma = []
    for (au, ak), (bu, bk) in zip(alpha, beta, strict=True):
        z = au * bu + ak * bk
        gamma.append((au * bu / z, ak * bk / z))
    learn = []
    for i in range(n - 1):
        eu, ek = _emit(params, seq[i + 1])
        learn.append(alpha[i][0] * t_ * ek * beta[i + 1][1] / scale[i + 1])
    return gamma, learn, sum(math.log(c) for c in scale)


def log_likelihood(params: BKTParams, sequences: Iterable[Sequence_]) -> float:
    return sum(_forward_backward(params, s)[2] for s in sequences if s)


@dataclass(frozen=True)
class FitResult:
    params: BKTParams
    log_likelihood: float
    iterations: int
    converged: bool
    observations: int


def _em(sequences: Sequence[Sequence_], start: BKTParams, max_iter: int, tol: float) -> FitResult:
    params, last = start, -math.inf
    observations = sum(len(s) for s in sequences)
    for iteration in range(1, max_iter + 1):
        init_known = known_total = known_wrong = unknown_total = unknown_right = 0.0
        unknown_before = learned = ll = 0.0
        for seq in sequences:
            gamma, learn, seq_ll = _forward_backward(params, seq)
            ll += seq_ll
            init_known += gamma[0][1]
            for (gu, gk), obs in zip(gamma, seq, strict=True):
                known_total += gk
                unknown_total += gu
                known_wrong += gk * (not obs)
                unknown_right += gu * obs
            unknown_before += sum(g[0] for g in gamma[:-1])
            learned += sum(learn)
        params = _bounded(
            init_known / len(sequences),
            learned / unknown_before if unknown_before > 0 else params.p_transit,
            known_wrong / known_total if known_total > 0 else params.p_slip,
            unknown_right / unknown_total if unknown_total > 0 else params.p_guess,
        )
        if ll - last < tol:
            return FitResult(params, ll, iteration, True, observations)
        last = ll
    return FitResult(params, log_likelihood(params, sequences), max_iter, False, observations)


def fit(
    sequences: Iterable[Sequence_],
    *,
    starts: int = 5,
    seed: int = 0,
    max_iter: int = 200,
    tol: float = 1e-6,
) -> FitResult:
    """Maximum-likelihood BKT parameters from answer sequences, best of `starts` EM runs."""
    data = [list(s) for s in sequences if s]
    if not data:
        raise ValueError("no answers to fit")
    rng = random.Random(seed)
    best: FitResult | None = None
    for k in range(starts):
        start = (
            BKTParams(p_init=0.2, p_transit=0.1, p_slip=0.1, p_guess=0.25)
            if k == 0
            else _bounded(
                rng.uniform(0.05, 0.6),
                rng.uniform(0.02, 0.4),
                rng.uniform(0.02, SLIP_MAX),
                rng.uniform(0.05, GUESS_MAX),
            )
        )
        result = _em(data, start, max_iter, tol)
        if best is None or result.log_likelihood > best.log_likelihood:
            best = result
    assert best is not None
    return best


# --- prediction quality ---------------------------------------------------------------------------


def predictions(params: BKTParams, seq: Sequence_) -> list[float]:
    """P(correct) for each answer, predicted from the answers before it only (no peeking)."""
    out: list[float] = []
    p = params.p_init
    for obs in seq:
        out.append(p * (1 - params.p_slip) + (1 - p) * params.p_guess)
        eu, ek = _emit(params, obs)
        known = p * ek / (p * ek + (1 - p) * eu)
        p = known + (1 - known) * params.p_transit
    return out


@dataclass(frozen=True)
class Scores:
    log_loss: float
    brier: float
    auc: float | None  # None when all answers are correct or all wrong
    n: int


def score(params: BKTParams, sequences: Iterable[Sequence_]) -> Scores:
    pairs = [
        (pred, obs)
        for seq in sequences
        for pred, obs in zip(predictions(params, seq), seq, strict=True)
    ]
    if not pairs:
        raise ValueError("no answers to score")
    log_loss = -sum(math.log(_clip(p if y else 1 - p, 1e-12, 1.0)) for p, y in pairs) / len(pairs)
    brier = sum((p - y) ** 2 for p, y in pairs) / len(pairs)
    return Scores(log_loss, brier, _auc(pairs), len(pairs))


def _auc(pairs: list[tuple[float, bool]]) -> float | None:
    """Probability a random correct answer was predicted higher than a random wrong one."""
    pos = sum(1 for _, y in pairs if y)
    neg = len(pairs) - pos
    if pos == 0 or neg == 0:
        return None
    ranked = sorted(pairs, key=lambda py: py[0])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        average_rank = (i + 1 + j) / 2  # ties share their average 1-based rank
        rank_sum += average_rank * sum(1 for _, y in ranked[i:j] if y)
        i = j
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


# --- simulation (for tests and reports) -----------------------------------------------------------


def simulate(params: BKTParams, learners: int, length: int, rng: random.Random) -> list[list[bool]]:
    """Answer sequences drawn from the BKT model itself."""
    data = []
    for _ in range(learners):
        known = rng.random() < params.p_init
        seq = []
        for i in range(length):
            if i > 0 and not known:
                known = rng.random() < params.p_transit
            seq.append(rng.random() < (1 - params.p_slip if known else params.p_guess))
        data.append(seq)
    return data
