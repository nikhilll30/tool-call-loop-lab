"""Assemble the full synthetic dataset deterministically."""
from __future__ import annotations
from .common import DEV_SEEDS, TEST_SEEDS
from . import floods, legit
from .handwritten import handwritten_legit


def all_traces() -> list[dict]:
    out = []
    for seed in DEV_SEEDS + TEST_SEEDS:
        for s in floods.FLOOD_SHAPES:
            out.append(floods.make(s, seed))
        for f in legit.LEGIT_FAMILIES:
            out.append(legit.make(f, seed))
    out.extend(handwritten_legit())
    return out
