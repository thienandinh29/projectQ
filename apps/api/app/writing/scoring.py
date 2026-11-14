"""The band scorer's measurement core (specs/writing/step-2.3.md). Pure: no model, no database.

The scoring service returns a model's raw output; everything that turns it into what a learner
sees, and everything the owner's evaluation measures, lives here so it is unit-tested:
- calibration of raw output to the IELTS scale (isotonic regression, pool adjacent violators);
- the range shown to the learner, from cross-validated residuals, rounded outward to half bands;
- when no band is shown (Task 1, too short, not calibrated, too wide: "không chắc");
- QWK over half-band classes, bootstrap intervals, ridge regression for the feature baseline,
  k-fold and the held-out test split.
"""

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

BAND_MIN, BAND_MAX = 0.0, 9.0
MIN_WORDS_FOR_BAND = 150
MAX_RANGE_WIDTH = 1.5  # wider than this is shown as "không chắc"
RANGE_QUANTILES = (0.10, 0.90)


def clip_band(x: float) -> float:
    return min(BAND_MAX, max(BAND_MIN, x))


def round_half(x: float) -> float:
    """Nearest half band (IELTS bands go in steps of 0.5), halves rounded up."""
    return clip_band(math.floor(x * 2 + 0.5) / 2)


def floor_half(x: float) -> float:
    return clip_band(math.floor(x * 2 + 1e-9) / 2)


def ceil_half(x: float) -> float:
    return clip_band(math.ceil(x * 2 - 1e-9) / 2)


# --- calibration ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Isotonic:
    """A non-decreasing map from raw score to band: block means at block centres, linear between."""

    xs: tuple[float, ...]
    ys: tuple[float, ...]

    def __call__(self, x: float) -> float:
        xs, ys = self.xs, self.ys
        if x <= xs[0]:
            return clip_band(ys[0])
        if x >= xs[-1]:
            return clip_band(ys[-1])
        hi = next(i for i, v in enumerate(xs) if v >= x)
        lo = hi - 1
        t = (x - xs[lo]) / (xs[hi] - xs[lo])
        return clip_band(ys[lo] + t * (ys[hi] - ys[lo]))


def fit_isotonic(raw: Sequence[float], band: Sequence[float]) -> Isotonic:
    """Pool adjacent violators: the least-squares non-decreasing fit of band on raw."""
    if len(raw) != len(band) or not raw:
        raise ValueError("need matching, non-empty raw and band lists")
    pairs = sorted(zip(raw, band, strict=True))
    blocks: list[list[float]] = []  # [sum_x, sum_y, count]
    for x, y in pairs:
        blocks.append([x, y, 1.0])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            x2, y2, n2 = blocks.pop()
            blocks[-1] = [blocks[-1][0] + x2, blocks[-1][1] + y2, blocks[-1][2] + n2]
    xs = [b[0] / b[2] for b in blocks]
    ys = [b[1] / b[2] for b in blocks]
    if len(xs) == 1:  # one block: a constant map
        return Isotonic((xs[0], xs[0] + 1.0), (ys[0], ys[0]))
    return Isotonic(tuple(xs), tuple(ys))


# --- the range shown to the learner --------------------------------------------------------


