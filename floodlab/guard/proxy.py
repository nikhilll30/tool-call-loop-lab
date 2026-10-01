"""Streaming guard proxy SKELETON (Phase 4 will evaluate it; nothing here is a result).

client -> guard (/v1/chat/completions, stream=true) -> upstream OpenAI-compatible endpoint.

Behaviour:
 * Reasoning/content deltas are forwarded immediately.
 * Tool-call deltas are HELD (buffer_tool_calls=True, default) so a flood never reaches the client's executor;
   they are released when the generation ends cleanly, dropped when the guard fires.
 * After every completed call: per-generation cap, then the detector library (frozen suite) over
   [history rebuilt from the request's messages] + [current generation]. Result hashes come from the tool messages
   in the request, so the state-aware detector works statelessly.
 * On fire: close the upstream stream (disconnect), emit a final chunk with finish_reason=<cfg> and a structured
   `floodlab_guard` object, a usage chunk (guard-counted), and [DONE].
 * #2509: per-conversation state counts consecutive byte-identical batches (>= min size); after N the guard refuses
   without contacting upstream (HARD_STOP_IDENTICAL_BATCH_RETRIES).
Limits: non-streaming requests are rejected (400); conversation fingerprint = hash(system + first user message).
"""
from __future__ import annotations
import json, time
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from ..canon import canonical_json, sha
from ..config import GuardConfig
from ..detectors.stream import check_suite
from ..sse import Assembler

MIN_BATCH_FOR_RETRY_COUNT = 3


def history_from_messages(messages: list[dict]) -> list[list[dict]]:
    """Rebuild prior generations [[{name,args,result_hash}]] from an OpenAI-style message list."""
    results = {m.get("tool_call_id"): sha(m.get("content") or "") for m in messages if m.get("role") == "tool"}
    gens = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            gens.append([{"name": c["function"]["name"], "args": c["function"]["arguments"], "result_hash": results.get(c["id"])}
                         for c in m["tool_calls"]])
    return gens


def fingerprint(messages: list[dict]) -> str:
    first = [m for m in messages if m.get("role") in ("system", "user")][:2]
    return sha(canonical_json([(m["role"], m.get("content")) for m in first]))


def batch_sig(calls: list[dict]) -> str:
    return sha(canonical_json([(c["name"], c["args"]) for c in calls]))


def _sse(o) -> str:
    return "data: " + json.dumps(o, separators=(",", ":")) + "\n\n"


