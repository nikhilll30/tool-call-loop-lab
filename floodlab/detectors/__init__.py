"""Detector library. Every detector: fn(trace_or_generations, cfg) -> DetectorResult."""
from __future__ import annotations
from dataclasses import replace
from ..config import SuiteConfig
from .base import DetectorResult, as_gens
from .baselines import exact_dup, adjacent, max_adjacent_run
from .near_dup import near_dup
from .cycle import cycle
from .distinct_ratio import distinct_ratio
from .cross_turn import cross_turn

BASELINES = ("exact_dup", "adjacent")
NEW = ("near_dup", "cycle", "distinct_ratio", "cross_turn")
ALL = BASELINES + NEW + ("combined_raw", "state_aware")


def _combine(name: str, results: list[DetectorResult]) -> DetectorResult:
    fired = [r for r in results if r.flag]
    if not fired:
        return DetectorResult(name, False, None, "OK", {})
    first = min(fired, key=lambda r: r.first_index)
    return DetectorResult(name, True, first.first_index, first.reason,
                          {"fired": {r.detector: r.first_index for r in fired}, "earliest": first.detector})


def state_aware(x, suite: SuiteConfig) -> DetectorResult:
    """(vi) The four new detectors with state-based suppression on: flags are dropped when tool results between
    the repeated calls differ (result hashes). Cannot suppress when result hashes are absent."""
    s = suite.with_state(True)
    gens = as_gens(x)
    rs = [near_dup(gens, s.near_dup), cycle(gens, s.cycle), distinct_ratio(gens, s.distinct_ratio), cross_turn(gens, s.cross_turn)]
    r = _combine("state_aware", rs)
    r.evidence["suppressed"] = {q.detector: q.evidence.get("suppressed_candidates", 0) for q in rs}
    return r


def run_all(x, suite: SuiteConfig = SuiteConfig()) -> dict[str, DetectorResult]:
    gens = as_gens(x)
    out = {
        "exact_dup": exact_dup(gens, suite.exact_dup),
        "adjacent": adjacent(gens, suite.adjacent),
        "near_dup": near_dup(gens, replace(suite.near_dup, use_state=False)),
        "cycle": cycle(gens, replace(suite.cycle, use_state=False)),
        "distinct_ratio": distinct_ratio(gens, replace(suite.distinct_ratio, use_state=False)),
        "cross_turn": cross_turn(gens, replace(suite.cross_turn, use_state=False)),
    }
    out["combined_raw"] = _combine("combined_raw", [out[k] for k in NEW])
    out["state_aware"] = state_aware(gens, suite)
    return out
