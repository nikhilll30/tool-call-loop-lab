"""Scripted MOCK agents (no model, no network). They are stand-ins for exercising the runner and a guard; they are NOT models and their behaviour
says nothing about any real model."""
from __future__ import annotations
from .envs import make_env


class RepeatBatchAgent:
    """Walks the environment's own scripted cycle (`mock_cycle`) `per_turn` calls per generation, forever (until the runner/guard stops it)."""
    def __init__(self, env_name: str, seed: int = 1, per_turn: int | None = None):
        sc = make_env(env_name, seed).scenario
        self.cycle = [dict(c) for c in sc.mock_cycle]
        self.per_turn = per_turn or sc.mock_per_turn
        self.pos = 0

    def __call__(self, messages, tools):
        calls = []
        for _ in range(self.per_turn):
            c = self.cycle[self.pos % len(self.cycle)]
            calls.append({"name": c["name"], "arguments": dict(c["arguments"])})
            self.pos += 1
        return {"content": "", "tool_calls": calls}


class ShrinkAfterFailureAgent:
    """Mimics the *shape* of the cancelled-batch-resend-then-shrink pattern: sends the full cycle once or twice, then single repeated calls."""
    def __init__(self, env_name: str, seed: int = 1, full_batches: int = 2):
        sc = make_env(env_name, seed).scenario
        self.cycle = [dict(c) for c in sc.mock_cycle]
        self.full_batches, self.turn = full_batches, 0

    def __call__(self, messages, tools):
        self.turn += 1
        batch = self.cycle if self.turn <= self.full_batches else self.cycle[:1]
        return {"content": "", "tool_calls": [{"name": c["name"], "arguments": dict(c["arguments"])} for c in batch]}


class GiveUpAfterAgent:
    """Wraps another agent and finishes with a final answer after `n_generations` generations (a well-behaved comparison)."""
    def __init__(self, inner, n_generations: int):
        self.inner, self.n, self.t = inner, n_generations, 0

    def __call__(self, messages, tools):
        self.t += 1
        if self.t > self.n:
            return {"content": "Giving up: the tool shows no progress.", "tool_calls": []}
        return self.inner(messages, tools)


class ReplayAgent:
    """Replays the tool calls of a stored trace (e.g. a fixture), one stored generation per agent call; finishes when the trace's generation has no calls.
    Useful to run a guard over the real (exploratory-2A) call sequences without any model."""
    def __init__(self, trace: dict):
        self.gens = [g["tool_calls"] for t in trace["turns"] for g in t["generations"]]
        self.i = 0

    def __call__(self, messages, tools):
        if self.i >= len(self.gens):
            return {"content": "", "tool_calls": []}
        calls = self.gens[self.i]
        self.i += 1
        return {"content": "", "tool_calls": [{"name": c["name"], "arguments": c["arguments"]} for c in calls]}