def guard_chunk(model, gid, guard: dict, finish_reason: str) -> str:
    return _sse({"id": gid, "object": "chat.completion.chunk", "model": model,
                 "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}], "floodlab_guard": guard})


def create_guard_app(upstream_base_url: str, cfg: GuardConfig | None = None, *, buffer_tool_calls: bool = True,
                     finish_reason: str = "stop", upstream_headers: dict | None = None) -> FastAPI:
    cfg = cfg or GuardConfig()
    app = FastAPI(title="floodlab guard proxy (skeleton)")
    app.state.cfg = cfg
    app.state.convs = {}      # fingerprint -> {"last_sig", "count"}
    app.state.events = []     # guard decisions (machine-readable)

    def make_guard(reason, detector, **kw):
        g = {"stopped": True, "reason": reason, "detector": detector, "config_id": cfg.id, "config_hash": cfg.hash(), **kw}
        app.state.events.append(g)
        return g

    @app.get("/health")
    def health():
        return {"ok": True, "guard_config": cfg.id, "guard_hash": cfg.hash()}

    @app.get("/debug/events")
    def events():
        return app.state.events

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        if not body.get("stream"):
            return JSONResponse({"error": {"message": "guard skeleton requires stream=true", "code": 400}}, status_code=400)
        messages = body.get("messages", [])
        model = body.get("model", "unknown")
        fp = fingerprint(messages)
        conv = app.state.convs.setdefault(fp, {"last_sig": None, "count": 0})
        hist = history_from_messages(messages)
        gid = "guard-" + fp[:8]

        # hard stop (#2509): refuse before contacting upstream
        if conv["count"] >= cfg.hard_stop_after_identical_cancelled:
            g = make_guard("HARD_STOP_IDENTICAL_BATCH_RETRIES", "identical_batch_counter", identical_batches=conv["count"], upstream_contacted=False)

            async def refuse():
                yield guard_chunk(model, gid, g, finish_reason)
                yield "data: [DONE]\n\n"
            return StreamingResponse(refuse(), media_type="text/event-stream")

        headers = dict(upstream_headers or {})
        if request.headers.get("authorization"):
            headers["Authorization"] = request.headers["authorization"]

        async def relay():
            asm = Assembler()
            completed: list[dict] = []
            held: list[str] = []
            fired = None
            t0 = time.time()
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", upstream_base_url.rstrip("/") + "/chat/completions", json=body, headers=headers) as resp:
                    if resp.status_code != 200:
                        err = (await resp.aread()).decode("utf-8", "replace")[:300]
                        yield _sse({"error": {"message": err, "code": resp.status_code, "source": "upstream"}})
                        yield "data: [DONE]\n\n"
                        return
                    async for line in resp.aiter_lines():
                        s = line.strip()
                        if not s or s.startswith(":"):
                            continue
                        if not s.startswith("data:"):
                            continue
                        payload = s[5:].strip()
                        if payload == "[DONE]":
                            break
                        chunk = json.loads(payload)
                        is_tc = any((ch.get("delta") or {}).get("tool_calls") for ch in chunk.get("choices", []))
                        is_fin = any(ch.get("finish_reason") for ch in chunk.get("choices", []))
                        if chunk.get("usage") and not chunk.get("choices"):
                            asm.feed(chunk)
                            held.append(_sse(chunk)); continue
                        for idx in asm.feed(chunk):
                            c = asm.calls[idx]
                            completed.append({"name": c["name"], "args": c["arguments"]})
                            if len(completed) > cfg.max_calls_per_generation:
                                fired = make_guard("MAX_CALLS_PER_GENERATION", "cap", calls_seen=len(completed), cap=cfg.max_calls_per_generation)
                            else:
                                r = check_suite(hist + [completed], cfg.suite, use_state=True)
                                if r.flag:
                                    fired = make_guard(r.reason, r.detector, calls_seen=len(completed), first_index=r.first_index, evidence=r.evidence)
                            if fired:
                                break
                        if fired:
                            break
                        if is_tc and buffer_tool_calls:
                            held.append(_sse(chunk))
                        elif is_fin and held:
                            # clean end: release held tool-call chunks, then the finish chunk
                            for h in held: yield h
                            held.clear(); yield _sse(chunk)
                        else:
                            yield _sse(chunk)
            # (leaving the context managers above closed the upstream connection if we broke out early)
            batch = completed
            if batch and len(batch) >= MIN_BATCH_FOR_RETRY_COUNT:
                sig = batch_sig(batch)
                conv["count"] = conv["count"] + 1 if conv["last_sig"] == sig else 1
                conv["last_sig"] = sig
            else:
                conv["last_sig"], conv["count"] = None, 0
            if fired is None and conv["count"] >= cfg.hard_stop_after_identical_cancelled:
                fired = make_guard("HARD_STOP_IDENTICAL_BATCH_RETRIES", "identical_batch_counter", identical_batches=conv["count"], upstream_contacted=True)
            if fired:
                fired.update(dropped_tool_calls=len(completed) if buffer_tool_calls else 0, elapsed_s=round(time.time() - t0, 3))
                yield guard_chunk(model, gid, fired, finish_reason)
                yield _sse({"id": gid, "object": "chat.completion.chunk", "model": model, "choices": [],
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "note": "guard-side; see upstream billing"}})
            else:
                for h in held: yield h
            yield "data: [DONE]\n\n"

        return StreamingResponse(relay(), media_type="text/event-stream")

    return app
