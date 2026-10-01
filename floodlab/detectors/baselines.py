"""Baselines: (i) Xiaomi-style exact within-generation duplicates; (ii) 'last N identical' adjacent guard."""
from __future__ import annotations
from ..config import ExactDupConfig, AdjacentConfig
from .base import DetectorResult, as_gens, raw_sig, flat


def exact_dup(x, cfg: ExactDupConfig = ExactDupConfig()) -> DetectorResult:
    """Counts calls that exactly repeat an earlier call (name + canonical args) within the SAME generation.
    Cross-generation repetition is invisible by construction (this replicates the vendor metric's scope)."""
    worst = 0
    for g in as_gens(x):
        seen, dups = set(), 0
        for c in g:
            s = raw_sig(c)
            if s in seen:
                dups += 1
                if dups >= cfg.min_dups:
                    return DetectorResult("exact_dup", True, c.gidx, "EXACT_DUP_WITHIN_GENERATION",
                                          {"dups_at_fire": dups, "generation_len": len(g), "turn": c.turn, "gen": c.gen})
            seen.add(s)
        worst = max(worst, dups)
    return DetectorResult("exact_dup", False, None, "OK", {"max_dups_in_a_generation": worst})


def adjacent(x, cfg: AdjacentConfig = AdjacentConfig()) -> DetectorResult:
    """'Last N identical': fires when the last N calls in emission order (across generations) are identical."""
    calls, run, best = flat(as_gens(x)), 0, 0
    prev = None
    for c in calls:
        s = raw_sig(c)
        run = run + 1 if s == prev else 1
        prev = s
        best = max(best, run)
        if run >= cfg.n:
            return DetectorResult("adjacent", True, c.gidx, "ADJACENT_IDENTICAL_RUN", {"run": run, "call": c.name})
    return DetectorResult("adjacent", False, None, "OK", {"max_adjacent_run": best})


def max_adjacent_run(x) -> int:
    calls, run, best, prev = flat(as_gens(x)), 0, 0, None
    for c in calls:
        s = raw_sig(c)
        run = run + 1 if s == prev else 1
        prev = s
        best = max(best, run)
    return best
