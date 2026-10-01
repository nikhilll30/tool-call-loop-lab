"""STAGE 2: offline detector evaluation on synthetic traces. Pure offline. Never touches the network.

Dev/test split: seeds 0-9 = dev (thresholds may be tuned), seeds 100-109 = test (held out, reported separately),
hand-written legit set has split 'none' and is reported on its own.
"""
from __future__ import annotations
import csv, json
from collections import defaultdict
from pathlib import Path
from .config import SuiteConfig
from .detectors import run_all, max_adjacent_run, BASELINES, NEW
from .gen.suites import all_traces

DETS = ["exact_dup", "adjacent", "near_dup", "cycle", "distinct_ratio", "cross_turn", "combined_raw", "state_aware"]


def evaluate(suite: SuiteConfig, traces: list[dict] | None = None) -> list[dict]:
    """One row per trace: per-detector flag + first index + summary stats."""
    rows = []
    traces = traces if traces is not None else all_traces()
    from .splits import refuse_exploratory
    refuse_exploratory(traces, "floodlab.evaluate (DEV path)")
    if any(t.get("split") == "heldout" for t in traces):
        raise ValueError("held-out traces must never enter the DEV evaluation path (floodlab.evaluate); use floodlab.heldout_eval")
    for t in traces:
        res = run_all(t, suite)
        n_calls = sum(len(g["tool_calls"]) for tu in t["turns"] for g in tu["generations"])
        row = {"run_id": t["run_id"], "label": t["label"], "shape": t["shape"], "split": t["split"], "n_calls": n_calls,
               "max_adjacent_run": max_adjacent_run(t)}
        for d in DETS:
            row[d] = bool(res[d].flag)
            row[d + "_first"] = res[d].first_index
        row["baseline_any"] = row["exact_dup"] or row["adjacent"]
        row["baseline_miss_caught_by_new"] = (not row["baseline_any"]) and (row["combined_raw"] or row["state_aware"])
        rows.append(row)
    return rows


def rate(rows, det):
    return sum(r[det] for r in rows) / len(rows) if rows else float("nan")


def per_shape_table(rows, label, split):
    by = defaultdict(list)
    for r in rows:
        if r["label"] == label and r["split"] == split:
            by[r["shape"]].append(r)
    return {s: {"n": len(v), **{d: rate(v, d) for d in DETS}} for s, v in sorted(by.items())}


def summarize(rows) -> dict:
    out = {}
    for split in ("dev", "test", "none"):
        out[split] = {
            "flood": per_shape_table(rows, "flood", split),
            "legit": per_shape_table(rows, "legitimate", split),
            "flood_overall": {d: rate([r for r in rows if r["label"] == "flood" and r["split"] == split], d) for d in DETS},
            "legit_fp_overall": {d: rate([r for r in rows if r["label"] == "legitimate" and r["split"] == split], d) for d in DETS},
            "n_flood": sum(1 for r in rows if r["label"] == "flood" and r["split"] == split),
            "n_legit": sum(1 for r in rows if r["label"] == "legitimate" and r["split"] == split),
        }
    out["legit_fp_all_splits"] = {d: rate([r for r in rows if r["label"] == "legitimate"], d) for d in DETS}
    out["n_legit_all"] = sum(1 for r in rows if r["label"] == "legitimate")
    return out


