"""Phase 2A: EXPLORATORY, UNGUARDED live trace collection (openai/gpt-oss-20b pinned to ONE provider (PINNED_NAME) via OpenRouter), hard-capped at $1.00.

    python -m floodlab.phase2a --preflight          # checks OPENROUTER_API_KEY by NAME only (value never read into any output)
    python -m floodlab.phase2a --mock               # whole flow against the loopback mock upstream, $0  (output: results/tmp/phase2a_mock/)
    python -m floodlab.phase2a --live               # the real thing (needs the key; refuses otherwise); output: data/exploratory_2A/

Safety properties (all enforced in code, see floodlab/budget.py and tests/test_phase2a.py):
 * key: read from the environment by the process only; put only in the Authorization header of an in-memory dict; every string that is saved or
   printed goes through `Redactor.scrub`. Headers are never stored.
 * budget: every request is pre-charged at a conservative worst case BEFORE launch and refused if spent + worst_case > $0.90 (hard cap $1.00).
 * pinned provider: {"order": [PINNED_NAME], "allow_fallbacks": false}; any other provider served, any error, rate limit, auth failure, >3x cost
   surprise or billing discrepancy STOPS the collection (exit code 3) and is reported; the provider is never unpinned.
 * a run is cancelled (HTTP stream closed) the moment it is flood-qualifying by the frozen definition (floodlab/criteria.py).
 * no detector or guard is run; traces carry split "exploratory-2A" and the note that they are NOT confirmatory data for Guard v2.
"""
from __future__ import annotations
import argparse, gzip, json, os, re, statistics, sys, time
from pathlib import Path
import httpx
from . import criteria as CR
from .budget import Anomaly, BudgetGuard, BudgetRefused, EFFECTIVE_CAP_USD, HARD_CAP_USD, est_tokens
from .canon import canonical_json, sha
from .scenarios import PROMPT_VERSION, Scenario, MODES
from .splits import EXPLORATORY_NOTE
from .sse import Assembler, parse_sse_line
from .tools import TOOL_SCHEMAS, TOOL_SCHEMA_VERSION
from .trace import make_call, make_generation, make_provenance, make_trace

ROOT = Path(__file__).resolve().parent.parent
KEY_ENV = "OPENROUTER_API_KEY"
LIVE_ROOT = "https://openrouter.ai"
MODEL = "openai/gpt-oss-20b"
PINNED_NAME = "Darkbloom"       # chosen per docs/PHASE2A_PROVIDER_CHOICE.md (DeepInfra was persistently 429ing; earlier DeepInfra data stays labelled DeepInfra)
PROVIDER_PIN = {"order": [PINNED_NAME], "allow_fallbacks": False}
SPLIT = "exploratory-2A"
LIVE_OUT = ROOT / "data" / "exploratory_2A"
MOCK_OUT = ROOT / "results" / "tmp" / "phase2a_mock"
LIVE_LEDGER = ROOT / "spend_ledger.jsonl"
ELICIT_MODES = ["history_primed", "rotating_argument", "ab_alternating", "cross_turn"]
SCEN_CYCLE = ["multi_hop", "fan_out", "pagination", "fix_loop", "missing_path", "error_fallback"]
# 429 retry window (connectivity + smoke only): 8 attempts/stage, backoff 45,90,180,360,400,400,400 s x jitter[0.5,1] ~ 23 min expected, 30 min hard wall
DEFAULT_RETRY_ATTEMPTS, DEFAULT_RETRY_WALL_S, DEFAULT_RETRY_BASE_S, DEFAULT_RETRY_CAP_S = 8, 1800.0, 45.0, 400.0
DEFAULT_RETRY_GLOBAL_WALL_S = 3600.0     # whole-process bound on time spent waiting in 429 backoff (per-scope window is DEFAULT_RETRY_WALL_S)
TAG_RE = re.compile(r"\s*\[floodlab scenario=[^\]]*\]")


class Redactor:
    """Scrubs the key value (held only in memory) and any OpenRouter-key-shaped token from every string that is saved or printed."""
    PAT = re.compile(r"sk-or-[A-Za-z0-9_\-]{6,}")

    def __init__(self, key: str | None):
        self._key = key

    def scrub(self, s):
        if not isinstance(s, str):
            return s
        if self._key:
            s = s.replace(self._key, "[REDACTED]")
        return self.PAT.sub("[REDACTED]", s)


def preflight_key_present() -> bool:
    return bool(os.environ.get(KEY_ENV))


class Upstream:
    def __init__(self, live: bool, root: str, key: str | None = None, mock_opts: dict | None = None):
        self.live, self.root, self._key, self.mock_opts = live, root.rstrip("/"), key, mock_opts or {}
        self.redact = Redactor(key)

    def __repr__(self):
        return f"Upstream(live={self.live}, root={self.root})"

    @property
    def chat_url(self):
        return self.root + ("/api/v1/chat/completions" if self.live else "/v1/chat/completions")

    @property
    def gen_url(self):
        return self.root + "/api/v1/generation"

    @property
    def key_url(self):
        return self.root + "/api/v1/key"

    def headers(self, extra=True) -> dict:
        h = {"Content-Type": "application/json"}
        if self._key:
            h["Authorization"] = "Bearer " + self._key          # in-memory only; never stored or printed
        if self.live and extra:
            h["X-Title"] = "tool-call-loop-lab phase2a"
        return h


def log(msg: str):
    print(msg, flush=True)


# --------------------------------------------------------------------------------------------- config
class Config:
    def __init__(self, live: bool, out_dir: Path, ledger_path: Path, max_tokens=4000, max_turns=8, max_calls=CR.RUN_CALL_CAP,
                 per_mode_initial=2, max_runs=30, stop_at_floods=5, cap=EFFECTIVE_CAP_USD, connectivity_max_tokens=64,
                 cancel_test_after_chunks=150, gen_retries=8, gen_retry_sleep=3.0, price_in=None, price_out=None,
                 retry_global_wall_s=DEFAULT_RETRY_GLOBAL_WALL_S, retry_max_attempts=DEFAULT_RETRY_ATTEMPTS, retry_total_wall_s=DEFAULT_RETRY_WALL_S, retry_base_s=DEFAULT_RETRY_BASE_S, retry_cap_s=DEFAULT_RETRY_CAP_S, sleep=None, rng=None):
        self.live, self.out_dir, self.ledger_path = live, Path(out_dir), Path(ledger_path)
        self.max_tokens, self.max_turns, self.max_calls = max_tokens, max_turns, max_calls
        self.per_mode_initial, self.max_runs, self.stop_at_floods, self.cap = per_mode_initial, max_runs, stop_at_floods, cap
        self.connectivity_max_tokens, self.cancel_test_after_chunks = connectivity_max_tokens, cancel_test_after_chunks
        self.gen_retries, self.gen_retry_sleep = gen_retries, gen_retry_sleep
        self.retry_global_wall_s = retry_global_wall_s
        self.retry_max_attempts, self.retry_total_wall_s, self.retry_base_s, self.retry_cap_s = retry_max_attempts, retry_total_wall_s, retry_base_s, retry_cap_s
        import random as _r
        self.sleep = sleep or time.sleep
        self.rng = rng or _r.Random()
        self.price_in, self.price_out = price_in, price_out


