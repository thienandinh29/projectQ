"""Small-sample statistics: every rate is reported with the interval it can honestly support.

A labelled sample of 50 items cannot prove a 5% error rate; an interval says what it can prove. The
exact (Clopper-Pearson) interval is used because it never claims more certainty than the data give.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import comb


@dataclass(frozen=True)
class Rate:
    """`k` of `n` with a 95% interval (None when n is 0: there is nothing to estimate)."""

    k: int
    n: int
    low: float | None
    high: float | None

    @property
    def point(self) -> float | None:
        return self.k / self.n if self.n else None

    def __str__(self) -> str:
        if self.n == 0 or self.low is None or self.high is None or self.point is None:
            return "n/a (0 cases)"
        return f"{self.k}/{self.n} = {self.point:.0%} (95%: {self.low:.0%} to {self.high:.0%})"


def _cdf_le(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Exact two-sided interval for a binomial proportion."""
    if n < 1 or not 0 <= k <= n:
        raise ValueError(f"need 0 <= k <= n and n >= 1, got k={k}, n={n}")
    if not 0 < confidence < 1:
        raise ValueError("confidence must be between 0 and 1")
    tail = (1 - confidence) / 2

    low = 0.0
    if k > 0:  # smallest p with P(X >= k) >= tail
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if 1 - _cdf_le(k - 1, n, mid) < tail:
                lo = mid
            else:
                hi = mid
        low = hi
    high = 1.0
    if k < n:  # largest p with P(X <= k) >= tail
        lo, hi = 0.0, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if _cdf_le(k, n, mid) >= tail:
                lo = mid
            else:
                hi = mid
        high = lo
    return low, high


def rate(k: int, n: int, confidence: float = 0.95) -> Rate:
    if n == 0:
        if k != 0:
            raise ValueError("k must be 0 when n is 0")
        return Rate(0, 0, None, None)
    low, high = clopper_pearson(k, n, confidence)
    return Rate(k, n, low, high)


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float | None:
    """Agreement between two labelers beyond chance (1 = perfect, 0 = chance); None if undefined."""
    if len(a) != len(b):
        raise ValueError("both labelers must label the same cases")
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    classes = set(a) | set(b)
    expected = sum((a.count(c) / n) * (b.count(c) / n) for c in classes)
    if expected == 1:  # everyone always said the same single class: kappa is undefined
        return None
    return (observed - expected) / (1 - expected)
