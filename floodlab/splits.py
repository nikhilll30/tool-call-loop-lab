"""Split guards. Exploratory data (Phase 2A) must never be used as untouched confirmatory data for Guard v2."""
from __future__ import annotations

EXPLORATORY_SPLITS = ("exploratory-2A",)
EXPLORATORY_NOTE = "EXPLORATORY: must NOT be used as untouched confirmatory data for Guard v2"


def is_exploratory(t: dict) -> bool:
    return t.get("split") in EXPLORATORY_SPLITS or bool(t.get("exploratory")) or str(t.get("split", "")).startswith("exploratory")


def refuse_exploratory(traces, where: str) -> None:
    bad = [t.get("run_id") for t in traces if is_exploratory(t)]
    if bad:
        raise ValueError(f"{where}: refusing exploratory-2A traces as confirmatory data ({len(bad)} found, e.g. {bad[:2]}). "
                         "Exploratory data was seen by its authors and cannot serve as untouched confirmatory data for Guard v2.")
