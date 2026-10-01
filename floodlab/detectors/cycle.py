"""(iii) Cycle detection: a period p (1..max_period) over call signatures repeating >= min_reps times,
within or across generations. O(n * max_period) via per-period run counters."""
from __future__ import annotations
from ..config import CycleConfig
from .base import DetectorResult, as_gens, flat, norm_sig, state_changed


def cycle(x, cfg: CycleConfig = CycleConfig()) -> DetectorResult:
    calls = flat(as_gens(x))
    sigs = [norm_sig(c, cfg.volatile_fields) for c in calls]
    P = cfg.max_period
    run = [0] * (P + 1)   # run[p] = consecutive positions i with sig[i] == sig[i-p]
    suppressed = 0
    for i, s in enumerate(sigs):
        for p in range(1, min(P, i) + 1):
            run[p] = run[p] + 1 if sigs[i - p] == s else 0
        for p in range(1, min(P, i) + 1):
            need = max(p * (cfg.min_reps - 1), cfg.min_len - p)
            if run[p] >= need:
                span = p + run[p]
                lo = i - span + 1
                if cfg.use_state:
                    changed, score = state_changed(calls[lo:i + 1], sigs[lo:i + 1], cfg.state_change_frac)
                    if changed:
                        suppressed += 1
                        break
                return DetectorResult("cycle", True, i, "CYCLE",
                                      {"period": p, "repeats": round(span / p, 2), "span_calls": span,
                                       "pattern": sigs[i - p + 1:i + 1][:8], "start_index": lo,
                                       "suppressed_before": suppressed})
    return DetectorResult("cycle", False, None, "OK" if not suppressed else "SUPPRESSED_STATE_CHANGED",
                          {"suppressed_candidates": suppressed})
