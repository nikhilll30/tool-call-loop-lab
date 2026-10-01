"""Local mock OpenAI-compatible upstream: /v1/chat/completions with streaming SSE tool_calls.

Deterministic replay of scripted behaviours (no model, no network). Request extension field `floodlab`:
  {"behavior": "auto|normal|rotating35|start_done|abc|cross_turn|cancel_retry|rotating35_multi",
   "seed": int, "delta_mode": "whole|incremental", "n_calls": int, "turns": int, "chunk_delay_s": float,
   "require_reasoning_passback": bool}
behavior "auto" derives the behaviour from the scenario mode embedded in the system prompt.
Disconnect detection: when the client closes mid-stream, the number of tokens "generated" so far is recorded in
app.state.disconnects (simulated billing-stop measurement: real providers may keep generating; this mock stops at
the moment the disconnect is observed, so the number is the *lower bound* the mock can report).
"""
from __future__ import annotations
import asyncio, json, random, re, time
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from ..canon import canonical_json
from ..scenarios import Scenario
from ..gen.floods import _pool

SCEN_RE = re.compile(r"\[floodlab scenario=(\w+) mode=(\w+) seed=(-?\d+)\]")
MODE_TO_BEHAVIOR = {"plain": "normal", "history_primed": "rotating35", "rotating_argument": "rotating35",
                    "ab_alternating": "start_done", "cross_turn": "cross_turn"}
DEFAULT_N = {"rotating35": 400, "rotating35_multi": 20, "start_done": 200, "abc": 60, "cross_turn": 12, "cancel_retry": 17}
DEFAULT_TURNS = {"rotating35": 1, "start_done": 1, "abc": 1, "cross_turn": 6, "cancel_retry": 10, "rotating35_multi": 20}