class Collector:
    def __init__(self, cfg: Config, up: Upstream, guard: BudgetGuard):
        self.cfg, self.up, self.guard = cfg, up, guard
        self.out = cfg.out_dir
        (self.out / "raw").mkdir(parents=True, exist_ok=True)
        self.traces: list[dict] = []
        self.requests: list[dict] = []      # request-level records (also written to requests.jsonl)
        self.stages: dict = {"anomaly": None, "cancel_observations": [], "stage_status": {}}
        self.pending_recon: list[dict] = []
        self.retry_state = {"attempts": {}, "wall_s": 0.0, "scope_wall_s": {}}
        self.stages["retries"] = []
        self.real_spent_settled = 0.0
        self.client = httpx.Client(timeout=httpx.Timeout(60.0, read=120.0))
        self.run_counter = 0

    # ----------------------------------------------------------------------- io
    def save(self):
        (self.out / "stages.json").write_text(json.dumps(self.stages, indent=1, default=str))

    def append_jsonl(self, name: str, obj: dict):
        with open(self.out / name, "a") as f:
            f.write(canonical_json(json.loads(self.up.redact.scrub(canonical_json(obj)))) + "\n")

    # ----------------------------------------------------------------------- payload
    def payload(self, messages, *, tools, max_tokens, stream, seed, mock_ext=None) -> dict:
        p = {"model": MODEL, "messages": messages, "max_tokens": max_tokens, "stream": stream, "provider": PROVIDER_PIN}
        if tools:
            p["tools"] = tools
        if stream:
            p["stream_options"] = {"include_usage": True}
        if self.up.live:
            p["usage"] = {"include": True}
        else:
            p["floodlab"] = {"behavior": "auto", "seed": seed, "delta_mode": "incremental" if seed % 2 else "whole", "reasoning_field": "reasoning",
                             "gen_ids": True, **self.up.mock_opts, **(mock_ext or {})}
        return p

    # ----------------------------------------------------------------------- one streamed request
    def stream_request(self, payload, *, sigs_prior, run_calls_prior, cancel_after_chunks=None, raw_name=None) -> dict:
        asm, completed, sigs, raw = Assembler(), [], [], []
        info = {"http_status": None, "error": None, "provider": None, "gen_id": None, "model_returned": None, "stopped": None, "chunks": 0,
                "comments": 0, "bad_lines": 0, "done_seen": False, "usage_chunk_has_choices": None, "usage_after_finish": None,
                "mid_stream_error": None}
        seen_finish = False
        t0 = time.time(); ttfb = None
        with self.client.stream("POST", self.up.chat_url, json=payload, headers=self.up.headers()) as resp:
            info["http_status"] = resp.status_code
            if resp.status_code != 200:
                info["error"] = self.up.redact.scrub(resp.read().decode("utf-8", "replace")[:600])
                info["retry_after"] = resp.headers.get("retry-after")
                info.update(asm=asm, completed=completed, sigs=sigs, t0=t0, ttfb=None, t1=time.time(), chars=0)
                return info
            for line in resp.iter_lines():
                if line.startswith(":"):
                    info["comments"] += 1
                    continue
                if not line.strip():
                    continue
                raw.append(self.up.redact.scrub(line))
                try:
                    ev = parse_sse_line(line)
                except json.JSONDecodeError:
                    info["bad_lines"] += 1
                    continue
                if ev is None:
                    continue
                if ev[0] == "done":
                    info["done_seen"] = True
                    break
                ch = ev[1]
                info["chunks"] += 1
                if ttfb is None:
                    ttfb = time.time() - t0
                info["gen_id"] = info["gen_id"] or ch.get("id")
                info["model_returned"] = info["model_returned"] or ch.get("model")
                if ch.get("provider"):
                    info["provider"] = info["provider"] or ch["provider"]
                    info["provider_chunks"] = info.get("provider_chunks", 0) + 1
                    if str(ch["provider"]).lower() != PINNED_NAME.lower():           # checked on EVERY chunk that names a provider
                        info["stopped"] = {"reason": "anomaly_provider_not_pinned", "provider": ch["provider"]}
                        break
                if ch.get("usage"):
                    info["usage_chunk_has_choices"] = bool(ch.get("choices"))
                    info["usage_after_finish"] = seen_finish
                if ch.get("error"):
                    info["mid_stream_error"] = self.up.redact.scrub(json.dumps(ch["error"])[:500])
                    info["stopped"] = {"reason": "anomaly_mid_stream_error"}
                    break
                for idx in asm.feed(ch):
                    c = asm.calls[idx]
                    completed.append({"name": c["name"], "args": c["arguments"], "ts": time.time()})
                    sigs.append(CR.signature(c["name"], c["arguments"]))
                    allsigs = sigs_prior + sigs
                    if CR.is_flood_qualifying(allsigs):
                        info["stopped"] = {"reason": "flood_qualifying_cancelled", "at_run_call_count": len(allsigs),
                                           "distinct_ratio": round(CR.distinct_ratio(allsigs), 4)}
                        break
                    if len(allsigs) >= self.cfg.max_calls:
                        info["stopped"] = {"reason": f"call_cap_{self.cfg.max_calls}", "at_run_call_count": len(allsigs)}
                        break
                if info["stopped"]:
                    break
                if any(c.get("finish_reason") for c in ch.get("choices", [])):
                    seen_finish = True
                if cancel_after_chunks and info["chunks"] >= cancel_after_chunks:
                    info["stopped"] = {"reason": "deliberate_early_disconnect_test", "after_chunks": info["chunks"]}
                    break
            t_stop = time.time()
            # leaving the `with` block closes the HTTP stream (client disconnect) when we stopped early
        if info["stopped"]:
            info["stopped"].setdefault("t_cancel", round(t_stop, 3))
            info["stopped"]["t_closed"] = round(time.time(), 3)
            info["stopped"]["chunks_at_cancel"] = info["chunks"]
            info["stopped"]["elapsed_since_request_s"] = round(t_stop - t0, 3)
        chars = len(asm.content) + len(asm.reasoning) + sum(len(c["name"]) + len(c["arguments"]) for c in asm.calls.values())
        if info["stopped"]:
            info["stopped"].update(chars_at_cancel=chars, reasoning_chars_at_cancel=len(asm.reasoning), content_chars_at_cancel=len(asm.content),
                                   est_tokens_at_cancel=round(chars / 4))
        if raw_name and raw:
            with gzip.open(self.out / "raw" / (raw_name + ".sse.gz"), "wt") as f:
                f.write("\n".join(raw) + "\n")
        info.update(asm=asm, completed=completed, sigs=sigs, t0=t0, ttfb=ttfb, t1=time.time(), chars=chars)
        return info

    # ----------------------------------------------------------------------- budget-guarded request wrapper
    def guarded(self, key: str, stage: str, run_id: str, messages, tools, max_tokens, fn):
        """pre-charge -> launch -> settle. fn(key) performs the HTTP request and returns (usage dict|None, extra dict)."""
        wc, est_p = self.guard.worst_case_request(messages, tools or [], max_tokens)
        self.guard.hard_check()
        self.guard.precharge(key, wc, stage=stage, run_id=run_id, model=MODEL, provider=PINNED_NAME + "(pinned)", est_prompt_tokens=est_p,
                             max_tokens=max_tokens, prompt_tokens=None, completion_tokens=None)
        return wc, est_p

    def settle(self, key, stage, run_id, wc, usage, provider, gen_id, cancelled):
        usage = usage or {}
        pt, ct = usage.get("prompt_tokens"), usage.get("completion_tokens")
        rt = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        if usage.get("cost") is not None:
            usd, src = float(usage["cost"]), "usage.cost"
        elif pt is not None and ct is not None:
            usd, src = self.guard.cost(pt, ct), "computed_from_tokens"
        else:
            return None            # no usage (cancelled / failed): keep the worst-case charge until the /generation reconcile
        tok_cost = self.guard.cost(pt or 0, ct or 0)
        if usd > wc + 1e-12:
            self.guard.settle(key, usd, src, stage=stage, run_id=run_id, model=MODEL, provider=provider, prompt_tokens=pt, completion_tokens=ct, gen_id=gen_id)
            raise Anomaly(f"actual cost ${usd:.6f} exceeds the worst-case pre-charge ${wc:.6f} ({key})")
        if tok_cost > 1e-5 and usd > 3 * tok_cost:
            self.guard.settle(key, usd, src, stage=stage, run_id=run_id, model=MODEL, provider=provider, prompt_tokens=pt, completion_tokens=ct, gen_id=gen_id)
            raise Anomaly(f"reported cost ${usd:.6f} is >3x the token-based estimate ${tok_cost:.6f} ({key})")
        self.guard.settle(key, usd, src, stage=stage, run_id=run_id, model=MODEL, provider=provider, prompt_tokens=pt, completion_tokens=ct,
                          reasoning_tokens=rt, gen_id=gen_id)
        self.real_spent_settled += usd
        return usd

    # ----------------------------------------------------------------------- /generation reconcile (free metadata GET)
    def fetch_generation(self, gen_id: str, retries=None) -> dict | None:
        retries = self.cfg.gen_retries if retries is None else retries
        for i in range(retries):
            try:
                r = self.client.get(self.up.gen_url, params={"id": gen_id}, headers=self.up.headers(extra=False))
            except httpx.HTTPError as e:
                log(f"  generation GET transport error ({type(e).__name__}); retrying")
                r = None
            if r is not None and r.status_code == 200:
                try:
                    return r.json().get("data")
                except Exception:
                    return None
            if r is not None and r.status_code in (401, 402, 403, 429):
                raise Anomaly(f"/generation returned HTTP {r.status_code}")
            time.sleep(self.cfg.gen_retry_sleep if self.up.live else 0.05)
        return None

    def fetch_key_usage(self) -> float | None:
        """Total account-key usage in USD from GET /api/v1/key (free). ONLY the numeric `usage` field is read; nothing else is kept or printed."""
        if not self.up.live:
            return None
        try:
            r = self.client.get(self.up.key_url, headers=self.up.headers(extra=False))
            if r.status_code == 200:
                u = r.json().get("data", {}).get("usage")
                return float(u) if u is not None else None
        except Exception:
            return None
        return None

    def reconcile(self, final=False):
        still = []
        for rec in self.pending_recon:
            g = self.fetch_generation(rec["gen_id"], retries=(self.cfg.gen_retries if final else 3))
            if g is None:
                rec["recon_attempts"] = rec.get("recon_attempts", 0) + 1
                still.append(rec)
                continue
            total = g.get("total_cost")
            rr = rec["request_record"]
            rr["generation"] = {k: g.get(k) for k in ("cancelled", "tokens_prompt", "tokens_completion", "native_tokens_prompt", "native_tokens_completion",
                                                     "native_tokens_reasoning", "total_cost", "provider_name", "finish_reason", "streamed", "latency",
                                                     "generation_time", "model", "num_media_prompt")}
            prov = g.get("provider_name")
            if prov and str(prov).lower() != PINNED_NAME.lower():
                raise Anomaly(f"/generation reports provider {prov!r} for {rec['gen_id']} (pinned {PINNED_NAME})")
            if total is not None:
                delta = self.guard.reconcile(rec["key"], float(total), stage=rec["stage"], run_id=rec["run_id"], model=MODEL, provider=prov, gen_id=rec["gen_id"],
                                             prompt_tokens=g.get("tokens_prompt"), completion_tokens=g.get("tokens_completion"))
                rr["reconciled_usd"] = float(total)
                if rec["cancelled"]:
                    self.real_spent_settled += float(total)
                if not rec["cancelled"]:
                    settled = rr.get("usd_settled")
                    if settled is not None and abs(float(total) - settled) > max(0.0005, 0.2 * settled):
                        raise Anomaly(f"billing discrepancy for {rec['gen_id']}: usage.cost ${settled:.6f} vs /generation total_cost ${float(total):.6f}")
                if rec["cancelled"]:
                    est_tok = rr.get("est_tokens_received")
                    obs = {"gen_id": rec["gen_id"], "run_id": rec["run_id"], "stage": rec["stage"], "stop_reason": rec.get("stop_reason"),
                           "max_tokens_requested": rr.get("max_tokens"), "generation_finish_reason": g.get("finish_reason"),
                           "chunks_received": rr.get("chunks"), "chars_received": rr.get("chars_received"), "est_completion_tokens_received(chars/4)": est_tok,
                           "generation_cancelled_flag": g.get("cancelled"), "generation_tokens_completion": g.get("tokens_completion"),
                           "generation_native_tokens_completion": g.get("native_tokens_completion"),
                           "generation_native_tokens_reasoning": g.get("native_tokens_reasoning"), "generation_total_cost_usd": total,
                           "precharge_usd": rec.get("precharge"), "ratio_reported_tokens_to_received_est": (round(g["tokens_completion"] / est_tok, 3)
                                                                                           if est_tok and g.get("tokens_completion") is not None else None)}
                    self.stages["cancel_observations"].append(obs)
            self.append_jsonl("requests.jsonl", rr)
        self.pending_recon = still
        self.save()

    # ----------------------------------------------------------------------- bounded 429 retry (connectivity + smoke ONLY)
    RETRY_STAGES = ("connectivity", "smoke", "pilot", "disconnect", "f3fu")

    def on_429(self, stage: str, key: str, run_id: str, attempt: int, retry_after=None, body: str = ""):
        """Called after an HTTP 429 (no generation started). Releases the provisional pre-charge (real spend $0), cross-checks the key usage
        counter, and (for RETRY_STAGES within budget) sleeps with exponential backoff + jitter and returns; otherwise raises Anomaly (stop & report).
        The provider is NEVER changed."""
        self.guard.release(key, "http_429_no_generation", stage=stage, run_id=run_id, model=MODEL, provider=PINNED_NAME + "(pinned)", http_status=429)
        ku = self.fetch_key_usage()
        if ku is not None and self.stages.get("key_usage_start_usd") is not None:
            excess = ku - (self.stages["key_usage_start_usd"] + self.real_spent_settled)
            slack = sum(r.get("precharge") or 0.0 for r in self.pending_recon if r.get("cancelled"))       # cancelled requests billed but not yet reconciled
            if excess > 2e-5 + slack + 0.05 * (self.real_spent_settled or 0):
                raise Anomaly(f"key usage counter (${ku:.6f}) exceeds real settled spend by ${excess:.6f} after a 429: billing discrepancy")
        scope = run_id if stage in ("pilot", "f3fu") else stage       # pilot: attempts counted per run (a 429 is only ever retried at a clean turn boundary)
        used = self.retry_state["attempts"].get(scope, 0) + 1
        self.retry_state["attempts"][scope] = used
        if stage not in self.RETRY_STAGES:
            self.stages["retries"].append({"stage": stage, "attempt": attempt, "status": 429, "action": "STOP (no retry outside connectivity/smoke)"})
            self.guard.note("429 in non-retry stage: stopping", stage=stage, run_id=run_id, http_status=429)
            raise Anomaly(f"HTTP 429 during {stage} stage (retries are only allowed for connectivity/smoke): {self.up.redact.scrub(body[:200])}")
        wait = min(self.cfg.retry_cap_s, self.cfg.retry_base_s * (2 ** (used - 1)))
        wait = wait * (0.5 + 0.5 * self.cfg.rng.random())          # jitter in [0.5, 1.0] x backoff
        if retry_after is not None:
            try:
                wait = max(wait, min(float(retry_after), self.cfg.retry_cap_s))
            except ValueError:
                pass
        rec = {"stage": stage, "attempt": used, "status": 429, "wait_s": round(wait, 2), "key_usage_usd": ku}
        if used >= self.cfg.retry_max_attempts:
            rec["action"] = "STOP (retry attempts exhausted)"
        elif self.retry_state["scope_wall_s"].get(scope, 0.0) + wait > self.cfg.retry_total_wall_s:
            rec["action"] = "STOP (retry wall-time budget exhausted)"
        elif self.retry_state["wall_s"] + wait > self.cfg.retry_global_wall_s:
            rec["action"] = "STOP (global retry wall-time budget exhausted)"
        else:
            rec["action"] = "retry"
        self.stages["retries"].append(rec)
        self.guard.note(f"429 retry stage={stage} attempt={used} wait={rec['wait_s']}s action={rec['action']}", stage=stage, run_id=run_id, http_status=429)
        log(f"  [retry] stage={stage} attempt={used}/{self.cfg.retry_max_attempts} status=429 wait={rec['wait_s']}s -> {rec['action']}")
        self.save()
        if rec["action"] != "retry":
            raise Anomaly(f"still rate-limited (HTTP 429) after {used} attempt(s) in stage {stage}: {rec['action']}; provider stays pinned to {PINNED_NAME}")
        self.cfg.sleep(wait)
        self.retry_state["wall_s"] += wait
        self.retry_state["scope_wall_s"][scope] = self.retry_state["scope_wall_s"].get(scope, 0.0) + wait

    # ----------------------------------------------------------------------- stage 1: connectivity
    def stage_connectivity(self):
        run_id = "p2a-connectivity"
        msgs = [{"role": "user", "content": "Reply with the single word: ok"}]
        p = self.payload(msgs, tools=None, max_tokens=self.cfg.connectivity_max_tokens, stream=False, seed=0)
        attempt = 0
        while True:
            attempt += 1
            key = f"{run_id}-r0-a{attempt}"
            wc, _ = self.guarded(key, "connectivity", run_id, msgs, None, self.cfg.connectivity_max_tokens, None)
            t0 = time.time()
            r = self.client.post(self.up.chat_url, json=p, headers=self.up.headers())
            dt = time.time() - t0
            if r.status_code == 429:
                self.on_429("connectivity", key, run_id, attempt, r.headers.get("retry-after"), r.text)
                continue
            break
        rec = {"stage": "connectivity", "run_id": run_id, "http_status": r.status_code, "latency_s": round(dt, 3), "attempts": attempt}
        if r.status_code != 200:
            rec["error"] = self.up.redact.scrub(r.text[:600])
            self.stages["connectivity"] = rec
            raise Anomaly(f"connectivity check failed: HTTP {r.status_code} {rec['error'][:200]}")
        d = r.json()
        if d.get("error"):
            rec["error"] = self.up.redact.scrub(json.dumps(d["error"])[:500])
            self.stages["connectivity"] = rec
            raise Anomaly("connectivity check returned an error body: " + rec["error"][:200])
        prov = d.get("provider")
        usage = d.get("usage") or {}
        ch = (d.get("choices") or [{}])[0]
        msg = ch.get("message") or {}
        rec.update(provider=prov, model_returned=d.get("model"), gen_id=d.get("id"), finish_reason=ch.get("finish_reason"), usage=usage,
                   content=self.up.redact.scrub(msg.get("content") or ""), reasoning_present=bool(msg.get("reasoning") or msg.get("reasoning_content")),
                   reasoning_chars=len(msg.get("reasoning") or msg.get("reasoning_content") or ""), max_tokens=self.cfg.connectivity_max_tokens)
        self.stages["connectivity"] = rec
        usd = self.settle(key, "connectivity", run_id, wc, usage, prov, d.get("id"), False)
        rr = {"request_key": key, "stage": "connectivity", "run_id": run_id, "gen_id": d.get("id"), "provider": prov, "usage": usage, "usd_settled": usd,
              "latency_s": round(dt, 3), "cancelled": False}
        self.requests.append(rr)
        if prov and str(prov).lower() != PINNED_NAME.lower():
            raise Anomaly(f"connectivity check served by provider {prov!r}, not {PINNED_NAME}")
        if d.get("id"):
            self.pending_recon.append({"key": key, "gen_id": d["id"], "stage": "connectivity", "run_id": run_id, "cancelled": False, "request_record": rr})
        log(f"[connectivity] ok provider={prov} finish={ch.get('finish_reason')} usd={usd} spent=${self.guard.spent():.6f}")

    # ----------------------------------------------------------------------- one scenario run (stages: smoke / elicit / cancel_test)
    def run_scenario_live(self, stage: str, scenario: Scenario, *, cancel_after_chunks=None) -> dict:
        self.run_counter += 1
        run_id = f"{'p2a' if self.up.live else 'p2a-mock'}-{stage}-{scenario.mode}-{scenario.id}-{scenario.seed}"
        self.guard.check(self.guard.worst_case_run(getattr(scenario, "max_turns", None) or self.cfg.max_turns, getattr(scenario, "max_tokens", None) or self.cfg.max_tokens), f"launch run {run_id}")
        env = scenario.env()
        msgs = scenario.build_messages()
        tools = getattr(scenario, "tools", TOOL_SCHEMAS)
        max_turns = getattr(scenario, "max_turns", None) or self.cfg.max_turns
        max_tokens_req = getattr(scenario, "max_tokens", None) or self.cfg.max_tokens
        mock_ext = getattr(scenario, "mock_ext", None)
        if self.up.live:
            msgs = [dict(m, content=TAG_RE.sub("", m["content"])) if m["role"] == "system" else m for m in msgs]
        turns, run_sigs, run_calls_total = [], [], 0
        term, anomaly = "max_turns_%d" % max_turns, None
        run_cost, run_pt, run_ct, shape_agg = 0.0, 0, 0, []
        t_run = time.time()
        req_records, cancelled_any = [], False
        try:
            for turn in range(max_turns):
                wc, est_p = self.guard.worst_case_request(msgs, tools, max_tokens_req)
                if est_p > self.guard.prompt_ceiling:
                    term = "prompt_ceiling"; break
                try:
                    self.guard.check(wc, f"request {run_id}#{turn}")
                except BudgetRefused as e:
                    term = "budget_guard"; log(f"  BUDGET GUARD: {e}"); break
                attempt = 0
                while True:
                    attempt += 1
                    key = f"{run_id}-r{turn}" + (f"-a{attempt}" if attempt > 1 else "")
                    wc, est_p = self.guard.worst_case_request(msgs, tools, max_tokens_req)
                    self.guard.check(wc, f"request {run_id}#{turn} attempt {attempt}")
                    self.guard.hard_check()
                    self.guard.precharge(key, wc, stage=stage, run_id=run_id, model=MODEL, provider=PINNED_NAME + "(pinned)", est_prompt_tokens=est_p,
                                         max_tokens=max_tokens_req, prompt_tokens=None, completion_tokens=None)
                    payload = self.payload(msgs, tools=tools, max_tokens=max_tokens_req, stream=True, seed=scenario.seed, mock_ext=mock_ext)
                    try:
                        info = self.stream_request(payload, sigs_prior=run_sigs, run_calls_prior=run_calls_total, cancel_after_chunks=cancel_after_chunks,
                                                   raw_name=f"{run_id}__t{turn}")
                    except httpx.HTTPError as e:
                        raise Anomaly(f"transport error {type(e).__name__} on {run_id}#{turn} (charge kept at worst case)")
                    if info["http_status"] == 429:
                        # no generation started (turn boundary / before run): release pre-charge; bounded retry in connectivity/smoke/disconnect/pilot; other stages stop
                        self.on_429(stage, key, run_id, attempt, info.get("retry_after"), info["error"] or "")
                        continue
                    break
                asm = info["asm"]
                if info["http_status"] != 200:
                    turns.append({"turn": turn, "messages": [{"role": "error", "content": info["error"]}], "generations": []})
                    raise Anomaly(f"HTTP {info['http_status']} on {run_id}#{turn}: {(info['error'] or '')[:300]}")
                stopped = info["stopped"]
                usage = asm.usage or {}
                provider = info["provider"]
                usd = self.settle(key, stage, run_id, wc, usage, provider, info["gen_id"], bool(stopped))
                if usd is not None:
                    run_cost += usd
                run_pt += usage.get("prompt_tokens") or 0; run_ct += usage.get("completion_tokens") or 0
                shp = asm.shape_summary(); shape_agg.append(shp)
                rr = {"request_key": key, "stage": stage, "run_id": run_id, "turn": turn, "gen_id": info["gen_id"], "provider": provider,
                      "model_returned": info["model_returned"], "usage": usage, "usd_settled": usd, "precharge_usd": wc, "cancelled": bool(stopped),
                      "stop_reason": (stopped or {}).get("reason"), "ttfb_s": round(info["ttfb"], 3) if info["ttfb"] is not None else None,
                      "latency_s": round(info["t1"] - info["t0"], 3), "chunks": info["chunks"], "sse_comment_lines": info["comments"],
                      "bad_sse_lines": info["bad_lines"], "done_seen": info["done_seen"], "chars_received": info["chars"],
                      "est_tokens_received": round(info["chars"] / 4), "max_tokens": max_tokens_req, "stop": stopped, "shape": shp, "finish_reason": asm.finish_reason,
                      "usage_chunk_has_choices": info["usage_chunk_has_choices"], "usage_after_finish": info["usage_after_finish"]}
                self.requests.append(rr); req_records.append(rr)
                if info["gen_id"]:
                    self.pending_recon.append({"key": key, "gen_id": info["gen_id"], "stage": stage, "run_id": run_id, "cancelled": bool(stopped),
                                               "stop_reason": (stopped or {}).get("reason"), "precharge": wc, "request_record": rr})
                if info["mid_stream_error"]:
                    raise Anomaly(f"mid-stream error on {run_id}#{turn}: {info['mid_stream_error'][:300]}")
                if stopped and stopped["reason"] == "anomaly_provider_not_pinned":
                    raise Anomaly(f"served by provider {stopped['provider']!r}, not {PINNED_NAME} ({run_id}#{turn})")
                if provider is None and self.up.live and turn == 0:
                    log("  note: no provider field in stream chunks; relying on /generation provider_name")
                # ---- calls of this generation
                calls = asm.ordered_calls()
                if stopped:
                    calls = calls[:len(info["completed"])]
                    cancelled_any = True
                truncated_dropped = False
                if asm.finish_reason == "length" and calls and not stopped:
                    try:
                        json.loads(calls[-1]["arguments"])
                    except json.JSONDecodeError:
                        calls = calls[:-1]; truncated_dropped = True
                seen_ids, quirks = set(), {"missing_ids": 0, "duplicate_ids": 0}
                for i, c in enumerate(calls):
                    if not c["id"]:
                        quirks["missing_ids"] += 1; c["id"] = f"synth_{turn}_{i}"
                    elif c["id"] in seen_ids:
                        quirks["duplicate_ids"] += 1; c["id"] = f"{c['id']}__dup{i}"
                    seen_ids.add(c["id"])
                trace_calls, tool_msgs = [], []
                for i, c in enumerate(calls):
                    try:
                        args = json.loads(c["arguments"]) if c["arguments"] else {}
                    except json.JSONDecodeError:
                        args = None
                    result = None
                    if not stopped:
                        result = env.execute(c["name"], args) if isinstance(args, dict) else canonical_json({"error": "invalid JSON arguments"})
                        tool_msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
                    ts = round(info["completed"][i]["ts"], 3) if i < len(info["completed"]) else None
                    trace_calls.append(make_call(i, c["name"], args if args is not None else c["arguments"], ts=ts, result=result))
                gen = make_generation(0, trace_calls, info["t0"], info["t1"], finish_reason=("cancelled_by_client:" + stopped["reason"]) if stopped else (asm.finish_reason or "unknown"),
                                      cancelled=bool(stopped), usage=usage, content=asm.content, reasoning_content=asm.reasoning)
                gen.update(gen_id=info["gen_id"], provider_served=provider, ttfb_s=rr["ttfb_s"], request_latency_s=rr["latency_s"], request_cost_usd=usd,
                           reasoning_field_seen=sorted(asm.reasoning_fields), delta_shape=shp, quirks=quirks, truncated_last_call_dropped=truncated_dropped)
                if stopped:
                    gen["stop"] = stopped
                tmsgs = [{"role": "assistant", "content": asm.content, "reasoning": asm.reasoning, "n_tool_calls": len(calls)}]
                tmsgs += [{"role": "tool", "tool_call_id": m["tool_call_id"], "result_hash": sha(m["content"])} for m in tool_msgs]
                turns.append({"turn": turn, "messages": tmsgs, "generations": [gen]})
                run_sigs.extend(CR.signature(c["name"], c["arguments"]) for c in calls)
                run_calls_total = len(run_sigs)
                log(f"  [{run_id}] turn {turn}: calls+{len(calls)} total={run_calls_total} distinct={len(set(run_sigs))} finish={gen['finish_reason']} "
                    f"usd={usd if usd is None else round(usd, 6)} spent=${self.guard.spent():.5f}")
                if stopped:
                    term = stopped["reason"]; break
                if not calls:
                    term = "completed" if asm.finish_reason == "stop" else f"no_calls:{asm.finish_reason}"; break
                rf = sorted(asm.reasoning_fields)[0] if asm.reasoning_fields else "reasoning"
                am = {"role": "assistant", "content": asm.content or None,
                      "tool_calls": [{"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}} for c in calls]}
                am[rf] = asm.reasoning
                if getattr(asm, "reasoning_details_merged", None):        # MiMo pilot: pass OpenRouter reasoning_details back unmodified (merged fragments)
                    am["reasoning_details"] = asm.reasoning_details_merged
                msgs.append(am); msgs.extend(tool_msgs)
        except Anomaly as e:
            anomaly = str(e); term = "anomaly"
        except BudgetRefused as e:
            term = "budget_guard"; log(f"  BUDGET GUARD: {e}")
        latency = time.time() - t_run
        n = len(run_sigs)
        qual = CR.is_flood_qualifying(run_sigs)
        gens = [g for t in turns for g in t.get("generations", [])]
        provs = sorted({g.get("provider_served") for g in gens if g.get("provider_served")})
        prov = make_provenance(model=MODEL, endpoint=(self.up.root + "/api/v1/chat/completions") if self.up.live else "mock-loopback",
                               scenario=f"{scenario.id}/{scenario.mode}", seed=scenario.seed,
                               detector_config={"id": CR.CRITERIA_ID, "hash": CR.CRITERIA_HASH, "note": "frozen flood-qualifying criteria only; no detector/guard run"},
                               guard_config="off", prompt_version=getattr(scenario, "prompt_version", PROMPT_VERSION) + ("+tagless" if self.up.live else ""), tool_schema_version=getattr(scenario, "tool_schema_version", TOOL_SCHEMA_VERSION))
        prov.update(provider_pinned=PROVIDER_PIN, provider_served=provs, gen_ids=[g.get("gen_id") for g in gens], max_tokens=max_tokens_req,
                    max_turns=max_turns, max_calls_cap=self.cfg.max_calls, stage=stage, mode=scenario.mode, temperature="provider default",
                    **getattr(scenario, "provenance_extra", {}))
        tr = make_trace(run_id, prov, turns, label="unknown", shape=CR.describe_shape(run_sigs) if qual else "", synthetic=not self.up.live, split=SPLIT,
                        latency_s=round(latency, 3), cost_usd=round(run_cost, 8), termination_reason=term,
                        notes=EXPLORATORY_NOTE + f"; prompt tokens={run_pt} completion tokens={run_ct}")
        tr["exploratory"] = True
        tr["flood_qualifying_machine"] = qual
        tr["human_confirmation"] = "PENDING (maintainer)" if qual else "n/a"
        tr["stats"] = {"n_calls": n, "n_distinct": len(set(run_sigs)), "distinct_ratio": round(CR.distinct_ratio(run_sigs), 4) if n else None,
                       "n_turns": len(turns), "criteria_hash": CR.CRITERIA_HASH, "mode": scenario.mode, "scenario": scenario.id, "stage": stage,
                       "cancelled": cancelled_any, "delta_shape": shape_agg[:1] and shape_agg, "anomaly": anomaly}
        self.traces.append(tr)
        self.append_jsonl("traces.jsonl", tr)
        for rr in req_records:
            pass
        self.save()
        if anomaly:
            self.stages["anomaly"] = {"run_id": run_id, "message": self.up.redact.scrub(anomaly)}
            self.save()
            raise Anomaly(anomaly)
        return tr

    # ----------------------------------------------------------------------- orchestration
    def scenario_for(self, mode: str, j: int, seed: int) -> Scenario:
        off = ELICIT_MODES.index(mode)
        return Scenario(SCEN_CYCLE[(j + off) % len(SCEN_CYCLE)], mode, seed)

    def repetition_sign(self, t: dict) -> bool:
        s = t["stats"]
        return bool(t["flood_qualifying_machine"] or (s["n_calls"] >= 10 and s["distinct_ratio"] is not None and s["distinct_ratio"] <= 0.6))

    def n_qual(self):
        return sum(1 for t in self.traces if t["stats"]["stage"] == "elicit" and t["flood_qualifying_machine"])

    def run_all(self):
        cfg = self.cfg
        self.stages.update(mode="live" if self.up.live else "mock", model=MODEL, provider_pin=PROVIDER_PIN, cap_effective=cfg.cap, cap_hard=HARD_CAP_USD,
                           caps={"max_tokens_per_request": cfg.max_tokens, "max_turns": cfg.max_turns, "max_calls": cfg.max_calls},
                           criteria=CR.CRITERIA, criteria_hash=CR.CRITERIA_HASH, started_at=time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                           spent_before_usd=self.guard.spent())
        self.stages["key_usage_start_usd"] = self.fetch_key_usage()
        try:
            log("== stage 1: connectivity ==")
            self.stage_connectivity(); self.stages["stage_status"]["connectivity"] = "ok"; self.save()
            log("== stage 2: smoke (streamed tool-calling, pagination/plain) ==")
            tr = self.run_scenario_live("smoke", Scenario("pagination", "plain", 1000))
            self.stages["stage_status"]["smoke"] = f"{tr['termination_reason']} calls={tr['stats']['n_calls']}"
            self.reconcile(); self.save()
            log("== stage 3: elicitation (prompt modes) ==")
            per_mode: dict[str, int] = {m: 0 for m in ELICIT_MODES}
            seed_ctr = [2000]
            n_elicit = lambda: sum(1 for t in self.traces if t["stats"]["stage"] == "elicit")

            def one(mode):
                j = per_mode[mode]; per_mode[mode] += 1; seed_ctr[0] += 1
                tr = self.run_scenario_live("elicit", self.scenario_for(mode, j, seed_ctr[0]))
                self.reconcile()
                return tr

            def done():
                return self.n_qual() >= cfg.stop_at_floods or n_elicit() >= cfg.max_runs
            for rnd in range(cfg.per_mode_initial):
                for m in ELICIT_MODES:
                    if done():
                        break
                    one(m)
            adaptive_log = []
            while not done():
                signs = {m: [t for t in self.traces if t["stats"]["stage"] == "elicit" and t["stats"]["mode"] == m and self.repetition_sign(t)] for m in ELICIT_MODES}
                quals = {m: sum(1 for t in signs[m] if t["flood_qualifying_machine"]) for m in ELICIT_MODES}
                order = sorted(ELICIT_MODES, key=lambda m: (-quals[m], -len(signs[m])))
                progressed = False
                for m in order:
                    want = 3 if signs[m] else (1 if per_mode[m] < cfg.per_mode_initial + 1 else 0)
                    for _ in range(want):
                        if done():
                            break
                        one(m); progressed = True
                    adaptive_log.append({"mode": m, "signs": len(signs[m]), "qualifying": quals[m], "extra_runs": want})
                    if done():
                        break
                if not progressed:
                    break
            self.stages["adaptive_log"] = adaptive_log
            self.stages["stage_status"]["elicit"] = f"{n_elicit()} runs, {self.n_qual()} flood-qualifying"
            stop_reason = ("enough evidence: >= %d flood-qualifying runs" % cfg.stop_at_floods) if self.n_qual() >= cfg.stop_at_floods else \
                ("max_runs reached" if n_elicit() >= cfg.max_runs else "all modes tried at small N; no further runs indicated")
            self.stages["collection_stop_reason"] = stop_reason
            log(f"== collection stopped: {stop_reason} ==")
            # ---- deliberate early-disconnect billing test if nothing was cancelled
            if not any(t["stats"]["cancelled"] for t in self.traces):
                log("== cancel/billing test: deliberate early disconnect ==")
                self.stages["cancel_test"] = "deliberate early-disconnect run"
                self.run_scenario_live("cancel_test", Scenario("fan_out", "rotating_argument", 3000), cancel_after_chunks=cfg.cancel_test_after_chunks)
            self.reconcile(final=True)
        except (Anomaly, BudgetRefused) as e:
            if isinstance(e, BudgetRefused):
                self.stages["budget_refusal"] = str(e)
            if self.stages.get("anomaly") is None and isinstance(e, Anomaly):
                self.stages["anomaly"] = {"message": self.up.redact.scrub(str(e))}
            log(f"!! STOP: {self.up.redact.scrub(str(e))}")
            try:
                self.reconcile(final=False)
            except Anomaly:
                pass
        finally:
            self.stages["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
            self.stages["spent_after_usd"] = self.guard.spent()
            self.stages["key_usage_end_usd"] = self.fetch_key_usage()
            self.stages["unreconciled_requests"] = [r["gen_id"] for r in self.pending_recon]
            self.save()
            self.client.close()
        return self.stages


# --------------------------------------------------------------------------------------------- secret scan
def secret_scan(paths, key: str | None) -> dict:
    """Scan files (incl. .gz) for the key VALUE (in memory) and key-shaped tokens / Authorization header values. Never prints matches' content."""
    pat = re.compile(r"sk-or-[A-Za-z0-9_\-]{6,}|Bearer\s+[A-Za-z0-9_\-\.]{16,}")
    files = []
    for p in map(Path, paths):
        files += [q for q in p.rglob("*") if q.is_file()] if p.is_dir() else ([p] if p.exists() else [])
    hits, n = [], 0
    for f in files:
        try:
            data = gzip.open(f, "rt", errors="replace").read() if f.suffix == ".gz" else f.read_text(errors="replace")
        except Exception:
            continue
        n += 1
        if (key and key in data) or pat.search(data):
            hits.append(str(f.relative_to(ROOT)) if str(f).startswith(str(ROOT)) else str(f))
    text = (f"Scanned {n} files (out dir, raw SSE .gz, ledger, this report) for the exact key value, `sk-or-...` tokens and `Bearer <token>` strings: "
            + ("**no matches - CLEAN**" if not hits else f"**MATCHES in {hits}**"))
    return {"clean": not hits, "hits": hits, "text": text}


# --------------------------------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Phase 2A exploratory unguarded collection (hard cap $1.00, effective $0.90)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--preflight", action="store_true", help="check the key is present (by name only) and exit")
    g.add_argument("--mock", action="store_true", help="run the whole flow against the loopback mock upstream ($0) [default]")
    g.add_argument("--live", action="store_true", help="LIVE OpenRouter calls (requires OPENROUTER_API_KEY)")
    g.add_argument("--report-only", action="store_true", help="regenerate the report from an existing out-dir")
    ap.add_argument("--out-dir", default=None); ap.add_argument("--ledger", default=None)
    ap.add_argument("--max-runs", type=int, default=30); ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--max-turns", type=int, default=8); ap.add_argument("--per-mode-initial", type=int, default=2)
    ap.add_argument("--cap", type=float, default=EFFECTIVE_CAP_USD)
    ap.add_argument("--retry-attempts", type=int, default=DEFAULT_RETRY_ATTEMPTS, help="max 429 attempts per stage (connectivity/smoke only)")
    ap.add_argument("--retry-wall-s", type=float, default=DEFAULT_RETRY_WALL_S, help="total wall time budget across 429 retries")
    ap.add_argument("--retry-base-s", type=float, default=DEFAULT_RETRY_BASE_S); ap.add_argument("--retry-cap-s", type=float, default=DEFAULT_RETRY_CAP_S)
    a = ap.parse_args(argv)
    if a.preflight:
        ok = preflight_key_present()
        print(f"{KEY_ENV}: {'present' if ok else 'ABSENT'} (checked by name only; value never read into output)")
        print(f"model={MODEL} provider pin={json.dumps(PROVIDER_PIN)} hard cap=${HARD_CAP_USD:.2f} effective cap=${a.cap:.2f}")
        return 0 if ok else 2
    if a.report_only:
        from .phase2a_report import write_report
        out = Path(a.out_dir) if a.out_dir else LIVE_OUT
        p = write_report(out, Path(a.ledger) if a.ledger else LIVE_LEDGER, mock=False, report_path=ROOT / "PHASE2A_REPORT.md")
        print("wrote", p); return 0
    live = a.live
    if live and not preflight_key_present():
        print(f"REFUSING live run: {KEY_ENV} is not set in the environment (checked by name only). No request was made.", file=sys.stderr)
        return 2
    out_dir = Path(a.out_dir) if a.out_dir else (LIVE_OUT if live else MOCK_OUT)
    ledger = Path(a.ledger) if a.ledger else (LIVE_LEDGER if live else out_dir / "spend_ledger.jsonl")
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = Config(live, out_dir, ledger, max_tokens=a.max_tokens, max_turns=a.max_turns, per_mode_initial=a.per_mode_initial, max_runs=a.max_runs, cap=a.cap,
                 retry_max_attempts=a.retry_attempts, retry_total_wall_s=a.retry_wall_s, retry_base_s=a.retry_base_s, retry_cap_s=a.retry_cap_s)
    guard = BudgetGuard(ledger, live=live, cap=a.cap)
    if live and guard.spent() >= guard.cap:
        print(f"REFUSING: ledger already shows ${guard.spent():.4f} >= effective cap ${guard.cap:.2f}", file=sys.stderr); return 2
    if live:
        up = Upstream(True, LIVE_ROOT, key=os.environ[KEY_ENV])
        col = Collector(cfg, up, guard)
        stages = col.run_all()
    else:
        from .mock_upstream.app import create_app
        from .servers import LocalServer
        for f in ("traces.jsonl", "requests.jsonl", "stages.json"):
            (out_dir / f).unlink(missing_ok=True)
        ledger.unlink(missing_ok=True)
        with LocalServer(create_app()) as srv:
            up = Upstream(False, srv.url.rsplit("/v1", 1)[0])
            col = Collector(cfg, up, guard)
            stages = col.run_all()
    from .phase2a_report import write_report
    rp = write_report(out_dir, ledger, mock=not live, report_path=(ROOT / "PHASE2A_REPORT.md") if live else out_dir / "PHASE2A_REPORT.MOCK.md")
    scan = secret_scan([out_dir, rp] + ([ledger] if live else []), os.environ.get(KEY_ENV) if live else None)
    rp.write_text(rp.read_text().replace("(filled by the runner's post-run scan)", scan["text"]))
    print("secret scan:", "CLEAN" if scan["clean"] else "!! FOUND MATCHES: " + str(scan["hits"]))
    print("report:", rp)
    print(f"spent: ${guard.spent():.6f}")
    return 3 if stages.get("anomaly") else 0


if __name__ == "__main__":
    raise SystemExit(main())
