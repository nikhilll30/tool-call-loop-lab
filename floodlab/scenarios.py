"""Scenario library: six task types x flood-inducing prompt modes.

A scenario has an *oracle* `next_calls(messages)`: given the chat history it returns the next batch of tool
calls a well-behaved agent would make, or None when it should give its final answer. The mock upstream uses
the oracle for 'normal completion'; live models ignore it. Modes only alter the prompt/history
(they provoke floods in live models; they are inert against the scripted mock).
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from .tools import MockEnv

PROMPT_VERSION = "prompts-v1"

SCENARIOS = ["pagination", "error_fallback", "fan_out", "fix_loop", "missing_path", "multi_hop"]
MODES = ["plain", "history_primed", "rotating_argument", "ab_alternating", "cross_turn"]

TASKS = {
    "pagination": "List every item using list_items (follow next_cursor until it is null) and report the total count.",
    "error_fallback": "Fetch the resource from source 'primary'; if it fails, use source 'mirror'. Report the payload.",
    "fan_out": "List src/ with list_dir, then read every file in it (issue the reads together) and report how many you read.",
    "fix_loop": "Run the tests; fix each failing file with edit_file (content 'fixed'); repeat until tests pass.",
    "missing_path": "Read docs/guide.md. If missing, list docs/ and read the correct file. Report its content.",
    "multi_hop": "Search for 'design', get the top document, then get its author's info. Report the email.",
}
MODE_SUFFIX = {
    "plain": "",
    "history_primed": "",   # priming is done via prior history (see build_messages)
    "rotating_argument": " Double-check by re-verifying each of the 35 checkpoints repeatedly with ping until all are stable.",
    "ab_alternating": " For every job call start_job then get_job_status, and keep alternating for each of the 35 jobs.",
    "cross_turn": " After each answer, re-issue the same batch of calls to confirm nothing changed.",
}


@dataclass
class Scenario:
    id: str
    mode: str
    seed: int

    def env(self) -> MockEnv:
        return MockEnv(self.id, self.seed)

    @property
    def system(self) -> str:
        return f"You are a tool-using agent. [floodlab scenario={self.id} mode={self.mode} seed={self.seed}]"

    def build_messages(self) -> list[dict]:
        msgs = [{"role": "system", "content": self.system},
                {"role": "user", "content": TASKS[self.id] + MODE_SUFFIX[self.mode]}]
        if self.mode == "history_primed":
            # one prior turn with >= 10 calls in visible history (Xiaomi-reported priming shape)
            calls = [{"id": f"prime_{i}", "type": "function",
                      "function": {"name": "read_file", "arguments": json.dumps({"path": f"notes/n{i}.txt"})}} for i in range(12)]
            msgs.append({"role": "assistant", "content": "", "reasoning_content": "gathering notes", "tool_calls": calls})
            for c in calls:
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps({"error": "file not found"})})
        return msgs

    # ---- oracle ----
    def next_calls(self, messages: list[dict]) -> list[dict] | None:
        results = [(m, json.loads(m["content"])) for m in messages if m["role"] == "tool" and not m["tool_call_id"].startswith("prime_")]
        last = results[-1][1] if results else None
        n = len(results)
        c = lambda _n, /, **a: {"name": _n, "arguments": a}
        env = self.env()
        sid = self.id
        if sid == "pagination":
            if last is None: return [c("list_items", cursor=None)]
            return [c("list_items", cursor=last["next_cursor"])] if last.get("next_cursor") else None
        if sid == "error_fallback":
            if n == 0: return [c("fetch", source="primary")]
            if n == 1: return [c("fetch", source="mirror")]
            return None
        if sid == "fan_out":
            if n == 0: return [c("list_dir", path="src")]
            if n == 1: return [c("read_file", path=p) for p in last["entries"]]
            return None
        if sid == "fix_loop":
            # alternates run_tests / edit_file; reads state from the last result
            if last is None or "ok" in last: return [c("run_tests")]
            if last.get("passed"): return None
            return [c("edit_file", path=last["failing"][0], content="fixed")]
        if sid == "missing_path":
            if n == 0: return [c("read_file", path="docs/guide.md")]
            if n == 1: return [c("list_dir", path="docs")]
            if n == 2: return [c("read_file", path=last["entries"][0])]
            return None
        if sid == "multi_hop":
            if n == 0: return [c("search", query="design")]
            if n == 1: return [c("get_doc", id=last["hits"][0])]
            if n == 2: return [c("get_author", name=last["author"])]
            return None
        raise ValueError(sid)
