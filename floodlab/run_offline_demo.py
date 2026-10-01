"""One-command offline demo:  python -m floodlab.run_offline_demo   (or: make demo)

Runs Stage 1' (synthetic trace generation), Stage 2 (detector eval + plot), verifies frozen-config tooling status,
and runs an end-to-end mock-upstream harness run + a guarded run. ZERO network to any LLM provider (loopback only).
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from .config import SuiteConfig
from .evaluate import evaluate, write_outputs, plot, baseline_miss_table, md_table
from .gen.suites import all_traces
from .trace import write_jsonl, read_jsonl
from . import freeze

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    out = ROOT / "results"
    (ROOT / "data" / "traces").mkdir(parents=True, exist_ok=True)
    print("== Stage 1' - synthetic trace generation (SYNTHETIC; not real-world) ==")
    traces = all_traces()
    n = write_jsonl(ROOT / "data" / "traces" / "synthetic_all.jsonl", traces)
    print(f"wrote {n} traces to data/traces/synthetic_all.jsonl "
          f"(flood={sum(t['label']=='flood' for t in traces)}, legitimate={sum(t['label']=='legitimate' for t in traces)})")
    print("\n== Stage 2 - offline detector evaluation ==")
    cfg = freeze.load_config(ROOT / "configs" / "frozen" / "detector_guard.DRAFT.yaml")
    suite = cfg.suite
    rows = evaluate(suite, read_jsonl(ROOT / "data" / "traces" / "synthetic_all.jsonl"))
    summ = write_outputs(rows, suite, out)
    plot(rows, out / "baseline_vs_new.png")
    print(f"suite={suite.id} hash={suite.hash()}; wrote results/eval_report.md, per_trace.csv, summary.json, baseline_vs_new.png")
    print("\nFalse-positive rate on legitimate suite (all splits, n=%d):" % summ["n_legit_all"])
    for d, v in summ["legit_fp_all_splits"].items():
        print(f"  {d:15s} {v:.3f}")
    print("\nBaseline-miss table (TEST seeds, SYNTHETIC):")
    print(md_table(list(baseline_miss_table(rows)[0].keys()), baseline_miss_table(rows)))
    print("\n== Stage 3 - freeze tooling status (DRAFT only; nothing is frozen) ==")
    print(freeze.status_text())
    print("\n== Stage 4 tooling smoke test: mock upstream + harness + guard (loopback only, $0) ==")
    from .smoke import run_smoke
    run_smoke(out)
    print("\nDONE. No live API calls were made. Spend: $0.00")
    return 0


if __name__ == "__main__":
    sys.exit(main())
