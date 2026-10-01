"""Canonical JSON + small helpers shared by traces and detectors."""
from __future__ import annotations
import hashlib, json
from typing import Any


def canonical_json(o: Any) -> str:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def canonical_args(args: Any) -> str:
    """Canonical JSON string for tool arguments (str or object).
    Unparseable strings (e.g. truncated JSON from a length cut) are returned verbatim."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return args
    return canonical_json(args)


def parse_args(args: Any) -> Any:
    """Parsed arguments, or None if unparseable."""
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return None
    return args


def sha(s: str, n: int = 16) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]


def drop_volatile(o: Any, volatile) -> Any:
    vs = {v.lower() for v in volatile}
    if isinstance(o, dict):
        return {k: drop_volatile(v, volatile) for k, v in o.items() if k.lower() not in vs}
    if isinstance(o, list):
        return [drop_volatile(v, volatile) for v in o]
    return o


def flatten(o: Any, prefix: str = "") -> dict:
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            out.update(flatten(v, f"{prefix}/{k}"))
        return out or {prefix: {}}
    if isinstance(o, list):
        out = {}
        for i, v in enumerate(o):
            out.update(flatten(v, f"{prefix}[{i}]"))
        return out or {prefix: []}
    return {prefix: o}
