"""Held-out LEGITIMATE generators L1-L11 (see docs/HELDOUT_DESIGN.md). SYNTHETIC; hard negatives by design."""
from __future__ import annotations
from .common import mk, rng_for, R, one_per_turn

LEGIT_STRUCTURES = ["L1_poll_long_plateau", "L2_retries_backoff_refresh", "L3_paginated_cursor_quirks",
                    "L4_batch_fanout_repeated_subcalls", "L5_idempotent_reread_after_write", "L6_test_fix_rerun",
                    "L7_noisy_results_unchanged_state", "L8_large_fanout_distinct", "L9_tree_crawl",
                    "L10_alternating_two_tool_distinct", "L11_batch_polling_multi_job"]
WHY = "legitimate by construction"


def L1_poll_long_plateau(seed):
    r = rng_for("L1", seed); L = r.randint(9, 40); job = {"job": f"build_{r.randint(0, 99)}"}
    res = [R(status="running", progress=p) for p in (0, 10)] + [R(status="running", progress=20)] * L + \
          [R(status="running", progress=p) for p in (40, 70, 90)] + [R(status="done", progress=100)]
    return mk(f"ho-L1-{seed}", LEGIT_STRUCTURES[0], "legitimate", seed, one_per_turn([("get_job_status", job, x) for x in res]), None,
              f"identical poll with {L}-poll unchanged plateau then progress; {WHY}")


def L2_retries_backoff_refresh(seed):
    r = rng_for("L2", seed); n = r.randint(6, 10); calls = []
    for a in range(n):
        ok = a == n - 1
        calls.append(("fetch", {"source": "api.example", "attempt": a, "wait_s": min(60, 2 ** a), "token": f"tok_{r.randint(0, 10**6)}"},
                      R(ok=True, data="payload") if ok else R(err=503)))
    return mk(f"ho-L2-{seed}", LEGIT_STRUCTURES[1], "legitimate", seed, one_per_turn(calls), None, "exponential backoff with refreshed token; identical 503s")


def L3_paginated_cursor_quirks(seed):
    r = rng_for("L3", seed); n = r.randint(25, 40); calls = []; cur = None
    for i in range(n):
        nxt = f"{r.getrandbits(48):012x}"
        if i == 3:      # empty page that still has a next cursor
            calls.append(("list_items", {"cursor": cur}, R(items=[], next=nxt)))
        elif i == 6:    # rate limited, same cursor retried
            calls.append(("list_items", {"cursor": cur}, R(err=429)))
            calls.append(("list_items", {"cursor": cur}, R(items=[f"i{i}"], next=nxt)))
        elif i == n // 2:   # server invalidates the cursor; crawl restarts from null and data changed
            calls.append(("list_items", {"cursor": None}, R(items=["restart", r.random()], next=nxt)))
        else:
            calls.append(("list_items", {"cursor": cur}, R(items=[f"i{i}", r.random()], next=nxt)))
        cur = nxt
    calls.insert(0, ("list_items", {"cursor": None}, R(items=["first"], next=calls[0][1]["cursor"] or "x")))
    return mk(f"ho-L3-{seed}", LEGIT_STRUCTURES[2], "legitimate", seed, one_per_turn(calls), None, "opaque cursors, empty page, 429 retry, restart with changed data")


def L4_batch_fanout_repeated_subcalls(seed):
    r = rng_for("L4", seed); reps = r.randint(5, 8); names = [f"metric_{k}" for k in range(6)]; g = []
    for rep in range(reps):
        for nm in names:
            g.append(("query_metric", {"name": nm}, R(v=r.random(), rep=rep)))
    return mk(f"ho-L4-{seed}", LEGIT_STRUCTURES[3], "legitimate", seed, [g], None, "6 metrics sampled repeatedly in one generation; every result differs")


def L5_idempotent_reread_after_write(seed):
    r = rng_for("L5", seed); files = [f"src/f{k}.py" for k in range(r.randint(2, 3))]; gens = []
    for i in range(r.randint(6, 14)):
        f = files[i % len(files)]; body = R(content=f"v{i}")
        gens.append([("edit_file", {"path": f, "content": f"v{i}"}, R(ok=True))])
        gens.append([("read_file", {"path": f}, body), ("read_file", {"path": f}, body)])
    return mk(f"ho-L5-{seed}", LEGIT_STRUCTURES[4], "legitimate", seed, gens, None, "write then verification double-read; content changes across rounds")