def baseline_miss_table(rows, split="test"):
    """Per flood shape: how often each baseline misses, and how often new detectors catch what BOTH baselines missed."""
    by = defaultdict(list)
    for r in rows:
        if r["label"] == "flood" and r["split"] == split:
            by[r["shape"]].append(r)
    tab = []
    for s, v in sorted(by.items()):
        n = len(v)
        both_miss = [r for r in v if not r["baseline_any"]]
        tab.append({"shape": s, "n": n, "max_adjacent_run(median)": sorted(r["max_adjacent_run"] for r in v)[n // 2],
                    "exact_dup": rate(v, "exact_dup"), "adjacent": rate(v, "adjacent"),
                    "new_detectors_raw": rate(v, "combined_raw"), "state_aware": rate(v, "state_aware"),
                    "both_baselines_miss": len(both_miss) / n,
                    "caught_by_new_raw": sum(r["combined_raw"] for r in both_miss) / n,
                    "caught_by_state_aware": sum(r["state_aware"] for r in both_miss) / n,
                    "median_first_idx_exact_dup": _med([r["exact_dup_first"] for r in v]),
                    "median_first_idx_state_aware": _med([r["state_aware_first"] for r in v])})
    return tab


def _med(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


def md_table(header, rows):
    fmt = lambda x: f"{x:.2f}" if isinstance(x, float) else str(x)
    return "\n".join(["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] +
                     ["| " + " | ".join(fmt(r[h]) for h in header) + " |" for r in rows])


def write_outputs(rows, suite, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "per_trace.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    summ = summarize(rows)
    (outdir / "summary.json").write_text(json.dumps({"suite_id": suite.id, "suite_hash": suite.hash(), **summ}, indent=1, default=str))
    lines = [f"# Offline detector evaluation (SYNTHETIC data; suite `{suite.id}` hash `{suite.hash()}`)\n",
             "Detection rate per flood shape / false-positive rate per legitimate family. Not real-world rates.\n"]
    for split, title in (("dev", "DEV seeds 0-9 (tuning allowed)"), ("test", "TEST seeds 100-109 (held out)")):
        s = summ[split]
        for kind, name, lab in (("flood", "Flood detection rate", "shape"), ("legit", "False-positive rate on legitimate", "family")):
            tab = [{lab: k, **v} for k, v in s[kind].items()]
            tab.append({lab: "**OVERALL**", "n": s["n_flood" if kind == "flood" else "n_legit"],
                        **(s["flood_overall"] if kind == "flood" else s["legit_fp_overall"])})
            lines += [f"## {name} - {title}\n", md_table([lab, "n"] + DETS, tab), ""]
    s = summ["none"]
    tab = [{"trace": r["run_id"], **{d: r[d] for d in DETS}} for r in rows if r["split"] == "none"]
    lines += ["## Hand-written legitimate set (n=%d) - flagged = false positive\n" % len(tab), md_table(["trace"] + DETS, tab), ""]
    lines += ["## Baseline-miss table (TEST seeds): shapes the exact-dup / last-3-identical baselines miss\n",
              md_table(list(baseline_miss_table(rows)[0].keys()), baseline_miss_table(rows)), "",
              "## Baseline-miss table (DEV seeds)\n",
              md_table(list(baseline_miss_table(rows, "dev")[0].keys()), baseline_miss_table(rows, "dev")), ""]
    miss = [r for r in rows if r["baseline_miss_caught_by_new"] and r["split"] == "test" and r["label"] == "flood"]
    lines += ["## Explicit baseline-miss cases (TEST): both baselines silent, new detectors fire\n",
              md_table(["run_id", "shape", "n_calls", "max_adjacent_run", "combined_raw_first", "state_aware_first"], miss), ""]
    (outdir / "eval_report.md").write_text("\n".join(lines))
    return summ


def plot(rows, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tab = per_shape_table(rows, "flood", "test")
    shapes = list(tab)
    fig, ax = plt.subplots(figsize=(11, 5))
    dets = ["exact_dup", "adjacent", "combined_raw", "state_aware"]
    w = 0.2
    for i, d in enumerate(dets):
        ax.bar([x + i * w for x in range(len(shapes))], [tab[s][d] for s in shapes], w, label=d)
    ax.set_xticks([x + 1.5 * w for x in range(len(shapes))]); ax.set_xticklabels(shapes, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("detection rate (TEST seeds, SYNTHETIC floods)"); ax.set_ylim(0, 1.05)
    fp = per_shape_table(rows, "legitimate", "test")
    ax.set_title("Baselines vs new detectors  |  legit FP (test): " + ", ".join(
        f"{d}={sum(fp[s][d] for s in fp) / len(fp):.2f}" for d in dets), fontsize=9)
    ax.legend(); fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)
