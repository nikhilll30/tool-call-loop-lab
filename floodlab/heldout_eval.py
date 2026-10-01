"""Phase 1.5: evaluate pre-registered policies on a ground-truth-labelled set, select per docs/SELECTION_PROCEDURE.md, write results.
This module (unlike floodlab/heldout/) imports detectors. It is NOT used by the dev evaluation path (floodlab/evaluate.py)."""
from __future__ import annotations
import csv, json
from pathlib import Path
from .policies import selectable_policies, diagnostic_policies, Policy
from .stats import clopper_pearson, wilson, boot_median_ci, quartiles
from .trace import flat_calls, read_jsonl

TARGET_UB = 0.05
DETECTION_FLOOR = 0.30


def n_calls(t) -> int:
    return len(flat_calls(t))


def evaluate_policy(p: Policy, traces: list[dict]) -> dict:
    per = []
    for t in traces:
        i, info = p.intervention(t)
        gt = t["ground_truth"]; n = n_calls(t)
        per.append({"run_id": t["run_id"], "structure": gt["structure"], "label": gt["label"], "loop_start": gt["loop_start_index"],
                    "n_calls": n, "intervention": i, "by": info.get("by"), "all": info.get("all")})
    floods = [r for r in per if r["label"] == "flood"]; legit = [r for r in per if r["label"] == "legitimate"]
    det = [r for r in floods if r["intervention"] is not None]
    fp = [r for r in legit if r["intervention"] is not None]
    lat_after = [max(0, r["intervention"] - r["loop_start"]) for r in det]
    lat_tot = [r["intervention"] for r in det]
    lat_after_all = lat_after + [r["n_calls"] - r["loop_start"] for r in floods if r["intervention"] is None]
    premature = [r["run_id"] for r in det if r["intervention"] < r["loop_start"]]
    frac_lost = [(r["n_calls"] - r["intervention"]) / r["n_calls"] for r in fp]
    q = quartiles(lat_after); qt = quartiles(lat_tot); qa = quartiles(lat_after_all)
    out = {
        "policy": p.id, "selectable": p.selectable, "n_flood": len(floods), "n_legit": len(legit),
        "detected": len(det), "detection_rate": len(det) / len(floods),
        "detection_ci_cp": clopper_pearson(len(det), len(floods)), "detection_ci_wilson": wilson(len(det), len(floods)),
        "fp": len(fp), "fp_rate": len(fp) / len(legit), "fp_ci_cp": clopper_pearson(len(fp), len(legit)), "fp_ci_wilson": wilson(len(fp), len(legit)),
        "interruption_rate": len(fp) / len(legit), "interruption_ci_cp": clopper_pearson(len(fp), len(legit)),
        "mean_frac_calls_not_executed_when_interrupted": (sum(frac_lost) / len(frac_lost)) if frac_lost else 0.0,
        "latency_after_start_q25_med_q75": q, "latency_after_start_max": max(lat_after) if lat_after else None,
        "latency_after_start_median_ci": boot_median_ci(lat_after),
        "latency_total_q25_med_q75": qt, "latency_total_max": max(lat_tot) if lat_tot else None,
        "latency_after_start_median_misses_as_trace_length": qa[1],
        "premature_interventions": premature,
        "false_negatives": [r["run_id"] for r in floods if r["intervention"] is None],
        "false_positives": [{"run_id": r["run_id"], "structure": r["structure"], "at": r["intervention"], "n_calls": r["n_calls"], "by": r["by"]} for r in fp],
    }
    return out, per


def per_structure(per: list[dict]) -> dict:
    d: dict = {}
    for r in per:
        s = d.setdefault(r["structure"], {"label": r["label"], "n": 0, "intervened": 0})
        s["n"] += 1; s["intervened"] += r["intervention"] is not None
    return d


def select(results: list[dict]) -> dict:
    """Pre-registered rule. results: metrics dicts for selectable policies only."""
    q = [r for r in results if r["selectable"] and r["interruption_ci_cp"][1] <= TARGET_UB and r["detection_rate"] >= DETECTION_FLOOR]
    if not q:
        return {"selected": None, "qualifying": [], "reason": "no selectable policy has legit-interruption CP upper bound <= %.3f and detection >= %.2f" % (TARGET_UB, DETECTION_FLOOR)}
    ncomp = lambda pid: 1 + ("+cap" in pid)
    q.sort(key=lambda r: (-r["detection_rate"], r["latency_after_start_median_misses_as_trace_length"], ncomp(r["policy"]), r["policy"]))
    return {"selected": q[0]["policy"], "qualifying": [r["policy"] for r in q], "reason": "highest detection among qualifying; tie-breaks per SELECTION_PROCEDURE.md"}


def run(traces: list[dict], outdir: Path) -> dict:
    from .splits import refuse_exploratory
    refuse_exploratory(traces, "floodlab.heldout_eval (HELD-OUT path)")
    outdir.mkdir(parents=True, exist_ok=True)
    allres, pers, structs = [], {}, {}
    for p in selectable_policies() + diagnostic_policies():
        m, per = evaluate_policy(p, traces)
        allres.append(m); pers[p.id] = per; structs[p.id] = per_structure(per)
    sel = select(allres)
    (outdir / "metrics.json").write_text(json.dumps({"results": allres, "selection": sel, "per_structure": structs}, indent=1, default=str))
    with open(outdir / "per_trace_outcomes.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["policy", "run_id", "structure", "label", "loop_start", "n_calls", "intervention_index", "by"])
        for pid, per in pers.items():
            for r in per: w.writerow([pid, r["run_id"], r["structure"], r["label"], r["loop_start"], r["n_calls"], r["intervention"], r["by"]])
    return {"results": allres, "selection": sel, "per_structure": structs, "per_trace": pers}
