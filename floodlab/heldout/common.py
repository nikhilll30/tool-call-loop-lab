"""HELD-OUT data helpers. Nothing in this package may import detectors (checked by tests/test_heldout_isolation.py)."""
from __future__ import annotations
import json, random
from ..gen.common import build

HELDOUT_FLOOD_SEEDS = list(range(1000, 1008))
HELDOUT_LEGIT_SEEDS = list(range(1000, 1010))


def rng_for(structure: str, seed: int) -> random.Random:
    return random.Random(f"{structure}:{seed}")


def R(**kw) -> str:
    return json.dumps(kw, sort_keys=True)


def one_per_turn(calls):
    return [[c] for c in calls]


def mk(run_id, structure, label, seed, gens, loop_start, rationale, note=""):
    t = build(run_id, shape=structure, label=label, seed=seed, gens=gens, note="SYNTHETIC HELD-OUT v1. " + note)
    t["split"] = "heldout"
    t["ground_truth"] = {"label": label, "loop_start_index": loop_start, "structure": structure, "rationale": rationale}
    assert (label == "flood") == (loop_start is not None)
    return t
