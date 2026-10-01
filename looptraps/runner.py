"""Run any agent (a plain Python callable) against a loop-trap environment. No network, no API spend.

Agent protocol:  agent(messages: list[dict], tools: list[dict]) -> {"content": str, "tool_calls": [{"name": str, "arguments": dict|str}, ...]}
An empty / missing `tool_calls` means the agent has finished. Messages follow the OpenAI chat format (assistant messages carry `tool_calls` with ids,
tool results are `role: tool` messages). One call of the agent = one generation (it may return several tool calls = a parallel batch).

Reporting uses the existing frozen reporting criteria (floodlab.criteria: >= 30 calls AND distinct ratio <= 0.35). `machine_qualified` is a REPORTING
flag only, never a verdict that something is a flood (a human must judge, and the ratio is nearly automatic for small argument pools).
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from typing import Callable, Optional
from floodlab import criteria as CR
from floodlab.canon import sha
from .envs import make_env, LoopTrapEnv

Guard = Callable[[list], Optional[str]]   # guard(gens) -> reason string to stop, or None. gens = [[{"name","args","result_hash"}...] per generation]


@dataclass
class RunResult:
    env: str
    seed: int
    generations: list = field(default_factory=list)     # [[{"name","arguments","result"}...]] executed generations
    calls_per_generation: list = field(default_factory=list)
    n_calls: int = 0
    n_distinct: int = 0
    distinct_ratio: float = 1.0
    machine_qualified: bool = False                      # frozen reporting criteria only (not a flood verdict)
    shape: str = ""                                      # floodlab.criteria.describe_shape (descriptive)
    termination: str = ""
    final_content: str = ""
    labels: str = "EXPLORATORY: reporting-only frozen criteria; not a flood verdict; no rate claims"

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("env", "seed", "calls_per_generation", "n_calls", "n_distinct", "distinct_ratio", "machine_qualified",
                                              "shape", "termination", "final_content", "labels")}


def max_calls_guard(n: int) -> Guard:
    """Example guard: stop once the cumulative number of calls (including the pending generation) reaches n."""
    def g(gens):
        return f"max_calls_{n}" if sum(len(x) for x in gens) >= n else None
    return g


def suite_guard(suite: str = "S0") -> Guard:
    """Example guard wrapping the EXISTING draft detector suite (floodlab.detectors.stream.check_suite). DRAFT config, not validated or frozen;
    Phase 1.5 selected no policy. Provided only as a plumbing example of the guard hook."""
    from floodlab.detectors.stream import check_suite
    from floodlab.policies import SUITES

    def g(gens):
        r = check_suite(gens, SUITES[suite])
        return f"{suite}:{r.detector}" if r.flag else None
    return g


def run_agent(agent: Callable, env_name: str, seed: int = 1, *, max_turns: Optional[int] = None, call_cap: int = CR.RUN_CALL_CAP,
              guard: Optional[Guard] = None) -> RunResult:
    """Drive `agent` against the environment. Stops on: agent finished, max_turns (default = the environment's own cap), call_cap, or guard.
    A guard is evaluated on each new generation BEFORE its calls are executed; if it returns a reason, that generation is not executed."""
    env: LoopTrapEnv = make_env(env_name, seed)
    turns = env.max_turns if max_turns is None else max_turns
    msgs = env.initial_messages()
    res = RunResult(env_name, seed)
    sigs, gens_for_guard = [], []
    res.termination = f"max_turns_{turns}"
    n_id = 0
    for _ in range(turns):
        out = agent([dict(m) for m in msgs], env.tools) or {}
        calls = list(out.get("tool_calls") or [])
        content = out.get("content") or ""
        if not calls:
            res.termination, res.final_content = "agent_finished", content
            break
        if len(sigs) + len(calls) > call_cap:
            calls = calls[: max(0, call_cap - len(sigs))]
            if not calls:
                res.termination = "call_cap"
                break
        if guard is not None:
            pend = gens_for_guard + [[{"name": c["name"], "args": c["arguments"], "result_hash": None} for c in calls]]
            why = guard(pend)
            if why:
                res.termination = "guard:" + str(why)
                break
        tcs, tool_msgs, rec = [], [], []
        for c in calls:
            n_id += 1
            cid = f"lt_{n_id}"
            args = c["arguments"]
            args_str = args if isinstance(args, str) else json.dumps(args, sort_keys=True, separators=(",", ":"))
            result = env.execute(c["name"], args)
            tcs.append({"id": cid, "type": "function", "function": {"name": c["name"], "arguments": args_str}})
            tool_msgs.append({"role": "tool", "tool_call_id": cid, "content": result})
            rec.append({"name": c["name"], "arguments": args_str, "result": result})
            sigs.append(CR.signature(c["name"], args))
        msgs.append({"role": "assistant", "content": content, "tool_calls": tcs})
        msgs.extend(tool_msgs)
        res.generations.append(rec)
        gens_for_guard.append([{"name": r["name"], "args": r["arguments"], "result_hash": sha(r["result"])} for r in rec])
        if len(sigs) >= call_cap:
            res.termination = "call_cap"
            break
    res.calls_per_generation = [len(g) for g in res.generations]
    res.n_calls, res.n_distinct = len(sigs), len(set(sigs))
    res.distinct_ratio = round(CR.distinct_ratio(sigs), 4)
    res.machine_qualified = CR.is_flood_qualifying(sigs)
    res.shape = CR.describe_shape(sigs)
    return res
