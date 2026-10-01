"""Trace records: builders, JSONL IO, and the flattened-call view used by detectors. See docs/TRACE_SCHEMA.md."""
from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Iterable
from .canon import canonical_args, parse_args, sha, canonical_json

SCHEMA_VERSION = "floodlab.trace/1"
SIM_T0 = 1_700_000_000.0   # simulated clock origin for synthetic traces


@dataclass(frozen=True)
class Call:
    gidx: int          # global 0-based index over the whole run, in emission order
    turn: int
    gen: int           # generation index within the turn
    idx: int           # index within the generation
    name: str
    args: str          # canonical JSON string
    args_obj: Any      # parsed (None if unparseable)
    result_hash: str | None
    ts: float | None


def make_call(index: int, name: str, args: Any, ts: float | None = None, result: str | None = None) -> dict:
    d = {"index": index, "name": name, "arguments": canonical_args(args), "timestamp": ts}
    if result is not None:
        d["result_hash"] = sha(result)
    return d


def make_generation(gen: int, calls: list[dict], t_start: float, t_end: float, finish_reason: str = "tool_calls",
                    cancelled: bool = False, usage: dict | None = None, content: str = "", reasoning_content: str = "") -> dict:
    return {"gen": gen, "t_start": t_start, "t_end": t_end, "finish_reason": finish_reason, "cancelled": cancelled,
            "content": content, "reasoning_content": reasoning_content, "usage": usage or {}, "tool_calls": calls}


def make_provenance(model="synthetic", endpoint="none", scenario="", seed=0, detector_config=None, guard_config="off",
                    prompt_version="n/a", tool_schema_version="n/a") -> dict:
    return {"model": model, "endpoint": endpoint, "scenario": scenario, "seed": seed,
            "detector_config": detector_config or {"id": None, "hash": None},
            "guard_config": guard_config, "prompt_version": prompt_version, "tool_schema_version": tool_schema_version}


def make_trace(run_id: str, provenance: dict, turns: list[dict], *, label="unknown", shape="", synthetic=True, split="none",
               latency_s=0.0, cost_usd=0.0, termination_reason="completed", notes="") -> dict:
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id, "synthetic": synthetic, "label": label, "shape": shape,
            "split": split, "provenance": provenance, "turns": turns, "latency_s": latency_s, "cost_usd": cost_usd,
            "termination_reason": termination_reason, "notes": notes}


REQUIRED_PROVENANCE = ["model", "endpoint", "scenario", "seed", "detector_config", "guard_config", "prompt_version", "tool_schema_version"]


def validate(trace: dict) -> list[str]:
    errs = []
    if trace.get("schema_version") != SCHEMA_VERSION: errs.append("schema_version")
    for k in ("run_id", "provenance", "turns", "latency_s", "cost_usd", "termination_reason", "label"):
        if k not in trace: errs.append("missing " + k)
    for k in REQUIRED_PROVENANCE:
        if k not in trace.get("provenance", {}): errs.append("provenance." + k)
    for t in trace.get("turns", []):
        for g in t.get("generations", []):
            for c in g.get("tool_calls", []):
                for k in ("index", "name", "arguments", "timestamp"):
                    if k not in c: errs.append(f"call.{k}")
    return errs


def generations(trace: dict) -> list[list[Call]]:
    """List of generations (each a list of Call), in emission order, with global indices."""
    out, g = [], 0
    for t in trace["turns"]:
        for gen in t["generations"]:
            calls = []
            for c in gen["tool_calls"]:
                a = c["arguments"]
                calls.append(Call(g, t["turn"], gen["gen"], c["index"], c["name"], canonical_args(a), parse_args(a),
                                  c.get("result_hash"), c.get("timestamp")))
                g += 1
            out.append(calls)
    return out


def flat_calls(trace: dict) -> list[Call]:
    return [c for g in generations(trace) for c in g]


def write_jsonl(path, traces: Iterable[dict]) -> int:
    n = 0
    with open(path, "w") as f:
        for t in traces:
            f.write(canonical_json(t) + "\n"); n += 1
    return n


def read_jsonl(path) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]