def quantile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile (numpy's default)."""
    if not values:
        raise ValueError("no values")
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (pos - lo) * (s[hi] - s[lo])


@dataclass(frozen=True)
class Calibration:
    isotonic: Isotonic
    residual_low: float  # 10th percentile of (examiner - predicted), cross-validated
    residual_high: float  # 90th percentile
    essays: int


@dataclass(frozen=True)
class BandRange:
    low: float
    high: float
    uncertain: bool  # wider than MAX_RANGE_WIDTH: shown as "không chắc"


def band_range(predicted: float, calibration: Calibration) -> BandRange:
    low = floor_half(predicted + calibration.residual_low)
    high = ceil_half(predicted + calibration.residual_high)
    return BandRange(low, high, uncertain=high - low > MAX_RANGE_WIDTH)


def no_band_reason(task: int, words: int, calibration: Calibration | None) -> str | None:
    """Why no band is shown, or None when one may be."""
    if task != 2:
        return "task1"
    if words < MIN_WORDS_FOR_BAND:
        return "too_short"
    if calibration is None:
        return "not_calibrated"
    return None


# --- metrics -------------------------------------------------------------------------------


def band_class(b: float) -> int:
    """0.0 -> 0, 0.5 -> 1, ..., 9.0 -> 18."""
    return round(clip_band(b) * 2)


def qwk(examiner: Sequence[float], predicted: Sequence[float]) -> float | None:
    """Quadratic weighted kappa over half-band classes; None when it is undefined (no spread)."""
    if len(examiner) != len(predicted) or not examiner:
        raise ValueError("need matching, non-empty lists")
    a = [band_class(x) for x in examiner]
    b = [band_class(round_half(x)) for x in predicted]
    lo, hi = min(a + b), max(a + b)
    k = hi - lo + 1
    if k == 1:
        return None
    n = len(a)
    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        observed[x - lo][y - lo] += 1
    row = [sum(r) for r in observed]
    col = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = (i - j) ** 2 / (k - 1) ** 2
            num += w * observed[i][j]
            den += w * row[i] * col[j] / n
    return None if den == 0 else 1 - num / den


def bootstrap_interval(
    examiner: Sequence[float],
    predicted: Sequence[float],
    stat: Callable[[Sequence[float], Sequence[float]], float | None],
    *,
    resamples: int = 2000,
    seed: int = 0,
    level: float = 0.95,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval of `stat`, resampling essays with replacement."""
    rng = random.Random(seed)
    n = len(examiner)
    values = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        v = stat([examiner[i] for i in idx], [predicted[i] for i in idx])
        if v is not None:
            values.append(v)
    if len(values) < resamples // 2:
        return None  # mostly undefined: say so rather than report a narrow interval
    tail = (1 - level) / 2
    return quantile(values, tail), quantile(values, 1 - tail)


def mae(examiner: Sequence[float], predicted: Sequence[float]) -> float:
    return sum(abs(e - p) for e, p in zip(examiner, predicted, strict=True)) / len(examiner)


def within_half(examiner: Sequence[float], predicted: Sequence[float]) -> float:
    pairs = zip(examiner, predicted, strict=True)
    return sum(abs(e - round_half(p)) <= 0.5 for e, p in pairs) / len(examiner)


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return None if sx == 0 or sy == 0 else sxy / (sx * sy)


# --- the feature baseline: ridge regression ------------------------------------------------


@dataclass(frozen=True)
class Ridge:
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    intercept: float

    def __call__(self, features: Sequence[float]) -> float:
        z = [(f - m) / s for f, m, s in zip(features, self.means, self.scales, strict=True)]
        return self.intercept + sum(w * v for w, v in zip(self.weights, z, strict=True))


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (a is small: one row per feature)."""
    n = len(b)
    m = [[*row[:], b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        for r in range(n):
            if r != col:
                f = m[r][col] / m[col][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col], strict=True)]
    return [m[i][n] / m[i][i] for i in range(n)]


def fit_ridge(x: Sequence[Sequence[float]], y: Sequence[float], alpha: float = 1.0) -> Ridge:
    """Ridge on standardised features; the intercept is not penalised."""
    if not x or len(x) != len(y):
        raise ValueError("need matching, non-empty rows and targets")
    n, d = len(x), len(x[0])
    means = [sum(r[j] for r in x) / n for j in range(d)]
    scales = [math.sqrt(sum((r[j] - means[j]) ** 2 for r in x) / n) or 1.0 for j in range(d)]
    z = [[(r[j] - means[j]) / scales[j] for j in range(d)] for r in x]
    y_mean = sum(y) / n
    yc = [v - y_mean for v in y]
    gram = [[sum(r[i] * r[j] for r in z) + (alpha if i == j else 0.0) for j in range(d)]
            for i in range(d)]  # fmt: skip
    rhs = [sum(r[i] * t for r, t in zip(z, yc, strict=True)) for i in range(d)]
    return Ridge(tuple(means), tuple(scales), tuple(_solve(gram, rhs)), y_mean)


# --- splits --------------------------------------------------------------------------------


def held_out_split(ids: Sequence[str], fraction: float = 0.3, seed: int = 0) -> list[str]:
    """The held-out test ids: a seeded random `fraction`, set aside before anything is tuned."""
    pool = sorted(set(ids))
    if len(pool) != len(ids):
        raise ValueError("essay ids must be unique")
    k = max(1, round(len(pool) * fraction))
    return sorted(random.Random(seed).sample(pool, k))


def kfold(ids: Sequence[str], k: int = 5, seed: int = 0) -> list[tuple[list[str], list[str]]]:
    """k (train, validation) splits; every id is validated exactly once."""
    pool = sorted(ids)
    random.Random(seed).shuffle(pool)
    folds = [pool[i::k] for i in range(k)]
    return [
        (sorted(x for j, f in enumerate(folds) if j != i for x in f), sorted(folds[i]))
        for i in range(k)
    ]
