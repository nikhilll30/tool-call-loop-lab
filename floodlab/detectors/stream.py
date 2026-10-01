"""Incremental use of the detector library on completed calls (used by the stop-early hook and the guard).
Re-runs the pure detectors over a bounded history after each completed call: simple, O(history) per call."""
from __future__ import annotations
from dataclasses import replace
from ..canon import canonical_args, parse_args
from ..config import SuiteConfig
from ..trace import Call
from .near_dup import near_dup
from .cycle import cycle
from .distinct_ratio import distinct_ratio
from .cross_turn import cross_turn
from .base import DetectorResult

MAX_HISTORY_CALLS = 400


def to_call_gens(gens: list[list[dict]]) -> list[list[Call]]:
    """gens: [[{name, args, result_hash?}]] -> Call objects with global indices."""
    out, g = [], 0
    for ti, gen in enumerate(gens):
        cs = []
        for i, c in enumerate(gen):
            a = canonical_args(c["args"])
            cs.append(Call(g, ti, 0, i, c["name"], a, parse_args(c["args"]), c.get("result_hash"), None))
            g += 1
        out.append(cs)
    return out


def check_suite(gens: list[list[dict]], suite: SuiteConfig, use_state: bool = True) -> DetectorResult:
    """Earliest-firing new detector over the (trimmed) history. Returns flag=False result if none fires."""
    while sum(len(g) for g in gens) > MAX_HISTORY_CALLS and len(gens) > 1:
        gens = gens[1:]
    s = suite.with_state(use_state)
    cg = to_call_gens(gens)
    rs = [near_dup(cg, s.near_dup), cycle(cg, s.cycle), distinct_ratio(cg, s.distinct_ratio), cross_turn(cg, s.cross_turn)]
    fired = [r for r in rs if r.flag]
    if not fired:
        return DetectorResult("suite", False)
    r = min(fired, key=lambda r: r.first_index)
    return DetectorResult(r.detector, True, r.first_index, r.reason, r.evidence)
