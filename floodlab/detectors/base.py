"""Shared detector plumbing. Detectors are pure functions: (trace_or_generations, config) -> DetectorResult."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from ..canon import canonical_json, drop_volatile
from ..trace import Call, generations


@dataclass
class DetectorResult:
    detector: str
    flag: bool
    first_index: int | None = None     # global 0-based call index at which the detector first fires
    reason: str = "OK"                 # reason code
    evidence: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def as_gens(x) -> list[list[Call]]:
    return generations(x) if isinstance(x, dict) else x


def flat(gens) -> list[Call]:
    return [c for g in gens for c in g]


def raw_sig(c: Call) -> str:
    return c.name + "|" + c.args


def norm_sig(c: Call, volatile) -> str:
    """Signature ignoring volatile fields."""
    if c.args_obj is None:
        return c.name + "|" + c.args
    return c.name + "|" + canonical_json(drop_volatile(c.args_obj, volatile))


def state_changed(calls: list[Call], sigs: list[str], threshold: float) -> tuple[bool, float]:
    """Did external state change between repeated calls? Score per repeated signature =
    (distinct result hashes - 1) / (occurrences - 1); mean over repeated signatures whose results are all known.
    Returns (changed, score). No result hashes -> (False, 0.0): cannot suppress."""
    by = defaultdict(list)
    for c, s in zip(calls, sigs):
        by[s].append(c.result_hash)
    scores = []
    for hs in by.values():
        if len(hs) < 2 or any(h is None for h in hs):
            continue
        scores.append((len(set(hs)) - 1) / (len(hs) - 1))
    if not scores:
        return False, 0.0
    m = sum(scores) / len(scores)
    return m >= threshold, round(m, 3)
