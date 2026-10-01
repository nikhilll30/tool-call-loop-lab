"""Print real example traces + per-detector output (used to build PHASE1_REPORT.md). Offline."""
import json
from floodlab.gen import floods, legit
from floodlab.detectors import run_all
from floodlab.trace import flat_calls, generations
from floodlab.config import SuiteConfig

suite = SuiteConfig()


def show(t, n_head=6):
    calls = flat_calls(t)
    gens = generations(t)
    print(f"run_id={t['run_id']} label={t['label']} shape={t['shape']} split={t['split']} synthetic={t['synthetic']}")
    print(f"note={t['notes']}")
    print(f"provenance={json.dumps(t['provenance'], sort_keys=True)}")
    print(f"turns={len(t['turns'])} generations={len(gens)} total_calls={len(calls)} distinct(name,args)={len({(c.name, c.args) for c in calls})}")
    print("generation sizes:", [len(g) for g in gens][:12], "..." if len(gens) > 12 else "")
    print("first calls (gidx turn gen idx | name args | result_hash):")
    for c in calls[:n_head + 4]:
        print(f"  {c.gidx:4d} t{c.turn} g{c.gen} #{c.idx:<3d}| {c.name} {c.args} | {c.result_hash}")
    print("  ...")
    for c in calls[-3:]:
        print(f"  {c.gidx:4d} t{c.turn} g{c.gen} #{c.idx:<3d}| {c.name} {c.args} | {c.result_hash}")
    print("raw JSONL record (first turn, truncated to first 2 tool calls):")
    tt = json.loads(json.dumps(t)); 
    tt["turns"] = tt["turns"][:1]
    for g in tt["turns"][0]["generations"]: g["tool_calls"] = g["tool_calls"][:2]
    print(json.dumps(tt, sort_keys=True))


def det(t):
    print(f"{'detector':15s} {'flag':5s} {'first_idx':>9s}  reason / evidence")
    for k, r in run_all(t, suite).items():
        print(f"{k:15s} {str(r.flag):5s} {str(r.first_index):>9s}  {r.reason} {json.dumps(r.evidence, sort_keys=True)[:230]}")


for title, t in (("PATHOLOGICAL A: rotating-35 over 20 generations (evades exact-dup AND adjacent)", floods.rotating35_multi_gen(100)),
                 ("PATHOLOGICAL B: #2482 shape, ONE generation, 4120 calls, 35 rotating inputs", floods.rotating35_one_gen(100)),
                 ("LEGITIMATE: polling with changing external state (one call per turn)", legit.polling_state_changes(100)),
                 ("LEGITIMATE: paginate with changing cursor", legit.pagination_cursor(100))):
    print("=" * 110); print(title); print("=" * 110)
    show(t); print(); det(t); print()
