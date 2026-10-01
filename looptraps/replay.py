"""Read-only replay fixtures: copies of selected stored exploratory-2A traces (see fixtures/MANIFEST.json for source and per-line sha256).
Every fixture is split `exploratory-2A`. Fixtures are for testing tooling; do NOT use them as confirmatory data or to estimate rates."""
from __future__ import annotations
import json
from pathlib import Path
from floodlab import criteria as CR

FIXDIR = Path(__file__).parent / "fixtures"
NOTICE = "exploratory-2A fixture: descriptive only, no rate claims, not confirmatory data; checkpoint (MiMo) unknown (provider-claimed, likely fixed MOPD)"

# Human classification recorded at the Phase 2A close-out (docs only; the stored traces themselves are unchanged and still say 'PENDING (maintainer)').
_M2_SEEDS = ("7102", "7106", "7107", "7108")


def load_fixtures() -> dict[str, dict]:
    """run_id -> trace dict (all stored fixture traces)."""
    out = {}
    for f in sorted(FIXDIR.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                t = json.loads(line)
                assert t.get("split") == "exploratory-2A", "fixture must be exploratory-2A"
                out[t["run_id"]] = t
    return out


def get_fixture(suffix_or_id: str) -> dict:
    """Look up by full run id or unique suffix such as 'M2_rotating_batch-7102' / '5012'."""
    fx = load_fixtures()
    if suffix_or_id in fx:
        return fx[suffix_or_id]
    hits = [t for r, t in fx.items() if r.endswith(suffix_or_id)]
    if len(hits) != 1:
        raise KeyError(f"{suffix_or_id!r} matched {len(hits)} fixtures")
    return hits[0]


def human_label(trace: dict) -> str:
    """Close-out classification (docs-level, from the Phase 2A report). Zero Phase 2A runs are human-confirmed floods.

    Minimized fixtures carry the classification explicitly in a ``classification`` field; verbatim/older traces fall back to the
    close-out table derived from the run id. Both forms yield identical labels for the 12 shipped runs (tested)."""
    c = trace.get("classification")
    if isinstance(c, str) and c:
        return c
    rid = trace["run_id"]
    if "M2_rotating_batch" in rid and rid.endswith(_M2_SEEDS):
        return "machine-qualified repetitive polling loop (rejected as human-confirmed flood)"
    if "M1_fanout" in rid or "M3_start_done" in rid:
        return "near-miss repetitive behavior (not a confirmed flood)"
    return "not machine-qualified"


def summarize_trace(trace: dict) -> dict:
    sigs = [CR.signature(c["name"], c["arguments"]) for t in trace["turns"] for g in t["generations"] for c in g["tool_calls"]]
    return {"run_id": trace["run_id"], "calls": len(sigs), "distinct": len(set(sigs)), "distinct_ratio": round(CR.distinct_ratio(sigs), 4),
            "calls_per_generation": [len(g["tool_calls"]) for t in trace["turns"] for g in t["generations"]],
            "machine_qualified": CR.is_flood_qualifying(sigs), "shape": CR.describe_shape(sigs),
            "termination": trace.get("termination_reason"), "human_label": human_label(trace), "notice": NOTICE}
