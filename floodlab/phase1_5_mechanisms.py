"""Post-hoc mechanism probe for error explanations (reads only; changes nothing). Output: results/phase1_5/mechanism_notes.txt"""
from __future__ import annotations
from collections import defaultdict, Counter
from pathlib import Path
from .heldout.dataset import PATH
from .policies import S0
from .trace import read_jsonl, flat_calls
from .detectors import run_all
from .detectors.base import norm_sig

ROOT = Path(__file__).resolve().parent.parent


def score(calls, sigs):
    by = defaultdict(list)
    for c, s in zip(calls, sigs): by[s].append(c.result_hash)
    sc = [(len(set(h)) - 1) / (len(h) - 1) for h in by.values() if len(h) > 1 and None not in h]
    return round(sum(sc) / len(sc), 2) if sc else None, len(by), len(calls)


def main():
    out = []
    ts = {t["run_id"]: t for t in read_jsonl(PATH)}
    for rid in ["ho-F1-1000", "ho-F2-1000", "ho-F4-1000", "ho-F5-1000", "ho-F7-1000", "ho-F7-1001", "ho-L1-1000", "ho-L5-1001", "ho-L6-1002",
                "ho-L7-1000", "ho-L8-1000", "ho-L11-1000", "ho-L4-1000", "ho-hw-L-poll60", "ho-hw-F-startdone3"]:
        t = ts.get(rid)
        if not t: continue
        calls = flat_calls(t); r = run_all(t, S0)
        sigs = [norm_sig(c, S0.near_dup.volatile_fields) for c in calls]
        raw = {k: (r[k].first_index, r[k].reason) for k in ("exact_dup", "adjacent", "near_dup", "cycle", "distinct_ratio", "cross_turn") if r[k].flag}
        fa = r["near_dup"].first_index if r["near_dup"].flag else r["cycle"].first_index if r["cycle"].flag else None
        upto = calls[: (fa + 1) if fa is not None else len(calls)]
        sc = score(upto, sigs[: len(upto)])
        out.append(f"{rid} label={t['label']} n={len(calls)} loop_start={t['ground_truth']['loop_start_index']} raw_fired={raw}\n"
                   f"    state score(mean per-repeated-signature (distinct results-1)/(occurrences-1)) up to first raw fire: {sc} [score, distinct sigs, calls]; suppress threshold={S0.near_dup.state_change_frac}\n"
                   f"    state_aware: flag={r['state_aware'].flag} first={r['state_aware'].first_index} suppressed={r['state_aware'].evidence.get('suppressed')}")
    (ROOT / "results" / "phase1_5" / "mechanism_notes.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
