"""(v) Cross-turn detector: identical / near-identical batches in consecutive generations (#2509 shape)."""
from __future__ import annotations
from collections import Counter
from ..config import CrossTurnConfig
from .base import DetectorResult, as_gens, norm_sig, state_changed


def _jaccard(a: Counter, b: Counter) -> float:
    inter = sum((a & b).values())
    union = sum((a | b).values())
    return inter / union if union else 1.0


def cross_turn(x, cfg: CrossTurnConfig = CrossTurnConfig()) -> DetectorResult:
    gens = [g for g in as_gens(x)]
    streak, suppressed, best = 0, 0, 0.0
    for k in range(1, len(gens)):
        a, b = gens[k - 1], gens[k]
        if len(a) < cfg.min_batch or len(b) < cfg.min_batch:
            streak = 0
            continue
        sa = [norm_sig(c, cfg.volatile_fields) for c in a]
        sb = [norm_sig(c, cfg.volatile_fields) for c in b]
        sim = _jaccard(Counter(sa), Counter(sb))
        best = max(best, sim)
        if sim >= cfg.min_similarity:
            streak += 1
            if streak >= cfg.min_streak:
                if cfg.use_state:
                    region = a + b
                    changed, _ = state_changed(region, sa + sb, cfg.state_change_frac)
                    if changed:
                        suppressed += 1
                        continue
                return DetectorResult("cross_turn", True, b[-1].gidx, "CROSS_TURN_BATCH_REPEAT",
                                      {"similarity": round(sim, 3), "batch_size": len(b), "streak": streak + 1,
                                       "generation_index": k, "suppressed_before": suppressed})
        else:
            streak = 0
    return DetectorResult("cross_turn", False, None, "OK" if not suppressed else "SUPPRESSED_STATE_CHANGED",
                          {"max_similarity": round(best, 3), "suppressed_candidates": suppressed})
