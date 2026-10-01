"""Synthetic flood generators (label = flood). SYNTHETIC: shapes reproduce documented failure structure
(MiMo-Code #2482, #2509); they say nothing about real-world rates. Deterministic given seed."""
from __future__ import annotations
import json, random
from .common import build

FLOOD_SHAPES = ["rotating35_one_gen", "rotating35_multi_gen", "start_done_alternation", "abc_cycle_one_gen",
                "abc_cycle_multi_gen", "near_dup_counter", "cross_turn_identical_batches", "cancel_retry_2509"]

TOOLS = ["read_file", "list_dir", "search", "get_doc"]


def _res(name, args):
    """Unchanged external state: result is a pure function of the (call) itself."""
    return json.dumps([name, args], sort_keys=True)


def _pool(rng, n):
    """n distinct call inputs across several tools."""
    out = []
    for i in range(n):
        name = rng.choice(TOOLS)
        key = {"read_file": "path", "list_dir": "path", "search": "query", "get_doc": "id"}[name]
        out.append((name, {key: f"{name}_{i}_{rng.randint(0, 9999)}"}))
    return out


def _c(pair):
    n, a = pair
    return (n, a, _res(n, a))


def rotating35_one_gen(seed, n_calls=4120):
    rng = random.Random(seed)
    pool = _pool(rng, 35)
    return build(f"flood-rot35-1g-{seed}", shape="rotating35_one_gen", label="flood", seed=seed,
                 gens=[[_c(pool[i % 35]) for i in range(n_calls)]],
                 note="SYNTHETIC #2482 shape: one generation, 35 rotating distinct inputs, max adjacent-identical run 1")


def rotating35_multi_gen(seed, n_gens=20, per_gen=20):
    rng = random.Random(seed)
    pool = _pool(rng, 35)
    gens = [[_c(pool[(k * per_gen + i) % 35]) for i in range(per_gen)] for k in range(n_gens)]
    return build(f"flood-rot35-mg-{seed}", shape="rotating35_multi_gen", label="flood", seed=seed, gens=gens,
                 note="SYNTHETIC: 35 rotating inputs spread over generations short enough that no generation contains an exact duplicate")


def start_done_alternation(seed, n_tasks=35, n_calls=300):
    rng = random.Random(seed)
    tasks = [f"T{rng.randint(100, 999)}_{i}" for i in range(n_tasks)]
    calls = []
    for i in range(n_calls):
        t = tasks[(i // 2) % n_tasks] if i % 2 == 0 else tasks[((i // 2) - 1) % n_tasks]   # start T5 / done T4 style
        calls.append(("start_job" if i % 2 == 0 else "get_job_status", {"job": t}))
    return build(f"flood-startdone-{seed}", shape="start_done_alternation", label="flood", seed=seed,
                 gens=[[_c(p) for p in calls]], note="SYNTHETIC: start/done alternation over rotating task ids (evades last-3-identical)")


def abc_cycle_one_gen(seed, reps=20):
    rng = random.Random(seed)
    abc = _pool(rng, 3)
    return build(f"flood-abc-1g-{seed}", shape="abc_cycle_one_gen", label="flood", seed=seed,
                 gens=[[_c(abc[i % 3]) for i in range(3 * reps)]], note="SYNTHETIC: A,B,C,A,B,C... in one generation")


def abc_cycle_multi_gen(seed, gens_n=12):
    rng = random.Random(seed)
    abc = _pool(rng, 3)
    return build(f"flood-abc-mg-{seed}", shape="abc_cycle_multi_gen", label="flood", seed=seed,
                 gens=[[_c(p) for p in abc] for _ in range(gens_n)], note="SYNTHETIC: [A,B,C] batch every turn (no in-generation duplicates)")


def near_dup_counter(seed, n_calls=60):
    rng = random.Random(seed)
    path = f"logs/run_{rng.randint(0, 999)}.txt"
    gen = []
    for i in range(n_calls):
        a = {"target": path, "ts": 1_700_000_000 + i * 7}      # only a volatile timestamp changes
        gen.append(("ping", a, _res("ping", {"target": path})))
    return build(f"flood-neardup-{seed}", shape="near_dup_counter", label="flood", seed=seed, gens=[gen],
                 note="SYNTHETIC: identical call, incrementing timestamp field (exact-dup canonical JSON differs every time)")


def cross_turn_identical_batches(seed, batch=12, turns=6):
    rng = random.Random(seed)
    pool = _pool(rng, batch)
    return build(f"flood-xturn-{seed}", shape="cross_turn_identical_batches", label="flood", seed=seed,
                 gens=[[_c(p) for p in pool] for _ in range(turns)], note="SYNTHETIC: identical 12-call batch re-issued each turn")


def cancel_retry_2509(seed, batch=17, retries=10):
    rng = random.Random(seed)
    pool = _pool(rng, batch)
    # client cap of 16 cancels the batch; nothing executed -> no results changed; model retries byte-identically
    gens = [[(n, a, None) for n, a in pool] for _ in range(retries)]
    return build(f"flood-cancelretry-{seed}", shape="cancel_retry_2509", label="flood", seed=seed, gens=gens,
                 cancelled=set(range(retries)), note="SYNTHETIC #2509 shape: identical 17-call batch, cancelled by client cap, retried 10x")


GENERATORS = {n: globals()[n] for n in FLOOD_SHAPES}


def make(shape, seed):
    return GENERATORS[shape](seed)