def L6_test_fix_rerun(seed):
    r = rng_for("L6", seed); rounds = r.randint(8, 16); failing = r.randint(6, 12); gens = []
    for i in range(rounds):
        if r.random() < 0.5 and failing > 1: failing -= 1     # stagnates about half the time
        f = f"src/m{i % 4}.py"
        gens.append([("run_tests", {"cmd": "pytest -q"}, R(failing=failing)), ("read_file", {"path": f}, R(c=f"body{i}")),
                     ("edit_file", {"path": f, "content": f"fix{i}"}, R(ok=True))])
    return mk(f"ho-L6-{seed}", LEGIT_STRUCTURES[5], "legitimate", seed, gens, None, "same test command each round after real edits; failing count non-increasing")


def L7_noisy_results_unchanged_state(seed):
    r = rng_for("L7", seed); n = r.randint(8, 25); calls = []
    for i in range(n):
        st = "healthy" if i == n - 1 else "starting"
        calls.append(("get_status", {"service": "api"}, R(state=st, server_time=1.7e9 + i * 3.1 + r.random(), request_id=f"{r.getrandbits(40):x}", load=r.random())))
    return mk(f"ho-L7-{seed}", LEGIT_STRUCTURES[6], "legitimate", seed, one_per_turn(calls), None,
              "unchanged state ('starting') polled until healthy; every result carries fresh timestamp/request id/load noise")


def L8_large_fanout_distinct(seed):
    r = rng_for("L8", seed); n = r.randint(24, 100)
    g = [("read_file", {"path": f"data/part_{i:03d}.csv"}, R(rows=r.randint(1, 999))) for i in range(n)]
    return mk(f"ho-L8-{seed}", LEGIT_STRUCTURES[7], "legitimate", seed, [g], None, f"{n} distinct reads in one generation")


def L9_tree_crawl(seed):
    r = rng_for("L9", seed); gens = [[("list_dir", {"path": "/"}, R(entries=["a", "b", "c"], v=0))]]; k = 0
    for d in range(r.randint(4, 7)):
        g = []
        for _ in range(r.randint(2, 12)):
            k += 1
            g.append(("list_dir", {"path": f"/d{d}/n{k}"}, R(e=k)) if r.random() < 0.5 else ("read_file", {"path": f"/d{d}/f{k}.txt"}, R(c=k)))
        gens.append(g)
    gens.append([("edit_file", {"path": "/out.txt", "content": "report"}, R(ok=True))])
    gens.append([("list_dir", {"path": "/"}, R(entries=["a", "b", "c", "out.txt"], v=1))])
    return mk(f"ho-L9-{seed}", LEGIT_STRUCTURES[8], "legitimate", seed, gens, None, "BFS crawl; root re-listed after a write (state changed)")


def L10_alternating_two_tool_distinct(seed):
    r = rng_for("L10", seed); n = r.randint(20, 45); calls = []
    for i in range(n):
        calls += [("search", {"query": f"topic {i} {r.randint(0, 999)}"}, R(hit=f"d{i}")), ("get_doc", {"id": f"d{i}"}, R(text=f"doc {i}"))]
    return mk(f"ho-L10-{seed}", LEGIT_STRUCTURES[9], "legitimate", seed, one_per_turn(calls), None, "search/get_doc alternation with distinct arguments")


def L11_batch_polling_multi_job(seed):
    r = rng_for("L11", seed); k = r.randint(4, 6); fin = [r.randint(2, 8) for _ in range(k)]; gens = []
    for t in range(max(fin) + 2):
        gens.append([("get_job_status", {"job": f"job_{j}"}, R(status="done" if t >= fin[j] else "running")) for j in range(k)])
    return mk(f"ho-L11-{seed}", LEGIT_STRUCTURES[10], "legitimate", seed, gens, None,
              "same status batch every turn until all jobs finish; unfinished jobs return an identical 'running' result")


GENERATORS = {s: globals()[s] for s in LEGIT_STRUCTURES}
