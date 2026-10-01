"""Assemble / verify the held-out dataset. Contains NO detector imports."""
from __future__ import annotations
import hashlib
from pathlib import Path
from . import floods, legit
from .common import HELDOUT_FLOOD_SEEDS, HELDOUT_LEGIT_SEEDS
from .handwritten import heldout_handwritten
from ..trace import write_jsonl

PATH = Path(__file__).resolve().parents[2] / "data" / "heldout" / "heldout_v1.jsonl"


def build_all() -> list[dict]:
    out = []
    for s in floods.FLOOD_STRUCTURES:
        out += [floods.GENERATORS[s](seed) for seed in HELDOUT_FLOOD_SEEDS]
    for s in legit.LEGIT_STRUCTURES:
        out += [legit.GENERATORS[s](seed) for seed in HELDOUT_LEGIT_SEEDS]
    out += heldout_handwritten()
    return out


def write(path: Path = PATH) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(path, build_all())
    return hashlib.sha256(path.read_bytes()).hexdigest()
