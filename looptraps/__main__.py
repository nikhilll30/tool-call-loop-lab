"""CLI:  python -m looptraps list | demo [--env NAME] | fixtures | replay RUN_ID_OR_SUFFIX"""
from __future__ import annotations
import argparse, json
from . import list_envs, run_agent, RepeatBatchAgent, ShrinkAfterFailureAgent, GiveUpAfterAgent, max_calls_guard, load_fixtures, summarize_trace, get_fixture, ReplayAgent


def main(argv=None):
    ap = argparse.ArgumentParser(prog="looptraps", description="No-spend loop-trap environments (EXPLORATORY; no rate claims).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    d = sub.add_parser("demo"); d.add_argument("--env", default="M2_rotating_batch"); d.add_argument("--seed", type=int, default=1)
    sub.add_parser("fixtures")
    r = sub.add_parser("replay"); r.add_argument("run"); r.add_argument("--guard-max-calls", type=int, default=None)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for e in list_envs(): print(f"{e['name']:32s} {e['description']}")
    elif a.cmd == "demo":
        for label, agent, guard in [("repeat-batch mock agent, no guard", RepeatBatchAgent(a.env, a.seed), None),
                                    ("repeat-batch mock agent, max_calls_20 guard", RepeatBatchAgent(a.env, a.seed), max_calls_guard(20)),
                                    ("gives-up-after-2 mock agent", GiveUpAfterAgent(RepeatBatchAgent(a.env, a.seed), 2), None)]:
            res = run_agent(agent, a.env, a.seed, max_turns=12, guard=guard)
            print(f"[{label}] calls={res.n_calls} per-gen={res.calls_per_generation} distinct={res.n_distinct} ratio={res.distinct_ratio} "
                  f"machine_qualified={res.machine_qualified} ended={res.termination}")
        print("NOTE: mock agents are scripted stand-ins, not models. machine_qualified is a reporting flag only.")
    elif a.cmd == "fixtures":
        for t in load_fixtures().values(): print(json.dumps(summarize_trace(t)))
    elif a.cmd == "replay":
        t = get_fixture(a.run)
        name = t["provenance"]["scenario"].split("/")[0]
        seed = t["provenance"]["seed"]
        res = run_agent(ReplayAgent(t), name, seed, max_turns=len(t["turns"]) + 1, guard=max_calls_guard(a.guard_max_calls) if a.guard_max_calls else None)
        print(json.dumps(res.to_dict(), indent=1)); print(json.dumps(summarize_trace(t), indent=1))


if __name__ == "__main__":
    main()
