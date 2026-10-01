"""(ii) Near-duplicate detector: normalized argument distance, ignoring volatile fields."""
from __future__ import annotations
from difflib import SequenceMatcher
from ..canon import flatten, drop_volatile
from ..config import NearDupConfig
from .base import DetectorResult, as_gens, flat, norm_sig, state_changed


def _leaves(c, volatile) -> dict:
    obj = c.args_obj
    if obj is None:
        return {"<raw>": c.args}
    return flatten(drop_volatile(obj, volatile))


def _leaf_dist(a, b) -> float:
    if a == b:
        return 0.0
    if isinstance(a, str) and isinstance(b, str) and min(len(a), len(b)) >= 20:
        return 1.0 - SequenceMatcher(None, a, b).ratio()   # long free text: tiny edits are tiny distances
    return 1.0                                              # short strings / numbers / bools: any change counts fully


def arg_distance(la: dict, lb: dict) -> float:
    keys = set(la) | set(lb)
    if not keys:
        return 0.0
    return sum(_leaf_dist(la.get(k), lb.get(k)) if (k in la and k in lb) else 1.0 for k in keys) / len(keys)


def near_dup(x, cfg: NearDupConfig = NearDupConfig()) -> DetectorResult:
    calls = flat(as_gens(x))
    leaves = [_leaves(c, cfg.volatile_fields) for c in calls]
    sigs = [norm_sig(c, cfg.volatile_fields) for c in calls]
    cache: dict = {}
    suppressed = 0
    for i, c in enumerate(calls):
        lo = max(0, i - cfg.window + 1)
        hits = []
        for j in range(lo, i):
            if calls[j].name != c.name:
                continue
            if sigs[j] == sigs[i]:
                d = 0.0
            else:
                k = (sigs[j], sigs[i])
                if k not in cache:
                    cache[k] = arg_distance(leaves[j], leaves[i])
                d = cache[k]
            if d <= cfg.max_dist:
                hits.append(j)
        if len(hits) + 1 >= cfg.min_repeats:
            if cfg.use_state:
                idx = hits + [i]
                changed, score = state_changed([calls[k] for k in idx], [sigs[k] for k in idx], cfg.state_change_frac)
                if changed:
                    suppressed += 1
                    continue
            return DetectorResult("near_dup", True, c.gidx, "NEAR_DUPLICATE_ARGS",
                                  {"tool": c.name, "near_dups_in_window": len(hits) + 1, "window": cfg.window,
                                   "max_dist": cfg.max_dist, "suppressed_before": suppressed})
    return DetectorResult("near_dup", False, None, "OK" if not suppressed else "SUPPRESSED_STATE_CHANGED",
                          {"suppressed_candidates": suppressed})
