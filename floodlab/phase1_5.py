"""Phase 1.5 runner:  python -m floodlab.phase1_5 [--outdir results/phase1_5] [--freeze]
Loads the held-out set (verifying its pre-registered sha256), evaluates every pre-registered policy, applies the pre-registered
selection rule, writes results. --freeze writes the selected candidate into configs/frozen and calls the freeze tooling. No tuning here."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
from .heldout.dataset import PATH
from .heldout_eval import run
from .policies import selectable_policies, guard_config_for, SUITES
from .trace import read_jsonl
from . import freeze

ROOT = Path(__file__).resolve().parent.parent


def registered_sha() -> str:
    return re.search(r"dataset sha256.*?`([0-9a-f]{64})`", (ROOT / "docs" / "SELECTION_PROCEDURE.md").read_text(), re.S).group(1)


def fmt_ci(ci): return f"[{ci[0]*100:.1f}, {ci[1]*100:.1f}]"


def markdown(res) -> str:
    L = ["| policy | sel | detect (CP 95% CI) | FP = interruption (CP 95% CI) | latency after start: median [IQR] max | latency total: median max | frac. calls lost when interrupted |", "|---|---|---|---|---|---|---|"]
    for r in res["results"]:
        a = r["latency_after_start_q25_med_q75"]; t = r["latency_total_q25_med_q75"]
        L.append(f"| {r['policy']} | {'Y' if r['selectable'] else 'diag'} | {r['detected']}/{r['n_flood']} = {r['detection_rate']*100:.1f}% {fmt_ci(r['detection_ci_cp'])} | "
                 f"{r['fp']}/{r['n_legit']} = {r['fp_rate']*100:.1f}% {fmt_ci(r['fp_ci_cp'])} | "
                 f"{'-' if r['latency_after_start_max'] is None else f'{a[1]:.0f} [{a[0]:.0f}-{a[2]:.0f}] max {r['latency_after_start_max']}'} (misses as len: {r['latency_after_start_median_misses_as_trace_length']:.0f}) | "
                 f"{'-' if r['latency_total_max'] is None else f'{t[1]:.0f} max {r['latency_total_max']}'} | {r['mean_frac_calls_not_executed_when_interrupted']:.2f} |")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--outdir", default=str(ROOT / "results" / "phase1_5")); ap.add_argument("--freeze", action="store_true")
    a = ap.parse_args(argv)
    actual = hashlib.sha256(PATH.read_bytes()).hexdigest()
    if actual != registered_sha():
        print(f"REFUSING: held-out dataset sha256 {actual} != pre-registered {registered_sha()}"); return 2
    traces = read_jsonl(PATH)
    out = Path(a.outdir)
    res = run(traces, out)
    (out / "results_table.md").write_text(markdown(res) + "\n")
    print(markdown(res)); print("\nSELECTION:", json.dumps(res["selection"]))
    if a.freeze:
        sel = res["selection"]["selected"]
        if sel is None:
            print("Nothing qualifies -> NOT freezing (pre-registered)."); return 1
        pol = next(p for p in selectable_policies() if p.id == sel)
        if pol.kind not in ("state_aware", "cap"):
            print(f"Selected {sel} is a baseline detector without a guard-config form; freeze it via a policy id record only."); 
        cfg = guard_config_for(pol) if pol.kind in ("state_aware", "cap") else None
        if cfg is None: return 3
        freeze.dump_config(cfg, freeze.DRAFT_CFG, header=f"# Selected by the pre-registered procedure (policy {sel}) on held-out v1 sha256 {actual}\n")
        freeze.DRAFT_FP.write_text(json.dumps({"status": "FROZEN-CANDIDATE", "max_fp_rate": 0.05, "method": "upper bound of Clopper-Pearson two-sided 95% CI on legit interruption rate must be <= 0.05",
                                               "policy": sel, "heldout_sha256": actual, "suite": "heldout_v1 legit (n=122)"}, indent=1))
        print(json.dumps(freeze.freeze(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
