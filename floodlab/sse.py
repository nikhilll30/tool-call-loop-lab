"""SSE parsing + tool_call delta assembly, handling BOTH delta styles:
 - whole-call-per-delta (SGLang MiMo parser): one delta carries id+name+full arguments
 - incremental fragments (OpenAI): id+name first, then argument string pieces keyed by `index`
Comment lines (': ...') are ignored; a chunk with `usage` (empty choices) is captured; [DONE] ends the stream.
Reasoning text is read from BOTH `delta.reasoning` (OpenRouter) and `delta.reasoning_content` (MiMo/DeepSeek style).
Call keys are internal sequence numbers; if a provider reuses an `index` for a new call id, a new call is started
(counted in `id_index_collisions`). Delta-shape statistics are collected for Phase 2A observations."""
from __future__ import annotations
import json
from dataclasses import dataclass, field


def parse_sse_line(line: str):
    """-> ('data', obj) | ('done', None) | None (ignored)"""
    line = line.strip()
    if not line or line.startswith(":"):
        return None
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if payload == "[DONE]":
        return ("done", None)
    return ("data", json.loads(payload))


@dataclass
class Assembler:
    content: str = ""
    reasoning: str = ""
    calls: dict = field(default_factory=dict)      # internal key -> {id, name, arguments}
    finish_reason: str | None = None
    usage: dict | None = None
    guard: dict | None = None
    extra_error: dict | None = None
    # ---- observations ----
    n_chunks: int = 0
    reasoning_fields: set = field(default_factory=set)
    has_reasoning_details: bool = False
    id_index_collisions: int = 0
    tc_delta_counts: dict = field(default_factory=dict)
    tc_first_has_args: dict = field(default_factory=dict)
    tc_provider_indices: list = field(default_factory=list)

    def __post_init__(self):
        self._done_set: set = set()
        self._map: dict = {}          # provider index -> internal key

    def feed(self, chunk: dict) -> list[int]:
        """Feed one parsed chunk. Returns keys of tool calls that became *complete* because of this chunk
        (a call is complete when a later call starts, or when finish_reason arrives)."""
        self.n_chunks += 1
        done: list[int] = []
        if chunk.get("usage"):
            self.usage = chunk["usage"]
        if chunk.get("floodlab_guard"):
            self.guard = chunk["floodlab_guard"]
        if chunk.get("error"):
            self.extra_error = chunk["error"]
        for ch in chunk.get("choices", []):
            d = ch.get("delta", {}) or {}
            if d.get("content"):
                self.content += d["content"]
            for fld in ("reasoning", "reasoning_content"):
                if d.get(fld):
                    self.reasoning += d[fld]
                    self.reasoning_fields.add(fld)
                    break
            if d.get("reasoning_details"):
                self.has_reasoning_details = True
            for tc in d.get("tool_calls") or []:
                pi = tc.get("index", 0)
                self.tc_provider_indices.append(pi)
                key = self._map.get(pi)
                new_id = tc.get("id")
                if key is not None and new_id and self.calls[key]["id"] and new_id != self.calls[key]["id"]:
                    self.id_index_collisions += 1
                    key = None
                if key is None:
                    prev = [k for k in self.calls if k not in self._done_set]
                    done.extend(prev)
                    self._done_set.update(prev)
                    key = len(self.calls)
                    self._map[pi] = key
                    self.calls[key] = {"id": new_id, "name": "", "arguments": ""}
                    self.tc_delta_counts[key] = 0
                    self.tc_first_has_args[key] = bool((tc.get("function") or {}).get("arguments"))
                self.tc_delta_counts[key] += 1
                f = tc.get("function", {}) or {}
                if new_id: self.calls[key]["id"] = new_id
                if f.get("name") and not self.calls[key]["name"]: self.calls[key]["name"] = f["name"]
                if f.get("arguments"): self.calls[key]["arguments"] += f["arguments"]
            if ch.get("finish_reason"):
                self.finish_reason = ch["finish_reason"]
                rest = [k for k in self.calls if k not in self._done_set]
                self._done_set.update(rest)
                done.extend(rest)
        return done

    def ordered_calls(self) -> list[dict]:
        return [self.calls[k] for k in sorted(self.calls)]

    def shape_summary(self) -> dict:
        n = len(self.calls)
        multi = sum(1 for c in self.tc_delta_counts.values() if c > 1)
        first_args = sum(1 for v in self.tc_first_has_args.values() if v)
        style = "none" if n == 0 else "whole" if multi == 0 else "incremental" if multi == n else "mixed"
        return {"calls": n, "delta_style": style, "calls_with_multiple_deltas": multi,
                "max_deltas_per_call": max(self.tc_delta_counts.values(), default=0),
                "first_delta_carries_arguments": first_args, "chunks": self.n_chunks,
                "reasoning_fields_seen": sorted(self.reasoning_fields), "reasoning_details_seen": self.has_reasoning_details,
                "id_index_collisions": self.id_index_collisions,
                "provider_indices_distinct": len(set(self.tc_provider_indices))}
