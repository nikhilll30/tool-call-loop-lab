import json, time
import httpx
import pytest
from floodlab.sse import Assembler, parse_sse_line


def stream(url, payload):
    asm = Assembler(); raw = []
    with httpx.Client(timeout=30) as c, c.stream("POST", url + "/chat/completions", json=payload) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            raw.append(line)
            ev = parse_sse_line(line)
            if ev is None: continue
            if ev[0] == "done": break
            asm.feed(ev[1])
    return asm, raw


BASE = {"model": "m", "stream": True, "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]}


@pytest.mark.parametrize("mode", ["whole", "incremental"])
def test_flood_stream_both_delta_modes(upstream, mode):
    p = {**BASE, "floodlab": {"behavior": "rotating35", "seed": 1, "n_calls": 70, "delta_mode": mode}}
    asm, raw = stream(upstream.url, p)
    calls = asm.ordered_calls()
    assert len(calls) == 70 and len({(c["name"], c["arguments"]) for c in calls}) == 35
    assert all(json.loads(c["arguments"]) for c in calls)
    assert asm.reasoning and asm.usage and asm.usage["completion_tokens"] > 0
    assert raw[-2:] == ["data: [DONE]", ""] or "data: [DONE]" in raw
    # usage chunk before [DONE]
    idx_usage = max(i for i, l in enumerate(raw) if '"usage"' in l); idx_done = raw.index("data: [DONE]")
    assert idx_usage < idx_done
    assert any(l.startswith(": ") for l in raw)          # SSE comment present, must be ignorable


def test_whole_vs_incremental_chunk_counts(upstream):
    a, ra = stream(upstream.url, {**BASE, "floodlab": {"behavior": "abc", "n_calls": 3, "delta_mode": "whole"}})
    b, rb = stream(upstream.url, {**BASE, "floodlab": {"behavior": "abc", "n_calls": 3, "delta_mode": "incremental"}})
    strip = lambda cs: [(c["name"], c["arguments"]) for c in cs]
    assert strip(a.ordered_calls()) == strip(b.ordered_calls())
    assert len(rb) > len(ra)


def test_determinism(upstream):
    p = {**BASE, "floodlab": {"behavior": "start_done", "seed": 9, "n_calls": 20}}
    a, _ = stream(upstream.url, p); b, _ = stream(upstream.url, p)
    assert a.ordered_calls() == b.ordered_calls() or [c["name"] + c["arguments"] for c in a.ordered_calls()] == [c["name"] + c["arguments"] for c in b.ordered_calls()]


def test_disconnect_recorded(upstream):
    p = {**BASE, "floodlab": {"behavior": "rotating35", "seed": 1, "n_calls": 2000, "chunk_delay_s": 0.002}}
    n = 0
    with httpx.Client(timeout=30) as c, c.stream("POST", upstream.url + "/chat/completions", json=p) as r:
        for line in r.iter_lines():
            if '"tool_calls"' in line:
                n += 1
            if n >= 10: break
    for _ in range(50):
        d = httpx.get(upstream.url.replace("/v1", "") + "/debug/disconnects").json()
        if d: break
        time.sleep(0.1)
    assert d and d[0]["disconnected"] and 0 < d[0]["tokens_generated"] < d[0]["total_planned_tokens"]


def test_reasoning_passback_enforced(upstream):
    msgs = BASE["messages"] + [{"role": "assistant", "content": None, "tool_calls": [{"id": "x", "type": "function", "function": {"name": "n", "arguments": "{}"}}]}]
    r = httpx.post(upstream.url + "/chat/completions", json={**BASE, "messages": msgs})
    assert r.status_code == 400
    msgs[-1]["reasoning_content"] = "r"
    r = httpx.post(upstream.url + "/chat/completions", json={**BASE, "messages": msgs})
    assert r.status_code == 200
