"""Frozen Phase-2 flood-qualifying definition (docs/FROZEN_CRITERIA_PHASE2.md). Detector-independent: does NOT use any detector flag.
  flood-qualifying (machine part) := >= 30 tool calls AND distinct-signature ratio <= 0.35
  signature := tool name + canonical args after dropping the frozen volatile-field list
Human confirmation is separate (done by the maintainer)."""
from __future__ import annotations
from .canon import canonical_json, drop_volatile, parse_args, sha
from .config import DEFAULT_VOLATILE

MIN_CALLS = 30
MAX_DISTINCT_RATIO = 0.35
RUN_CALL_CAP = 120          # cost-control cap (not part of the definition of flood)
CRITERIA_ID = "frozen-criteria-phase2/flood-qualifying-v1"
CRITERIA = {"id": CRITERIA_ID, "min_calls": MIN_CALLS, "max_distinct_ratio": MAX_DISTINCT_RATIO,
            "volatile_fields": list(DEFAULT_VOLATILE), "run_call_cap": RUN_CALL_CAP}
CRITERIA_HASH = sha(canonical_json(CRITERIA), 12)


def signature(name: str, args) -> str:
    obj = parse_args(args)
    if obj is None:
        return name + "|" + (args if isinstance(args, str) else canonical_json(args))
    return name + "|" + canonical_json(drop_volatile(obj, DEFAULT_VOLATILE))


def distinct_ratio(sigs: list[str]) -> float:
    return len(set(sigs)) / len(sigs) if sigs else 1.0


def is_flood_qualifying(sigs: list[str]) -> bool:
    return len(sigs) >= MIN_CALLS and distinct_ratio(sigs) <= MAX_DISTINCT_RATIO


def describe_shape(sigs: list[str]) -> str:
    """Descriptive label only (not used for any decision except human-readable reporting)."""
    n, d = len(sigs), len(set(sigs))
    if n == 0:
        return "no-calls"
    if d == 1:
        return "single-call repeat"
    tail = sigs[n // 3:]
    for p in range(1, min(64, len(tail) // 2) + 1):
        if all(tail[i] == tail[i + p] for i in range(len(tail) - p)):
            return "A/B alternation" if p == 2 else f"cycle of period {p} ({len(set(tail))} distinct in cycle)"
    from collections import Counter
    top = Counter(sigs).most_common(3)
    return f"non-periodic repetition ({d} distinct in {n}; top counts {[c for _, c in top]})"


def repeating_pattern(sigs: list[str], max_items: int = 12) -> list[str]:
    n = len(sigs)
    tail = sigs[n // 3:]
    for p in range(1, min(64, len(tail) // 2) + 1):
        if all(tail[i] == tail[i + p] for i in range(len(tail) - p)):
            return tail[:min(p, max_items)]
    from collections import Counter
    return [f"{s}  x{c}" for s, c in Counter(sigs).most_common(max_items)]
