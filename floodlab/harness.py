"""Replay harness: run a scenario against ANY OpenAI-compatible base_url, execute mock tools, loop turns,
preserve reasoning_content on pass-back, enforce token/call/turn caps and a $ budget, write provenance-rich traces.

SAFETY: the default is the built-in local mock upstream (loopback). A non-loopback base_url is refused unless
allow_network=True (CLI: --allow-network) AND a budget is set; the key is read from an env var *name* (never printed).
Phase 1 only ever runs against the mock. Spend ledger: spend_ledger.jsonl (one JSON line per run, $ amounts).
"""
from __future__ import annotations
import argparse, json, os, time, ipaddress
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
import httpx
from .canon import canonical_json, sha
from .config import SuiteConfig
from .detectors.stream import check_suite
from .scenarios import Scenario, PROMPT_VERSION
from .sse import Assembler, parse_sse_line
from .tools import TOOL_SCHEMAS, TOOL_SCHEMA_VERSION
from .trace import make_call, make_generation, make_provenance, make_trace, write_jsonl

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / "spend_ledger.jsonl"


class BudgetExceeded(RuntimeError):
    pass


class NetworkNotAllowed(RuntimeError):
    pass


def is_loopback(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass
class Budget:
    max_usd: float = 0.0
    price_in_per_m: float = 0.0
    price_out_per_m: float = 0.0
    spent: float = 0.0

    def cost(self, pt: int, ct: int) -> float:
        return pt * self.price_in_per_m / 1e6 + ct * self.price_out_per_m / 1e6

    def check_before(self, est_prompt_tokens: int, max_completion: int):
        worst = self.spent + self.cost(est_prompt_tokens, max_completion)
        if worst > self.max_usd + 1e-12:
            raise BudgetExceeded(f"worst-case ${worst:.4f} would exceed budget ${self.max_usd:.4f}")

    def add(self, pt, ct):
        self.spent += self.cost(pt, ct)


def append_ledger(entry: dict, path: Path = LEDGER):
    with open(path, "a") as f:
        f.write(canonical_json(entry) + "\n")


@dataclass
class Caps:
    max_turns: int = 12
    max_calls_total: int = 500
    max_completion_tokens: int = 20000     # per run (sum over generations)
    max_tokens_per_request: int = 8000


class DetectorStopHook:
    """Stop-early hook: called with all completed calls (prior turns + current partial generation);
    returns a reason dict to cancel the stream, or None. Used later by the guard."""
    def __init__(self, suite: SuiteConfig, use_state: bool = True, max_calls_per_generation: int | None = None):
        self.suite, self.use_state, self.cap = suite, use_state, max_calls_per_generation

    def __call__(self, prior_gens: list[list[dict]], current: list[dict]) -> dict | None:
        if self.cap is not None and len(current) > self.cap:
            return {"reason": "MAX_CALLS_PER_GENERATION", "detector": "cap", "at_call": len(current)}
        r = check_suite(prior_gens + [current], self.suite, self.use_state)
        if r.flag:
            return {"reason": r.reason, "detector": r.detector, "evidence": r.evidence}
        return None


def stream_generation(client: httpx.Client, base_url: str, headers: dict, payload: dict, stop_hook=None, prior_gens=None):
    """One streamed generation. Returns (Assembler, info dict). Closes the connection early if stop_hook fires."""
    asm = Assembler()
    completed: list[dict] = []
    stopped = None
    t0 = time.time()
    with client.stream("POST", base_url.rstrip("/") + "/chat/completions", json=payload, headers=headers) as resp:
        if resp.status_code != 200:
            body = resp.read().decode("utf-8", "replace")[:300]
            return asm, {"http_status": resp.status_code, "error": body, "t0": t0, "t1": time.time(), "stopped": None, "completed": completed}
        for line in resp.iter_lines():
            ev = parse_sse_line(line)
            if ev is None:
                continue
            if ev[0] == "done":
                break
            for idx in asm.feed(ev[1]):
                c = asm.calls[idx]
                completed.append({"name": c["name"], "args": c["arguments"], "ts": time.time()})
                if stop_hook is not None and stopped is None:
                    stopped = stop_hook(prior_gens or [], completed)
                    if stopped:
                        stopped["at_generation_call_count"] = len(completed)
                        break
            if stopped:
                break            # leaving the `with` closes the HTTP stream = client disconnect
    return asm, {"http_status": 200, "error": None, "t0": t0, "t1": time.time(), "stopped": stopped, "completed": completed}


def run_scenario(scenario: Scenario, base_url: str, *, model: str = "mock", api_key_env: str | None = None,
                 delta_mode: str = "whole", behavior: str = "auto", flood_kwargs: dict | None = None,
                 caps: Caps = Caps(), budget: Budget | None = None, stop_hook=None, suite: SuiteConfig | None = None,
                 guard_config="off", allow_network: bool = False, ledger_path: Path = LEDGER, reasoning_passback: bool = True,
                 extra_headers: dict | None = None) -> dict:
    if not is_loopback(base_url) and not allow_network:
        raise NetworkNotAllowed(f"{base_url} is not loopback; pass allow_network=True (Phase 1 never does)")
    budget = budget or Budget()
    if not is_loopback(base_url) and budget.max_usd <= 0:
        raise BudgetExceeded("non-loopback endpoint requires a positive budget")
    headers = dict(extra_headers or {})
    if api_key_env:
        key = os.environ.get(api_key_env)
        if key:
            headers["Authorization"] = "Bearer " + key      # never logged
    env, msgs = scenario.env(), scenario.build_messages()
    turns, prior_gens = [], []
    total_calls = total_comp = total_prompt = 0
    term = "max_turns"
    t_run = time.time()
    detector_cfg = {"id": suite.id, "hash": suite.hash()} if suite else {"id": None, "hash": None}
    with httpx.Client(timeout=60.0) as client:
        for turn in range(caps.max_turns):
            est_prompt = len(canonical_json(msgs)) // 4
            try:
                budget.check_before(est_prompt, caps.max_tokens_per_request)
            except BudgetExceeded:
                term = "budget_guard"; break
            payload = {"model": model, "messages": msgs, "tools": TOOL_SCHEMAS, "stream": True,
                       "stream_options": {"include_usage": True}, "max_tokens": caps.max_tokens_per_request,
                       "floodlab": {"behavior": behavior, "delta_mode": delta_mode, "seed": scenario.seed, **(flood_kwargs or {})}}
            asm, info = stream_generation(client, base_url, headers, payload, stop_hook, prior_gens)
            if info["http_status"] != 200:
                term = f"http_{info['http_status']}"
                turns.append({"turn": turn, "messages": [{"role": "error", "content": info["error"]}], "generations": []})
                break
            usage = asm.usage or {}
            pt, ct = usage.get("prompt_tokens", est_prompt), usage.get("completion_tokens", 0)
            total_prompt += pt; total_comp += ct
            budget.add(pt, ct)
            calls = asm.ordered_calls()
            cancelled = info["stopped"] is not None
            forwarded = calls[:len(info["completed"])] if cancelled else calls     # incomplete trailing call is discarded
            # execute tools (only when the generation was not cancelled by a stop)
            trace_calls, tool_msgs, hashes = [], [], []
            for i, c in enumerate(forwarded):
                try:
                    args = json.loads(c["arguments"])
                except json.JSONDecodeError:
                    args = None
                result = None
                if not cancelled:
                    result = env.execute(c["name"], args) if isinstance(args, dict) else json.dumps({"error": "invalid JSON arguments"})
                    tool_msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
                trace_calls.append(make_call(i, c["name"], args if args is not None else c["arguments"],
                                             ts=round(info["completed"][i]["ts"], 3) if i < len(info["completed"]) else None, result=result))
                hashes.append(sha(result) if result is not None else None)
            fr = "cancelled_by_stop_hook" if cancelled else (asm.finish_reason or "unknown")
            gen = make_generation(0, trace_calls, info["t0"], info["t1"], finish_reason=fr, cancelled=cancelled, usage=usage,
                                  content=asm.content, reasoning_content=asm.reasoning)
            if cancelled:
                gen["stop"] = info["stopped"]
            if asm.guard:
                gen["floodlab_guard"] = asm.guard
            tmsgs = [{"role": "assistant", "content": asm.content, "reasoning_content": asm.reasoning, "n_tool_calls": len(forwarded)}]
            tmsgs += [{"role": "tool", "tool_call_id": m["tool_call_id"], "result_hash": sha(m["content"])} for m in tool_msgs]
            turns.append({"turn": turn, "messages": tmsgs, "generations": [gen]})
            prior_gens.append([{"name": c["name"], "args": c["arguments"], "result_hash": h} for c, h in zip(forwarded, hashes)])
            total_calls += len(forwarded)
            if cancelled:
                term = "stopped_by_hook:" + info["stopped"]["reason"]; break
            if asm.guard:
                term = "guard_stop:" + asm.guard.get("reason", "?"); break
            if not calls:
                term = "completed" if asm.finish_reason == "stop" else f"no_calls:{asm.finish_reason}"; break
            if total_calls > caps.max_calls_total:
                term = "call_cap"; break
            if total_comp > caps.max_completion_tokens:
                term = "token_cap"; break
            am = {"role": "assistant", "content": asm.content or None,
                  "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]}
            if reasoning_passback:
                am["reasoning_content"] = asm.reasoning
            msgs.append(am)
            msgs.extend(tool_msgs)
    latency = time.time() - t_run
    tr = make_trace(f"run-{scenario.id}-{scenario.mode}-{scenario.seed}-{behavior}-{delta_mode}",
                    make_provenance(model=model, endpoint=base_url if not api_key_env else urlparse(base_url).netloc,
                                    scenario=f"{scenario.id}/{scenario.mode}", seed=scenario.seed, detector_config=detector_cfg,
                                    guard_config=guard_config, prompt_version=PROMPT_VERSION, tool_schema_version=TOOL_SCHEMA_VERSION),
                    turns, label="unknown", shape="", synthetic=is_loopback(base_url), split="none",
                    latency_s=round(latency, 3), cost_usd=round(budget.spent, 6), termination_reason=term,
                    notes=f"mock-upstream run; delta_mode={delta_mode}; tokens prompt={total_prompt} completion={total_comp}")
    append_ledger({"run_id": tr["run_id"], "model": model, "endpoint_kind": "mock-loopback" if is_loopback(base_url) else "remote",
                   "usd": round(budget.spent, 6), "prompt_tokens": total_prompt, "completion_tokens": total_comp,
                   "live_call": not is_loopback(base_url), "phase": "1-offline"}, ledger_path)
    return tr


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Replay harness (default: in-process local mock upstream, $0)")
    ap.add_argument("--scenario", default="pagination"); ap.add_argument("--mode", default="plain"); ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--base-url", default=None, help="OpenAI-compatible base URL. Omit to use the local mock upstream (--dry-run default).")
    ap.add_argument("--api-key-env", default=None, help="NAME of env var holding the key (value never printed)")
    ap.add_argument("--allow-network", action="store_true"); ap.add_argument("--budget-usd", type=float, default=0.0)
    ap.add_argument("--price-in", type=float, default=0.0); ap.add_argument("--price-out", type=float, default=0.0)
    ap.add_argument("--model", default="mock"); ap.add_argument("--delta-mode", default="whole", choices=["whole", "incremental"])
    ap.add_argument("--behavior", default="auto"); ap.add_argument("--out", default=str(ROOT / "data" / "traces" / "harness_run.jsonl"))
    ap.add_argument("--dry-run", action="store_true", help="force the local mock upstream even if --base-url is given")
    a = ap.parse_args(argv)
    from .mock_upstream.app import create_app
    from .servers import LocalServer
    sc = Scenario(a.scenario, a.mode, a.seed)
    budget = Budget(a.budget_usd, a.price_in, a.price_out)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    if a.base_url is None or a.dry_run:
        with LocalServer(create_app()) as srv:
            tr = run_scenario(sc, srv.url, delta_mode=a.delta_mode, behavior=a.behavior, budget=budget, model=a.model)
    else:
        tr = run_scenario(sc, a.base_url, model=a.model, api_key_env=a.api_key_env, delta_mode=a.delta_mode, behavior=a.behavior,
                          budget=budget, allow_network=a.allow_network)
    write_jsonl(a.out, [tr])
    print(f"wrote {a.out}: termination={tr['termination_reason']} turns={len(tr['turns'])} cost=${tr['cost_usd']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
