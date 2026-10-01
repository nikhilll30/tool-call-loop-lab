"""End-to-end smoke for the demo: harness -> mock upstream, and harness -> guard -> mock upstream. Loopback only."""
from __future__ import annotations
import json, tempfile
from pathlib import Path
from .config import GuardConfig
from .freeze import load_config
from .guard import create_guard_app
from .harness import run_scenario, Caps, Budget
from .mock_upstream.app import create_app
from .scenarios import Scenario
from .servers import LocalServer
from .trace import write_jsonl, validate


def run_smoke(outdir: Path):
    cfg = load_config()
    ledger = Path(__file__).resolve().parent.parent / "spend_ledger.jsonl"   # $0 entries only
    traces = []
    up_app = create_app()
    with LocalServer(up_app) as up:
        sc = Scenario("pagination", "plain", 3)
        t = run_scenario(sc, up.url, ledger_path=ledger); traces.append(t)
        print(f"  normal run   : {t['termination_reason']}, turns={len(t['turns'])}, valid={not validate(t)}")
        sc = Scenario("fan_out", "rotating_argument", 3)
        t = run_scenario(sc, up.url, delta_mode="incremental", behavior="rotating35", flood_kwargs={"n_calls": 300, "turns": 1},
                         ledger_path=ledger, guard_config="off"); traces.append(t)
        n = sum(len(g["tool_calls"]) for tu in t["turns"] for g in tu["generations"])
        print(f"  flood, guard OFF (incremental deltas): {n} calls executed, termination={t['termination_reason']}")
        guard_app = create_guard_app(up.url, cfg)
        with LocalServer(guard_app) as g:
            t = run_scenario(sc, g.url, behavior="rotating35", flood_kwargs={"n_calls": 300, "turns": 1},
                             guard_config={"id": cfg.id, "hash": cfg.hash()}, ledger_path=ledger, suite=cfg.suite); traces.append(t)
            n = sum(len(g_["tool_calls"]) for tu in t["turns"] for g_ in tu["generations"])
            ev = guard_app.state.events[-1]
            print(f"  flood, guard ON: {n} calls reached tools, termination={t['termination_reason']}, "
                  f"guard reason={ev['reason']} via {ev['detector']} after {ev['calls_seen']} calls")
        d = up_app.state.disconnects
        print(f"  upstream saw {len(d)} client disconnect(s); tokens 'generated' at disconnect: {[x['tokens_generated'] for x in d]} "
              f"(planned {[x['total_planned_tokens'] for x in d]})")
    write_jsonl(outdir / "smoke_traces.jsonl", traces)
    print("  wrote results/smoke_traces.jsonl (mock-upstream runs; SYNTHETIC)")
