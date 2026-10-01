"""Exact / Wilson binomial intervals and bootstrap median (no scipy)."""
from __future__ import annotations
import math
import numpy as np


def _binom_cdf(k, n, p):
    if p <= 0: return 1.0
    if p >= 1: return 1.0 if k >= n else 0.0
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact two-sided (1-alpha) interval by bisection."""
    def solve(f, lo=0.0, hi=1.0):
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid): hi = mid
            else: lo = mid
        return (lo + hi) / 2
    lower = 0.0 if k == 0 else solve(lambda p: 1 - _binom_cdf(k - 1, n, p) >= alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: _binom_cdf(k, n, p) <= alpha / 2, 0.0, 1.0)
    return lower, upper


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0: return (float("nan"),) * 2
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def boot_median_ci(xs, n_boot=2000, seed=20260929):
    if not len(xs): return (float("nan"),) * 2
    rng = np.random.default_rng(seed); a = np.asarray(xs, float)
    m = [np.median(rng.choice(a, size=len(a), replace=True)) for _ in range(n_boot)]
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def quartiles(xs):
    if not len(xs): return (float("nan"),) * 3
    a = np.asarray(xs, float)
    return float(np.percentile(a, 25)), float(np.median(a)), float(np.percentile(a, 75))
