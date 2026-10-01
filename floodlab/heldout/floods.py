"""Held-out FLOOD generators F1-F9 (see docs/HELDOUT_DESIGN.md). SYNTHETIC. Structures differ from dev generators."""
from __future__ import annotations
import math
from .common import mk, rng_for, R, one_per_turn

FLOOD_STRUCTURES = ["F1_slow_drift_offset", "F2_slow_drift_timestamp", "F3_mixed_tool_lcm_cycle", "F4_noisy_result_repeat",
                    "F5_low_rate_with_heartbeat", "F6_flood_after_legit_prefix", "F7_startdone_rotating_permuted_ids",
                    "F8_oscillating_edit_same_failure", "F9_growing_batch_repeat"]


def F1_slow_drift_offset(seed):
    r = rng_for("F1", seed); n = r.randint(50, 80); path = f"logs/app_{r.randint(0, 99)}.log"
    calls = [("read_file", {"path": path, "offset": 4096 * i}, R(content="head" if i == 0 else "", eof=i > 0)) for i in range(n)]
    return mk(f"ho-F1-{seed}", FLOOD_STRUCTURES[0], "flood", seed, one_per_turn(calls), 1,
              "offset drifts by 4096 each call while every read past the first returns empty EOF")


def F2_slow_drift_timestamp(seed):
    r = rng_for("F2", seed); n = r.randint(50, 80); t0 = 1_700_000_000 + r.randint(0, 10**6)
    calls = [("search", {"query": "deploy errors", "since": t0 + 300 * i}, R(hits=[])) for i in range(n)]
    return mk(f"ho-F2-{seed}", FLOOD_STRUCTURES[1], "flood", seed, one_per_turn(calls), 1,
              "same query with a `since` cursor advancing 300s per call; always empty")


def F3_mixed_tool_lcm_cycle(seed):
    r = rng_for("F3", seed)
    sizes = r.choice([[2, 3, 2, 3], [3, 4, 2, 3], [4, 3, 4, 2], [3, 3, 4, 4]])
    tools = [("read_file", "path"), ("list_dir", "path"), ("search", "query"), ("get_doc", "id")]
    pools = [[f"{t[0]}_{r.randint(0, 999)}_{k}" for k in range(s)] for t, s in zip(tools, sizes)]
    lcm = math.lcm(*sizes); period = 4 * lcm
    gens, seen, loop_start, idx = [], set(), None, 0
    for lap in range(lcm * 3):
        g = []
        for ti, (name, key) in enumerate(tools):
            args = {key: pools[ti][lap % sizes[ti]]}
            sig = (name, tuple(args.items()))
            if loop_start is None and sig in seen: loop_start = idx
            seen.add(sig); g.append((name, args, R(name=name, args=args))); idx += 1
        gens.append(g)
    return mk(f"ho-F3-{seed}", FLOOD_STRUCTURES[2], "flood", seed, gens, loop_start,
              f"4 tools with arg pools {sizes}; joint period {period} calls; loop starts at the first exact repeat")


def F4_noisy_result_repeat(seed):
    r = rng_for("F4", seed); n = r.randint(30, 60); q = f"best practices topic {r.randint(0, 99)}"
    calls = [("web_search", {"query": q}, R(results=[r.random() for _ in range(3)], ts=i)) for i in range(n)]
    return mk(f"ho-F4-{seed}", FLOOD_STRUCTURES[3], "flood", seed, one_per_turn(calls), 1,
              "identical query repeated; each result differs (noise), no new information")


def F5_low_rate_with_heartbeat(seed):
    r = rng_for("F5", seed); n_turns = r.randint(90, 110)
    a, b, d = (f"job_{r.randint(0, 99)}_{k}" for k in "abd")
    calls = []
    for lap in range(n_turns // 4):
        calls += [("get_job_status", {"job": a}, R(s="running")), ("get_job_status", {"job": b}, R(s="running")),
                  ("log_message", {"text": f"still waiting, lap {lap}"}, R(ok=True)), ("get_job_status", {"job": d}, R(s="running"))]
    return mk(f"ho-F5-{seed}", FLOOD_STRUCTURES[4], "flood", seed, one_per_turn(calls), 4,
              "one call per turn; lap of 3 unchanged polls + a unique log message; loop starts at second lap")


def F6_flood_after_legit_prefix(seed):
    r = rng_for("F6", seed); pre = r.randint(12, 30); m = r.randint(6, 10); nloop = r.randint(90, 110)
    prefix = [("list_items", {"cursor": str(5 * i)}, R(page=i, items=list(range(5 * i, 5 * i + 5)))) for i in range(pre)]
    pool = [("read_file", {"path": f"cfg/{r.randint(0, 999)}_{k}.yaml"}, None) for k in range(m)]
    loop = [(pool[i % m][0], pool[i % m][1], R(same=pool[i % m][1])) for i in range(nloop)]
    gens = one_per_turn(prefix) + [loop[i:i + 5] for i in range(0, nloop, 5)]
    return mk(f"ho-F6-{seed}", FLOOD_STRUCTURES[5], "flood", seed, gens, pre + m,
              f"{pre} distinct paging calls then a rotation over {m} inputs; loop starts at first repeat")


def F7_startdone_rotating_permuted_ids(seed):
    r = rng_for("F7", seed); n = r.randint(18, 30); ids = [f"J{r.randint(100, 999)}_{i}" for i in range(n)]
    calls = []
    for lap in range(3):
        p = ids[:]; r.shuffle(p)
        for j in range(n):
            calls += [("start_job", {"job": p[j]}, R(started=p[j])), ("get_job_status", {"job": p[j - 1]}, R(s="running"))]
    return mk(f"ho-F7-{seed}", FLOOD_STRUCTURES[6], "flood", seed, [calls], 2 * n,
              "single generation; start/status alternation over ids re-permuted each lap; loop starts at lap 2")


def F8_oscillating_edit_same_failure(seed):
    r = rng_for("F8", seed); path = f"src/mod_{r.randint(0, 9)}.py"; cmd = {"cmd": "pytest -x"}
    fail = R(passed=False, failing=[path + "::test_x"])
    gens = []
    for i in range(r.randint(30, 45)):
        gens.append([("edit_file", {"path": path, "content": "variant_" + "AB"[i % 2]}, R(ok=True)), ("run_tests", cmd, fail)])
    return mk(f"ho-F8-{seed}", FLOOD_STRUCTURES[7], "flood", seed, gens, 5,
              "edit flips between two contents, same test fails identically; loop starts at the test that follows the recurring edit A (index 5), matching HELDOUT_DESIGN.md")


def F9_growing_batch_repeat(seed):
    r = rng_for("F9", seed); b0 = r.randint(8, 14); turns = r.randint(6, 9)
    base = [("read_file", {"path": f"data/{r.randint(0, 9999)}_{i}.csv"}, None) for i in range(b0)]
    gens = []
    for k in range(turns):
        g = [(n, a, R(same=a)) for n, a, _ in base] + [("read_file", {"path": f"extra/{seed}_{j}.csv"}, R(extra=j)) for j in range(k)]
        gens.append(g)
    return mk(f"ho-F9-{seed}", FLOOD_STRUCTURES[8], "flood", seed, gens, b0,
              "each turn re-issues the whole previous batch plus one new call; loop starts at turn 2")


GENERATORS = {s: globals()[s] for s in FLOOD_STRUCTURES}
