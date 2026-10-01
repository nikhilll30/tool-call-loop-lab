"""Legitimate negative-control generators (label = legitimate): valid work that can *look* repetitive.
SYNTHETIC. Results reflect simulated external state, so state-aware detection has something to see."""
from __future__ import annotations
import json, random
from .common import build

LEGIT_FAMILIES = ["pagination_cursor", "retries_changing_args", "parallel_fanout", "polling_state_changes",
                  "alternating_read_write", "identical_calls_state_changed", "batched_polling_state_changes"]


def pagination_cursor(seed):
    rng = random.Random(seed)
    n = rng.randint(120, 200)
    gens = []
    for c in range(0, n, 5):
        res = json.dumps({"items": list(range(c, c + 5)), "cursor": c})
        gens.append([("list_items", {"cursor": str(c)}, res)])
    return build(f"legit-pagination-{seed}", shape="pagination_cursor", label="legitimate", seed=seed, gens=gens,
                 note="SYNTHETIC: one call per turn, changing cursor")


def retries_changing_args(seed):
    rng = random.Random(seed)
    gens = []
    for a in range(rng.randint(6, 10)):
        ok = a >= 5
        gens.append([("fetch", {"source": f"mirror-{a}", "timeout_s": 5 * (a + 1)}, json.dumps({"ok": ok, "a": a}))])
    return build(f"legit-retries-{seed}", shape="retries_changing_args", label="legitimate", seed=seed, gens=gens,
                 note="SYNTHETIC: retries with changing source/timeout")


def parallel_fanout(seed):
    rng = random.Random(seed)
    n = rng.randint(20, 40)
    g = [("read_file", {"path": f"src/mod_{i:02d}.py"}, json.dumps({"content": f"m{i}-{rng.randint(0, 99999)}"})) for i in range(n)]
    return build(f"legit-fanout-{seed}", shape="parallel_fanout", label="legitimate", seed=seed, gens=[g],
                 note="SYNTHETIC: 20-40 distinct-arg calls in one generation")


def polling_state_changes(seed):
    rng = random.Random(seed)
    k = rng.randint(8, 16)
    gens = [[("get_job_status", {"job": "build"}, json.dumps({"progress": p * 100 // k, "status": "running" if p < k else "done"}))]
            for p in range(1, k + 1)]
    return build(f"legit-polling-{seed}", shape="polling_state_changes", label="legitimate", seed=seed, gens=gens,
                 note="SYNTHETIC: identical poll each turn; external state (progress) changes")


def alternating_read_write(seed):
    rng = random.Random(seed)
    rounds = rng.randint(8, 14)
    files = [f"src/mod_{i:02d}.py" for i in range(rng.randint(2, 4))]
    gens = []
    for r in range(rounds):
        f = files[r % len(files)]
        gens.append([("run_tests", {}, json.dumps({"failing": rounds - r}))])
        gens.append([("edit_file", {"path": f, "content": f"fixed v{r}"}, json.dumps({"ok": True}))])
    return build(f"legit-altrw-{seed}", shape="alternating_read_write", label="legitimate", seed=seed, gens=gens,
                 note="SYNTHETIC: run_tests/edit_file alternation (fix-loop) with progressing failures")


def identical_calls_state_changed(seed):
    rng = random.Random(seed)
    path = "config/app.yaml"
    gens = []
    for r in range(rng.randint(8, 12)):
        gens.append([("read_file", {"path": path}, json.dumps({"content": f"v{r}"})),
                     ("edit_file", {"path": path, "content": f"v{r + 1}"}, json.dumps({"ok": True}))])
    return build(f"legit-identread-{seed}", shape="identical_calls_state_changed", label="legitimate", seed=seed, gens=gens,
                 note="SYNTHETIC: identical read_file repeated; content legitimately changed between reads")


def batched_polling_state_changes(seed):
    rng = random.Random(seed)
    k = rng.randint(10, 16)
    g = [("get_job_status", {"job": "deploy"}, json.dumps({"progress": p * 100 // k})) for p in range(1, k + 1)]
    return build(f"legit-batchpoll-{seed}", shape="batched_polling_state_changes", label="legitimate", seed=seed, gens=[g],
                 note="SYNTHETIC: repeated identical poll calls in ONE generation with changing results (sampled state)")


GENERATORS = {n: globals()[n] for n in LEGIT_FAMILIES}


def make(family, seed):
    return GENERATORS[family](seed)
