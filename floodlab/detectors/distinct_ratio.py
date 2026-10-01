"""(iv) Distinct-input-ratio / low-entropy detector over a sliding window of call signatures."""
from __future__ import annotations
import math
from collections import Counter
from ..config import DistinctRatioConfig
from .base import DetectorResult, as_gens, flat, norm_sig, state_changed


def distinct_ratio(x, cfg: DistinctRatioConfig = DistinctRatioConfig()) -> DetectorResult:
    calls = flat(as_gens(x))
    sigs = [norm_sig(c, cfg.volatile_fields) for c in calls]
    W = cfg.window
    if len(calls) < W:
        return DetectorResult("distinct_ratio", False, None, "OK", {"note": "fewer calls than window"})
    cnt = Counter(sigs[:W])
    suppressed = 0
    for i in range(W - 1, len(calls)):
        if i >= W:
            cnt[sigs[i]] += 1
            old = sigs[i - W]
            cnt[old] -= 1
            if cnt[old] == 0:
                del cnt[old]
        ratio = len(cnt) / W
        ent = -sum((v / W) * math.log2(v / W) for v in cnt.values())
        nent = ent / math.log2(W)
        if ratio <= cfg.max_ratio or nent <= cfg.max_norm_entropy:
            if cfg.use_state:
                lo = i - W + 1
                changed, _ = state_changed(calls[lo:i + 1], sigs[lo:i + 1], cfg.state_change_frac)
                if changed:
                    suppressed += 1
                    continue
            return DetectorResult("distinct_ratio", True, i, "LOW_DISTINCT_RATIO" if ratio <= cfg.max_ratio else "LOW_ENTROPY",
                                  {"distinct": len(cnt), "window": W, "ratio": round(ratio, 3), "norm_entropy": round(nent, 3),
                                   "suppressed_before": suppressed})
    return DetectorResult("distinct_ratio", False, None, "OK" if not suppressed else "SUPPRESSED_STATE_CHANGED",
                          {"suppressed_candidates": suppressed})