def tok(s: str) -> int:
    return max(1, len(s) // 4)


def _sse(obj) -> str:
    return "data: " + json.dumps(obj, separators=(",", ":")) + "\n\n"


def plan_calls(behavior: str, seed: int, n: int, k: int, fl: dict | None = None) -> list[dict]:
    """k = 0-based index of this flood turn. Returns [{name, arguments(dict)}]."""
    rng = random.Random(seed)
    if behavior == "cycle":      # Phase 2A families: repeat fl["cycle"] (list of {name, arguments}) n calls per turn, continuing across turns
        cyc = (fl or {})["cycle"]
        return [dict(cyc[(k * n + i) % len(cyc)]) for i in range(n)]
    if behavior == "rotating35":
        pool = _pool(rng, 35)
        return [{"name": a, "arguments": b} for a, b in (pool[i % 35] for i in range(n))]
    if behavior == "rotating35_multi":
        pool = _pool(rng, 35)
        return [{"name": a, "arguments": b} for a, b in (pool[(k * 20 + i) % 35] for i in range(20))]
    if behavior == "start_done":
        tasks = [f"T{rng.randint(100, 999)}_{i}" for i in range(35)]
        out = []
        for i in range(n):
            t = tasks[(i // 2) % 35] if i % 2 == 0 else tasks[((i // 2) - 1) % 35]
            out.append({"name": "start_job" if i % 2 == 0 else "get_job_status", "arguments": {"job": t}})
        return out
    if behavior == "abc":
        abc = _pool(rng, 3)
        return [{"name": a, "arguments": b} for a, b in (abc[i % 3] for i in range(n))]
    if behavior in ("cross_turn", "cancel_retry"):
        pool = _pool(rng, n)
        return [{"name": a, "arguments": b} for a, b in pool]
    raise ValueError(behavior)


def create_app() -> FastAPI:
    app = FastAPI(title="floodlab mock upstream")
    app.state.disconnects = []
    app.state.requests = []
    app.state.n429 = 0        # number of injected 429 responses
    app.state.chat_count = 0  # number of chat requests received (incl. 429s)
    app.state.gens = {}       # generation id -> OpenRouter-like /generation record (simulated)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/debug/disconnects")
    def disconnects():
        return app.state.disconnects

    @app.get("/debug/requests")
    def requests_log():
        return app.state.requests

    @app.get("/api/v1/generation")
    def generation(id: str):
        g = app.state.gens.get(id)
        if g is None:
            return JSONResponse({"error": {"code": 404, "message": "Resource not found"}}, status_code=404)
        return {"data": g}

    @app.post("/v1/chat/completions")
    @app.post("/api/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        fl = body.get("floodlab", {}) or {}
        messages = body.get("messages", [])
        app.state.chat_count += 1
        # 429 injection (tests): first N requests, and/or every request from the k-th on (0-based, counting all chat requests)
        if (app.state.n429 < int(fl.get("http_429_first_n", 0))) or ("http_429_from_request" in fl and app.state.chat_count - 1 >= int(fl["http_429_from_request"])):
            app.state.n429 += 1
            hdr = {"Retry-After": str(fl["retry_after"])} if "retry_after" in fl else {}
            return JSONResponse({"error": {"message": "Provider returned error", "code": 429,
                                           "metadata": {"raw": "mock: temporarily rate-limited upstream"}}}, status_code=429, headers=hdr)
        # MiMo-like rule: with thinking on, assistant tool-call messages must pass reasoning_content back
        if fl.get("require_reasoning_passback", True):
            for m in messages:
                if m.get("role") == "assistant" and m.get("tool_calls") and "reasoning_content" not in m and "reasoning" not in m:
                    return JSONResponse({"error": {"message": "reasoning_content must be passed back with tool_calls", "code": 400}}, status_code=400)
        sm = next((SCEN_RE.search(m["content"]) for m in messages if m["role"] == "system" and SCEN_RE.search(m.get("content") or "")), None)
        scen = Scenario(sm.group(1), sm.group(2), int(sm.group(3))) if sm else None
        behavior = fl.get("behavior", "auto")
        if behavior == "auto":
            behavior = MODE_TO_BEHAVIOR.get(scen.mode, "normal") if scen else "normal"
        seed = int(fl.get("seed", scen.seed if scen else 0))
        mode = fl.get("delta_mode", "whole")
        delay = float(fl.get("chunk_delay_s", 0.0005))
        rfield = fl.get("reasoning_field", "reasoning_content")
        provider = fl.get("provider", "Darkbloom")
        cost_mult = float(fl.get("cost_multiplier", 1.0))
        PIN, POUT = 0.018, 0.09
        n_prior = sum(1 for m in messages if m["role"] == "assistant" and m.get("tool_calls") and not m["tool_calls"][0]["id"].startswith("prime_"))
        calls, final_text, finish = [], "", "tool_calls"
        long_n = 0
        if behavior == "long_text":            # long streamed reasoning (Phase 2A disconnect test); no tool calls
            long_n = int(fl.get("n_pieces", 400)); final_text, finish = "Done.", "stop"
        elif behavior == "normal":
            oracle = scen.next_calls(messages) if scen else None
            if oracle:
                calls = oracle
            else:
                final_text, finish = "Done. The task is complete.", "stop"
        else:
            n = int(fl.get("n_calls", DEFAULT_N.get(behavior, 1)))
            turns = int(fl.get("turns", DEFAULT_TURNS.get(behavior, 50)))
            if n_prior >= turns:
                final_text, finish = "Giving up; final answer.", "stop"
            else:
                calls = plan_calls(behavior, seed, n, n_prior, fl)
                finish = "length" if behavior in ("rotating35", "start_done", "abc") else "tool_calls"
        rid = (f"gen-mock-{seed}-{n_prior}-{len(app.state.requests)}" if fl.get("gen_ids") else f"chatcmpl-mock-{seed}-{n_prior}-{len(app.state.requests)}")
        prompt_tokens = tok(canonical_json(messages))
        app.state.requests.append({"id": rid, "behavior": behavior, "delta_mode": mode, "n_calls": len(calls), "n_messages": len(messages)})
        rec = {"id": rid, "behavior": behavior, "planned_calls": len(calls), "tokens_generated": 0}

        async def gen():
            chunk = lambda delta, fr=None, **kw: _sse({"id": rid, "object": "chat.completion.chunk", "created": 1700000000,
                                                       "model": body.get("model", "mock"), "provider": provider, "choices": [{"index": 0, "delta": delta, "finish_reason": fr}], **kw})
            try:
                yield ": MOCK PROCESSING\n\n"    # SSE comment clients must ignore
                yield chunk({"role": "assistant", "content": ""})
                if long_n:
                    for i in range(long_n):
                        yield chunk({rfield: f"w{i} "})
                        rec["tokens_generated"] += 2
                        if i % 5 == 0:
                            await asyncio.sleep(delay)
                            if await request.is_disconnected():
                                raise asyncio.CancelledError()
                if calls:
                    for piece in ("Let me ", "work through ", "this."):
                        yield chunk({rfield: piece})
                        rec["tokens_generated"] += tok(piece)
                if final_text:
                    yield chunk({"content": final_text})
                    rec["tokens_generated"] += tok(final_text)
                for i, c in enumerate(calls):
                    args = canonical_json(c["arguments"])
                    cid = f"call_{rid}_{i}"
                    if mode == "whole":
                        yield chunk({"tool_calls": [{"index": i, "id": cid, "type": "function", "function": {"name": c["name"], "arguments": args}}]})
                    else:
                        yield chunk({"tool_calls": [{"index": i, "id": cid, "type": "function", "function": {"name": c["name"], "arguments": ""}}]})
                        step = max(4, len(args) // 3)
                        for p in range(0, len(args), step):
                            yield chunk({"tool_calls": [{"index": i, "function": {"arguments": args[p:p + step]}}]})
                            if delay: await asyncio.sleep(delay / 3)
                    rec["tokens_generated"] += tok(c["name"] + args) + 8
                    if await request.is_disconnected():
                        raise asyncio.CancelledError()
                    await asyncio.sleep(delay)
                yield chunk({}, finish)
                completion = rec["tokens_generated"]
                cost = (prompt_tokens * PIN + completion * POUT) / 1e6 * cost_mult
                app.state.gens[rid] = {"id": rid, "model": body.get("model", "mock"), "provider_name": provider, "cancelled": False,
                                       "tokens_prompt": prompt_tokens, "tokens_completion": completion, "native_tokens_prompt": prompt_tokens,
                                       "native_tokens_completion": completion, "native_tokens_reasoning": 0, "total_cost": cost,
                                       "finish_reason": finish, "streamed": True}
                yield _sse({"id": rid, "object": "chat.completion.chunk", "model": body.get("model", "mock"), "provider": provider, "choices": [],
                            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion, "total_tokens": prompt_tokens + completion,
                                      "cost": cost, "completion_tokens_details": {"reasoning_tokens": 0}}})
                yield "data: [DONE]\n\n"
                rec["completed"] = True
            except (asyncio.CancelledError, GeneratorExit):
                rec.update(completed=False, disconnected=True, total_planned_tokens=sum(tok(c["name"] + canonical_json(c["arguments"])) + 8 for c in calls))
                billed = rec["tokens_generated"] + int(fl.get("billing_overrun_tokens", 0))
                app.state.gens[rid] = {"id": rid, "model": body.get("model", "mock"), "provider_name": provider, "cancelled": True,
                                       "tokens_prompt": prompt_tokens, "tokens_completion": billed, "native_tokens_prompt": prompt_tokens,
                                       "native_tokens_completion": billed, "native_tokens_reasoning": 0,
                                       "total_cost": (prompt_tokens * PIN + billed * POUT) / 1e6 * cost_mult, "finish_reason": None, "streamed": True}
                app.state.disconnects.append(rec)
                raise

        if not body.get("stream"):
            return JSONResponse({"id": rid, "object": "chat.completion", "model": body.get("model", "mock"),
                                 "choices": [{"index": 0, "finish_reason": finish, "message": {
                                     "role": "assistant", "content": final_text or None, "reasoning_content": "Let me work through this." if calls else None,
                                     "tool_calls": [{"id": f"call_{rid}_{i}", "type": "function", "function": {"name": c["name"], "arguments": canonical_json(c["arguments"])}} for i, c in enumerate(calls)] or None}}],
                                 "provider": provider,
                                 "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 1, "total_tokens": prompt_tokens + 1,
                                           "cost": (prompt_tokens * PIN + 1 * POUT) / 1e6 * cost_mult}})
        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


app = create_app()
