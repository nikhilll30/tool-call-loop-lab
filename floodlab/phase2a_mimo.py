"""Phase 2A MiMo-V2.6-Flash pilot (docs/PHASE2A_MIMO_PILOT_PLAN.md). EXPLORATORY-2A only. Reuses the Phase 2A collector/budget/SSE code; no detector, guard or criteria code is touched.

    python -m floodlab.phase2a_mimo --mock                          # whole flow against the loopback mock, $0
    python -m floodlab.phase2a_mimo --live --stage connectivity     # 1 request, max_tokens 64
    python -m floodlab.phase2a_mimo --live --stage disconnect       # 3 requests (disconnect after 30 / 120 chunks + control), max_tokens 400
    python -m floodlab.phase2a_mimo --live --stage smoke            # 1 M2 run, 3 turns
    python -m floodlab.phase2a_mimo --live --stage families         # M1, M2, M3, F1a, F7 + <=3 adaptive extension runs (<= 9 runs in total with smoke)
    python -m floodlab.phase2a_mimo --live --stage report
Model xiaomi/mimo-v2.6-flash, provider pinned to Xiaomi (first party) {"order":["Xiaomi"],"allow_fallbacks":false}; checkpoint: unknown (provider-claimed, likely fixed MOPD).
ATTEMPT 3 (attempts 1-2 pinned to Novita aborted at $0, status -2). This is a likely-fixed-model CONTRAST, not a reproduction of the historical pre-fix RL failure.
Pilot cap $0.10 on spend since pilot start (in addition to the cumulative $0.90 effective / $1.00 hard caps), $0.02 per run, guard prices 0.15/0.30 $/M x 1.25, prompt ceiling 16k tokens.
"""
from __future__ import annotations
import argparse, contextlib, json, os, re, statistics, sys, time
from collections import Counter
from pathlib import Path
from . import criteria as CR
from . import phase2a as P
from . import phase2a_pilot as PP
from .budget import Anomaly, BudgetGuard, BudgetRefused
from .phase2a_common import load_jsonl
from .phase2a_mimo_families import make as make_mimo
from .phase2a_report import excerpt
from .sse import Assembler

MODEL_MIMO = "xiaomi/mimo-v2.6-flash"
PIN_NAME = "Xiaomi"
PIN = {"order": [PIN_NAME], "allow_fallbacks": False}
CHECKPOINT = "unknown (provider-claimed, likely fixed MOPD)"
RUN_SET = "mimo-pilot-xiaomi-1"
PILOT_CAP_USD = 0.10
RUN_CAP_USD = 0.02
GUARD_PRICE_IN, GUARD_PRICE_OUT = 0.15, 0.30
PROMPT_CEILING = 16000
MAX_TOKENS = 3000
MAX_RUNS_TOTAL = 9
OUT = P.LIVE_OUT / "mimo_pilot_xiaomi"
MOCK_OUT = P.ROOT / "results" / "tmp" / "phase2a_mimo_mock"
REPORT = P.ROOT / "PHASE2A_MIMO_PILOT_REPORT.md"
ATTEMPT3_SECTION = "ATTEMPT3_SECTION.md"   # written into the out dir; appended to REPORT by hand so the history of attempts 1-2 is kept
FAMILY_PLAN = [("M1_fanout_cancel_resend", 8), ("M2_rotating_batch", 8), ("M3_start_done_alternation", 8), ("F1a_cancel_retry_explain", 8), ("F7_crossturn_history_primed", 6)]
SMOKE_TURNS = 3
XML_MARKERS = ("<tool_call>", "<function=", "<parameter=", "</tool_call>")


# ------------------------------------------------------------------------------------------------ patching of the shared collector for this model / pin
class MimoAssembler(Assembler):
    """Same SSE assembly; additionally keeps OpenRouter `reasoning_details` items (merged when consecutive fragments share type/index/format) so they can be passed back unmodified."""
    def __post_init__(self):
        super().__post_init__()
        self._details: list = []

    def feed(self, chunk):
        for ch in chunk.get("choices", []) or []:
            for it in ((ch.get("delta") or {}).get("reasoning_details") or []):
                self._add_detail(it)
        return super().feed(chunk)

    def _add_detail(self, it):
        if not isinstance(it, dict):
            return
        if self._details:
            last = self._details[-1]
            if all(last.get(k) == it.get(k) for k in ("type", "index", "format")) and isinstance(last.get("text"), str) and isinstance(it.get("text"), str):
                last["text"] += it["text"]
                for k, v in it.items():
                    if k not in ("text",) and v is not None and k not in last:
                        last[k] = v
                return
        self._details.append(dict(it))

    @property
    def reasoning_details_merged(self):
        return self._details


class MimoDisconnectScenario(PP.DisconnectScenario):
    """Disconnect/billing test scenario carrying the same provenance labels (checkpoint unknown)."""
    provenance_extra = {"run_set": RUN_SET, "checkpoint": CHECKPOINT, "model_requested": MODEL_MIMO, "family_stage": "disconnect"}


@contextlib.contextmanager
def configured():
    """Point the shared Phase 2A collector at MiMo + the pinned provider for the duration of the block (module globals it reads at call time), then restore."""
    saved = (P.MODEL, P.PINNED_NAME, P.PROVIDER_PIN, P.Assembler, PP.DISCONNECT_MAX_TOKENS, PP.DISCONNECT_BUDGET_USD, PP.DisconnectScenario)
    PP.DisconnectScenario = MimoDisconnectScenario
    P.MODEL, P.PINNED_NAME, P.PROVIDER_PIN, P.Assembler = MODEL_MIMO, PIN_NAME, PIN, MimoAssembler
    PP.DISCONNECT_MAX_TOKENS, PP.DISCONNECT_BUDGET_USD = 400, 0.01
    try:
        yield
    finally:
        P.MODEL, P.PINNED_NAME, P.PROVIDER_PIN, P.Assembler, PP.DISCONNECT_MAX_TOKENS, PP.DISCONNECT_BUDGET_USD, PP.DisconnectScenario = saved


class PilotGuard(BudgetGuard):
    """BudgetGuard + pilot-specific cap (spend since pilot start <= $0.10) + per-run cap ($0.02). Same worst-case pre-charge logic (price x margin), prices rounded up."""
    def __init__(self, ledger_path, *, live, pilot_start_spent, pilot_cap=PILOT_CAP_USD, run_cap=RUN_CAP_USD, **kw):
        super().__init__(ledger_path, live=live, price_in=GUARD_PRICE_IN, price_out=GUARD_PRICE_OUT, prompt_ceiling=PROMPT_CEILING, **kw)
        self.pilot_start, self.pilot_cap, self.run_cap = pilot_start_spent, pilot_cap, run_cap
        self.last_refusal = None

    def pilot_spent(self) -> float:
        return self.spent() - self.pilot_start

    def run_spent(self, run_id: str) -> float:
        return sum(r.get("usd", 0.0) for r in self.rows() if r.get("run_id") == run_id)

    def check(self, worst_case: float, what: str = "request") -> None:
        ps = self.pilot_spent()
        if ps + worst_case > self.pilot_cap + 1e-12:
            self.last_refusal = {"kind": "pilot_cap", "what": what}
            raise BudgetRefused(f"{what}: pilot spend ${ps:.6f} + worst-case ${worst_case:.6f} > pilot cap ${self.pilot_cap:.2f}")
        m = re.match(r"(?:request|precharge) (\S+?)(?:#\d+.*|-r\d+(?:-a\d+)?)$", what)
        if m:
            rs = self.run_spent(m.group(1))
            if rs > self.run_cap + 1e-12:
                self.last_refusal = {"kind": "run_cap", "what": what, "run_spent": rs}
                raise BudgetRefused(f"{what}: this run's cost ${rs:.6f} exceeds the per-run cap ${self.run_cap:.2f}")
        try:
            super().check(worst_case, what)
        except BudgetRefused:
            self.last_refusal = {"kind": "cumulative_cap", "what": what}
            raise


class MimoCollector(P.Collector):
    def __init__(self, *a, tag="stage", **kw):
        super().__init__(*a, **kw)
        self.tag = tag

    def save(self):
        (self.out / f"stages_{self.tag}.json").write_text(json.dumps(self.stages, indent=1, default=str))


# ------------------------------------------------------------------------------------------------ descriptive recorders (no decisions except the stated stop rules)
def _gens(t):
    return [g for tu in t["turns"] for g in tu["generations"]]


def calls_per_generation(t) -> list[int]:
    return [len(g["tool_calls"]) for g in _gens(t)]


def xml_leaks(t) -> list[dict]:
    out = []
    for i, g in enumerate(_gens(t)):
        for fld in ("content", "reasoning_content"):
            txt = g.get(fld) or ""
            hit = [m for m in XML_MARKERS if m in txt]
            if hit:
                out.append({"gen_index": i, "field": fld, "markers": hit, "generation_had_parsed_calls": len(g["tool_calls"]) > 0, "finish_reason": g.get("finish_reason")})
    return out


def passback_check(t, requests: list[dict]) -> list[dict]:
    """For each consecutive pair of requests in the run: prompt-token growth vs what the previous generation produced. If reasoning is passed back AND counted, growth ~ completion tokens (incl. reasoning) + tool results;
    if it is dropped, growth ~ (completion - reasoning) + tool results. Descriptive; tool-result size is estimated from chars/3.5."""
    rs = sorted([r for r in requests if r.get("run_id") == t["run_id"] and r.get("usage")], key=lambda r: r.get("turn", 0))
    out = []
    for a, b in zip(rs, rs[1:]):
        ua, ub = a["usage"], b["usage"]
        ct, rt = ua.get("completion_tokens") or 0, (ua.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        growth = (ub.get("prompt_tokens") or 0) - (ua.get("prompt_tokens") or 0)
        turn = next((tu for tu in t["turns"] if tu["turn"] == a.get("turn")), None)
        res_chars = 0
        if turn:
            from .phase2a_families import make as _mk  # noqa: F401  (import kept lazy; results are not stored in traces, so approximate from call count)
        n_calls = len(_gens(t)[a.get("turn", 0)]["tool_calls"]) if a.get("turn", 0) < len(_gens(t)) else 0
        est_res = n_calls * 60
        with_rt, without_rt = ct + est_res, max(0, ct - rt) + est_res
        verdict = "n/a (reasoning tokens < 50)" if rt < 50 else ("counted (growth closer to WITH-reasoning)" if abs(growth - with_rt) <= abs(growth - without_rt) else "NOT counted (growth closer to WITHOUT-reasoning)")
        out.append({"run_id": t["run_id"], "turn": a.get("turn"), "prompt_growth": growth, "completion_tokens": ct, "reasoning_tokens": rt, "est_result_tokens": est_res,
                    "expected_growth_with_reasoning": with_rt, "expected_growth_without_reasoning": without_rt, "verdict": verdict})
    return out


def within_turn_duplicate_rate(t) -> list[float]:
    """Xiaomi's exact within-turn repetition metric (N-U)/N per generation with >=2 calls (descriptive only)."""
    r = []
    for g in _gens(t):
        sigs = [CR.signature(c["name"], c["arguments"]) for c in g["tool_calls"]]
        if len(sigs) >= 2:
            r.append(round((len(sigs) - len(set(sigs))) / len(sigs), 3))
    return r


def annotate(col, t) -> dict:
    rec = {"run_id": t["run_id"], "calls_per_generation": calls_per_generation(t), "xml_leaks": xml_leaks(t), "passback": passback_check(t, col.requests),
           "within_turn_duplicate_rate": within_turn_duplicate_rate(t), "quirks": [g.get("quirks") for g in _gens(t)],
           "finish_reasons": [g.get("finish_reason") for g in _gens(t)], "delta_styles": [(g.get("delta_shape") or {}).get("delta_style") for g in _gens(t)],
           "provider_served": t["provenance"].get("provider_served"), "checkpoint": CHECKPOINT,
           "reasoning_details_seen": [(g.get("delta_shape") or {}).get("reasoning_details_seen") for g in _gens(t)]}
    col.append_jsonl("recorders.jsonl", rec)
    return rec


def mk_scenario(family: str, seed: int, max_turns: int, stage: str):
    sc = make_mimo(family, seed)
    sc.max_turns, sc.max_tokens = max_turns, MAX_TOKENS
    sc.provenance_extra = {"run_set": RUN_SET, "checkpoint": CHECKPOINT, "model_requested": MODEL_MIMO, "family_stage": stage, "guard_prices_per_M": [GUARD_PRICE_IN, GUARD_PRICE_OUT],
                           "pilot_cap_usd": PILOT_CAP_USD, "run_cap_usd": RUN_CAP_USD, "seed_sent_to_provider": False}
    return sc


# ------------------------------------------------------------------------------------------------ stages
def run_one(col: MimoCollector, family: str, seed: int, max_turns: int, stage: str) -> dict:
    sc = mk_scenario(family, seed, max_turns, stage)
    tr = col.run_scenario_live(stage, sc)            # raises Anomaly on any stop-and-report condition
    col.reconcile()
    rec = annotate(col, tr)
    for lk in rec["xml_leaks"]:
        if not lk["generation_had_parsed_calls"] and any(m in lk["markers"] for m in ("<tool_call>", "<function=")) and lk["field"] == "content":
            raise Anomaly(f"xml leak that broke parsing in {tr['run_id']}: {lk}")
    return tr


def all_calls_single(t) -> bool:
    cpg = [c for c in calls_per_generation(t) if c > 0]
    return len(cpg) >= 3 and all(c == 1 for c in cpg[:3])


def stage_smoke(col: MimoCollector, seed=7001) -> dict:
    tr = run_one(col, "M2_rotating_batch", seed, SMOKE_TURNS, "smoke")
    cpg = calls_per_generation(tr)
    col.stages["smoke"] = {"run_id": tr["run_id"], "calls_per_generation": cpg, "termination": tr["termination_reason"], "n_calls": tr["stats"]["n_calls"]}
    tool_gens = [c for c in cpg if c > 0]
    if len(tool_gens) >= 3 and all(c == 1 for c in tool_gens[:3]):
        col.stages["premise_failed"] = "first 3 tool-using generations each had exactly 1 call (premise of the pilot fails): STOP"
        raise Anomaly(col.stages["premise_failed"])
    return tr


def repetition_sign(t) -> bool:
    if PP.repetition_sign(t):
        return True
    return any(x > 0 for x in within_turn_duplicate_rate(t))


def stage_families(col: MimoCollector, start_seed=7101) -> dict:
    smoke = [t for t in col.traces if t["stats"]["stage"] == "smoke"]
    used = len(smoke)
    fam_traces = [t for t in col.traces if t["stats"]["stage"] == "pilot"]
    def nq():
        return sum(1 for t in col.traces if t["flood_qualifying_machine"])
    seed = start_seed + len(fam_traces)
    stop = None
    todo = [f for f in FAMILY_PLAN if not any(t["stats"]["mode"] == f[0] for t in fam_traces)]
    for fam, mt in todo:
        if nq() >= 5: stop = "5 flood-qualifying runs"; break
        try:
            run_one(col, fam, seed, mt, "pilot"); seed += 1
        except BudgetRefused as e:
            stop = f"budget guard refused to launch {fam}: {e}"; break
        if col.guard.last_refusal and col.guard.last_refusal["kind"] == "pilot_cap":
            stop = "pilot cap reached"; break
    fam_traces = [t for t in col.traces if t["stats"]["stage"] == "pilot"]
    ext = 0
    while stop is None and used + len(fam_traces) < MAX_RUNS_TOTAL and nq() < 5 and ext < 3:
        signs = {}
        for f, mt in FAMILY_PLAN:
            ts = [t for t in fam_traces if t["stats"]["mode"] == f]
            signs[f] = (sum(1 for t in ts if t["flood_qualifying_machine"]), sum(1 for t in ts if repetition_sign(t)))
        cand = sorted([f for f in FAMILY_PLAN if signs[f[0]][1] > 0], key=lambda f: (-signs[f[0]][0], -signs[f[0]][1]))
        col.stages.setdefault("extension_log", []).append({"signs": signs, "candidates": [c[0] for c in cand]})
        if not cand:
            stop = "no family showed repetition signs: no extension runs"; break
        fam, mt = cand[0]
        try:
            run_one(col, fam, seed, mt, "pilot"); seed += 1; ext += 1
        except BudgetRefused as e:
            stop = f"budget guard refused to launch extension run: {e}"; break
        fam_traces = [t for t in col.traces if t["stats"]["stage"] == "pilot"]
        if col.guard.last_refusal and col.guard.last_refusal["kind"] == "pilot_cap":
            stop = "pilot cap reached"; break
    if stop is None:
        stop = "5 flood-qualifying runs" if nq() >= 5 else (f"{used + len(fam_traces)} runs done (max {MAX_RUNS_TOTAL}); no scaling")
    col.stages["families_stop_reason"] = stop
    return {"stop": stop}


# ------------------------------------------------------------------------------------------------ runner
def pilot_start_spent(out: Path, ledger: Path, live: bool) -> float:
    f = out / "pilot_start.json"
    if f.exists():
        return json.loads(f.read_text())["ledger_spent_at_pilot_start_usd"]
    s = BudgetGuard(ledger, live=live).spent()
    f.write_text(json.dumps({"ledger_spent_at_pilot_start_usd": s, "at": time.strftime("%Y-%m-%d %H:%M:%S %Z")}))
    return s


def key_usage(col: MimoCollector, tries=6, gap=4.0):
    return PP.key_usage_stable(col, tries=tries, gap=gap)


def run_stage(stage: str, *, live: bool, out: Path, ledger: Path, up, retry_attempts: int, retry_wall: float, start_spent: float, sleep=None) -> MimoCollector:
    cfg = P.Config(live, out, ledger, max_tokens=MAX_TOKENS, max_turns=8, retry_max_attempts=retry_attempts, retry_total_wall_s=retry_wall, gen_retries=10 if live else 4,
                   connectivity_max_tokens=64, **({"sleep": sleep} if sleep else {}))
    guard = PilotGuard(ledger, live=live, pilot_start_spent=start_spent)
    col = MimoCollector(cfg, up, guard, tag=stage)
    col.traces = load_jsonl(out / "traces.jsonl")
    col.stages.update(stage=stage, run_set=RUN_SET, model=MODEL_MIMO, provider_pin=PIN, checkpoint=CHECKPOINT, mode="live" if live else "mock", spent_before_stage_usd=guard.spent(),
                      pilot_start_ledger_usd=start_spent, pilot_cap_usd=PILOT_CAP_USD, run_cap_usd=RUN_CAP_USD, guard_prices=[GUARD_PRICE_IN, GUARD_PRICE_OUT], prompt_ceiling=PROMPT_CEILING,
                      criteria_hash=CR.CRITERIA_HASH, started_at=time.strftime("%Y-%m-%d %H:%M:%S %Z"))
    col.stages["key_usage_start_usd"] = key_usage(col, gap=4.0 if live else 0.01)
    try:
        if stage == "connectivity":
            col.stage_connectivity()
            c = col.stages.get("connectivity", {})
            if str(c.get("provider")).lower() != PIN_NAME.lower():
                raise Anomaly(f"connectivity served by {c.get('provider')!r}, not {PIN_NAME}")
        elif stage == "disconnect":
            PP.disconnect_test(col, points=(30, 120), control=True)
        elif stage == "smoke":
            stage_smoke(col)
        elif stage == "families":
            stage_families(col)
        col.reconcile(final=True)
    except (Anomaly, BudgetRefused) as e:
        if isinstance(e, BudgetRefused):
            col.stages["budget_refusal"] = str(e)
        if col.stages.get("anomaly") is None and isinstance(e, Anomaly):
            col.stages["anomaly"] = {"message": up.redact.scrub(str(e))}
        P.log(f"!! STOP: {up.redact.scrub(str(e))}")
        try:
            col.reconcile(final=False)
        except Anomaly:
            pass
    finally:
        col.stages["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
        col.stages["spent_after_stage_usd"] = guard.spent()
        col.stages["pilot_spent_usd"] = guard.pilot_spent()
        col.stages["key_usage_end_usd"] = key_usage(col, gap=4.0 if live else 0.01)
        col.stages["unreconciled_requests"] = [r["gen_id"] for r in col.pending_recon]
        col.save()
    return col


# ------------------------------------------------------------------------------------------------ report
def _fmt(x, nd=6):
    return "n/a" if x is None else (f"{x:.{nd}f}" if isinstance(x, float) else str(x))


def write_mimo_report(out: Path, ledger: Path, *, mock: bool, report_path: Path, start_spent: float, ku_now, avail: dict | None) -> Path:
    traces = load_jsonl(out / "traces.jsonl")
    reqs = load_jsonl(out / "requests.jsonl")
    recs = {r["run_id"]: r for r in load_jsonl(out / "recorders.jsonl")}
    st = {}
    for s in ("connectivity", "disconnect", "smoke", "families"):
        f = out / f"stages_{s}.json"
        if f.exists():
            st[s] = json.loads(f.read_text())
    guard = PilotGuard(ledger, live=not mock, pilot_start_spent=start_spent)
    L = []; A = L.append
    runs = [t for t in traces if t["stats"]["stage"] in ("smoke", "pilot")]
    quals = [t for t in runs if t["flood_qualifying_machine"]]
    A(f"# ATTEMPT 3 - PHASE 2A MiMo-V2.6-Flash PILOT, pinned to Xiaomi first party ({RUN_SET}) - {'MOCK DRY RUN ($0, NOT live data)' if mock else 'LIVE'}\n")
    A(f"**EXPLORATORY-2A only; must NOT be used as untouched confirmatory data for Guard v2.** Model `{MODEL_MIMO}`, provider pinned `{json.dumps(PIN)}` (Xiaomi first party), **checkpoint: {CHECKPOINT}** - "
      "this report does not assert which weights are served (not the historical pre-fix RL checkpoint by assumption, and MOPD is a provider claim, not a verified fact); this is a likely-fixed-model contrast, not a reproduction of the pre-fix failure. Guard v2 OFF; no detector, guard or frozen criterion changed or run "
      f"(flood-qualifying = >= {CR.MIN_CALLS} calls AND distinct ratio <= {CR.MAX_DISTINCT_RATIO}, criteria hash `{CR.CRITERIA_HASH}`; human confirmation by the maintainer). "
      "No rate claims: N is tiny and the result is specific to this provider, these mock-tool prompts and this time window.\n")
    A("## 1. Headline\n")
    anomalies = {s: v.get("anomaly") for s, v in st.items() if v.get("anomaly")}
    A(f"- runs executed (smoke + families + extension): **{len(runs)}** (max {MAX_RUNS_TOTAL}); flood-qualifying runs (machine part of the frozen definition): **{len(quals)}**; runs with >= 30 calls: **{sum(1 for t in runs if t['stats']['n_calls'] >= 30)}**")
    A(f"- pilot spend (ledger, since pilot start): **${guard.pilot_spent():.6f}** (pilot cap ${PILOT_CAP_USD:.2f}); cumulative Phase 2A ledger ${guard.spent():.6f} (was ${start_spent:.6f} before the pilot; hard cap $1.00, effective $0.90)")
    A(f"- stop reason: {st.get('families', {}).get('families_stop_reason', 'families stage not run')}")
    A(f"- anomalies / aborts: {json.dumps(anomalies) if anomalies else 'none'}; 429 retries: {json.dumps({s: v.get('retries') for s, v in st.items() if v.get('retries')}) or 'none'}")
    if not mock and len(quals) < 5:
        A(f"- **P2-B: {len(quals)} < 5 flood-qualifying runs => NULL RESULT** for these conditions (not evidence about the model, the checkpoint, the provider, or the guard).")
    A("")
    A("## 2. Provider availability check (before any spend)\n")
    if avail:
        A(f"- snapshot `{avail['file']}` fetched **{avail['fetched_at']}** (free GET, no key): {PIN_NAME} listed = {avail['listed']}, status = {avail['status']} (0 = OK), tools = {avail['tools']}, tool_choice = {avail['tool_choice']}, reasoning = {avail['reasoning']}, "
          f"uptime 5m/30m/1d = {avail['uptime']}, pricing in/out/cache = {avail['pricing']}; other endpoints listed (not used): {avail['others']}")
    A("- pin verification (stage 1 connectivity): " + (json.dumps({k: st['connectivity']['connectivity'].get(k) for k in ('provider', 'model_returned', 'http_status', 'finish_reason', 'usage')}) if 'connectivity' in st and st['connectivity'].get('connectivity') else 'not run'))
    A("")
    A("## 3. Disconnect / billing findings for Xiaomi (3 requests, max_tokens 400; provider is NOT on OpenRouter's documented cancel list)\n")
    dts = (st.get("disconnect") or {}).get("disconnect_tests") or []
    if dts:
        A("| test | chunks received | est tokens received (chars/4) | /generation tokens_completion (native) | reasoning tokens | /generation cost | cancelled flag | billed / full-400 cost | key-usage delta | verdict (rule: billed <= 1.2 x received + 60 tokens) |\n|---|---|---|---|---|---|---|---|---|---|")
        for o in dts:
            g = o["generation_second_read_after_12s"] or o["generation_first_read"] or {}
            est = o["client"]["est_tokens_received_chars_div_4"]
            tc = g.get("native_tokens_completion") if g.get("native_tokens_completion") is not None else g.get("tokens_completion")
            v = "n/a"
            if o["requested_disconnect_chunks"] and tc is not None and est is not None:
                v = "cancel stops billing (approx.)" if tc <= 1.2 * est + 60 else "billed well beyond received: provider likely ran on after disconnect"
            elif not o["requested_disconnect_chunks"]:
                v = "control (ran to end / max_tokens)"
            A(f"| {o['test']} | {o['client']['chunks_received']} | {est} | {g.get('tokens_completion')} ({g.get('native_tokens_completion')}) | {g.get('native_tokens_reasoning')} | {g.get('total_cost')} | {g.get('cancelled')} | {o.get('billed_fraction_of_full')} | {o.get('key_usage_delta')} | {v} |")
        A("\nCaveats: chars/4 is a rough token estimate for reasoning text; the key-usage counter lags; `/generation` `cancelled` was False for client aborts on Darkbloom too and is not proof either way. UNVERIFIED beyond these 3 requests.\n")
    else:
        A("not run.\n")
    A("## 4. Calls per generation (parallel-call evidence)\n")
    allg = [c for t in runs for c in calls_per_generation(t)]
    tool_g = [c for c in allg if c > 0]
    A(f"- generations in the {len(runs)} runs: {len(allg)}; with >=1 tool call: {len(tool_g)}; distribution of calls per generation (all): {dict(sorted(Counter(allg).items()))}")
    A(f"- generations with >= 2 calls: {sum(1 for c in tool_g if c >= 2)} of {len(tool_g)}; max calls in one generation: {max(tool_g, default=0)}; median (tool-using): {statistics.median(tool_g) if tool_g else 'n/a'}")
    styles = Counter(s for r in recs.values() for s in r["delta_styles"])
    A(f"- delta styles: {dict(styles)}; finish reasons: {dict(Counter(f for r in recs.values() for f in r['finish_reasons']))}; id/index collisions or duplicate ids (quirks): "
      f"{sum(1 for r in recs.values() for q in r['quirks'] if q and (q.get('duplicate_ids') or q.get('missing_ids')))} generations; xml leaks recorded: {sum(len(r['xml_leaks']) for r in recs.values())}; within-turn duplicate rates (N-U)/N for generations with >= 2 calls: "
      f"{[x for r in recs.values() for x in r['within_turn_duplicate_rate']]}")
    A("")
    A("## 5. Reasoning pass-back check\n")
    pb = [p for r in recs.values() for p in r["passback"]]
    A(f"- reasoning (and OpenRouter `reasoning_details`, when streamed) is passed back verbatim on the assistant message. reasoning_details seen in the stream: {sum(1 for r in recs.values() for x in r['reasoning_details_seen'] if x)} generations.")
    A(f"- verdicts over {len(pb)} consecutive-request pairs: {dict(Counter(p['verdict'] for p in pb))}")
    if pb:
        A("| run | turn | prompt growth | prev completion tok | prev reasoning tok | expected growth WITH reasoning | WITHOUT | verdict |\n|---|---|---|---|---|---|---|---|")
        for p in pb[:24]:
            A(f"| {p['run_id'].split('-', 2)[-1]} | {p['turn']} | {p['prompt_growth']} | {p['completion_tokens']} | {p['reasoning_tokens']} | {p['expected_growth_with_reasoning']} | {p['expected_growth_without_reasoning']} | {p['verdict']} |")
    A("\n(The growth check compares billed prompt tokens with the previous generation's token counts; tool-result size is estimated as 60 tokens/call. Approximate, descriptive, not proof.)\n")
    A("## 6. Per run\n")
    A("| run id | family | stage | generations | calls | calls/generation | distinct | distinct ratio | shape (descriptive) | termination | flood-qualifying | cost usd | latency s |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t in runs:
        sigs = [CR.signature(c["name"], c["arguments"]) for tu in t["turns"] for g in tu["generations"] for c in g["tool_calls"]]
        s = t["stats"]
        A(f"| {t['run_id']} | {s['mode']} | {s['stage']} | {s['n_turns']} | {s['n_calls']} | {calls_per_generation(t)} | {s['n_distinct']} | {s['distinct_ratio']} | {CR.describe_shape(sigs)} | {t['termination_reason']} | {t['flood_qualifying_machine']} | {t['cost_usd']:.6f} | {t['latency_s']} |")
    A("")
    A("## 7. Flood-qualifying runs - HUMAN CONFIRMATION NEEDED (maintainer)\n")
    if not quals:
        A("none.\n")
    for t in quals:
        A(f"### `{t['run_id']}` (split `{t['split']}`, provider {t['provenance'].get('provider_served')}, checkpoint {CHECKPOINT}, human confirmation {t['human_confirmation']})\n```\n{excerpt(t)}\n```\n")
    A("## 8. Spend and reconciliation\n")
    g_sum = sum((r.get("generation") or {}).get("total_cost") or 0 for r in reqs)
    A(f"- ledger (live_call rows): pilot **${guard.pilot_spent():.6f}**, cumulative **${guard.spent():.6f}**")
    A(f"- sum of /generation total_cost over the pilot's {len(reqs)} recorded requests: ${g_sum:.6f}; requests without a retrievable /generation record: {sum(1 for r in reqs if not r.get('generation'))}")
    A(f"- streamed usage.cost vs /generation on non-cancelled requests: ${sum(r.get('usd_settled') or 0 for r in reqs if not r.get('cancelled') and r.get('generation')):.6f} vs ${sum((r.get('generation') or {}).get('total_cost') or 0 for r in reqs if not r.get('cancelled')):.6f}")
    ks = [(s, v.get("key_usage_start_usd"), v.get("key_usage_end_usd")) for s, v in st.items()]
    A("- OpenRouter key-usage counter (GET /api/v1/key, `usage` only; each value read repeatedly until two reads agree): " + "; ".join(f"{s}: {a} -> {b}" for s, a, b in ks) + (f"; final {ku_now}" if ku_now is not None else ""))
    A(f"- provider per request (/generation provider_name): {dict(Counter((r.get('generation') or {}).get('provider_name') for r in reqs if r.get('generation')))}; model per request (/generation): {dict(Counter((r.get('generation') or {}).get('model') for r in reqs if r.get('generation')))}; chunk provider: {dict(Counter(p for t in traces for p in t['provenance'].get('provider_served', [])))}; model returned in chunks: {dict(Counter(r.get('model_returned') for r in reqs))}")
    A(f"- cancelled streams: {sum(1 for r in reqs if r.get('cancelled'))}\n")
    A("## 9. Caveats\n")
    A("- exploratory-2A; checkpoint unknown (provider-claimed); Xiaomi-first-party-specific; mock-tool prompts adapted for batching (families-mimo-v1); the OpenRouter payload did not send `seed` or sampling parameters (provider defaults). N <= 9: no rate claims; a null result is not evidence about the model, the served checkpoint or the guard. Guard v2 was not started.")
    A("- secret scan: (filled by the runner)\n")
    report_path.write_text("\n".join(L))
    return report_path


def fetch_prespend_snapshot() -> Path:
    """Free GET (no Authorization header) of the OpenRouter endpoints list; saved as a new timestamped file in evidence/."""
    import httpx
    t = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    f = P.ROOT / "evidence" / f"openrouter_mimo-v2.6-flash_endpoints_prespend_{PIN_NAME.lower()}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    try:
        r = httpx.get(P.LIVE_ROOT + "/api/v1/models/xiaomi/mimo-v2.6-flash/endpoints", timeout=20.0)
        d = r.json() if r.status_code == 200 else {"data": {"endpoints": []}, "http_status": r.status_code}
    except Exception as e:
        d = {"data": {"endpoints": []}, "error": type(e).__name__}
    f.write_text(json.dumps({"fetched_at": t, "purpose": "immediately-before-spend availability check", "url": P.LIVE_ROOT + "/api/v1/models/xiaomi/mimo-v2.6-flash/endpoints", "auth": "none", "response": d}, indent=1))
    return f


def availability_from_snapshot(path: Path) -> dict | None:
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    e = next((x for x in d["response"]["data"]["endpoints"] if x["provider_name"] == PIN_NAME), None)
    if not e:
        return {"file": (str(path.relative_to(P.ROOT)) if str(path).startswith(str(P.ROOT)) else str(path)), "fetched_at": d["fetched_at"], "listed": False, "status": None, "tools": None, "tool_choice": None, "reasoning": None, "uptime": None, "pricing": None, "others": None}
    sp = e["supported_parameters"]
    return {"file": (str(path.relative_to(P.ROOT)) if str(path).startswith(str(P.ROOT)) else str(path)), "fetched_at": d["fetched_at"], "listed": True, "status": e["status"], "tools": "tools" in sp, "tool_choice": "tool_choice" in sp, "reasoning": "reasoning" in sp,
            "uptime": [round(e["uptime_last_5m"], 1), round(e["uptime_last_30m"], 1), round(e["uptime_last_1d"], 1)],
            "pricing": [e["pricing"]["prompt"], e["pricing"]["completion"], e["pricing"]["input_cache_read"]],
            "others": [f"{x['provider_name']}(status {x['status']})" for x in d["response"]["data"]["endpoints"] if x["provider_name"] != PIN_NAME]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true"); g.add_argument("--live", action="store_true")
    ap.add_argument("--stage", choices=["connectivity", "disconnect", "smoke", "families", "report"], default=None)
    ap.add_argument("--out-dir", default=None); ap.add_argument("--ledger", default=None)
    ap.add_argument("--snapshot", default=None, help="(tests) use this snapshot file instead of fetching; live runs fetch a fresh one (free GET, no key)")
    a = ap.parse_args(argv)
    live = a.live
    if live and not P.preflight_key_present():
        print(f"REFUSING live run: {P.KEY_ENV} is not set in the environment (checked by name only). No request was made.", file=sys.stderr); return 2
    if live and not a.stage:
        print("REFUSING: --live needs an explicit --stage", file=sys.stderr); return 2
    out = Path(a.out_dir) if a.out_dir else (OUT if live else MOCK_OUT)
    ledger = Path(a.ledger) if a.ledger else (P.LIVE_LEDGER if live else out / "spend_ledger.jsonl")
    out.mkdir(parents=True, exist_ok=True)
    if live and not a.snapshot:
        a.snapshot = str(fetch_prespend_snapshot())          # free unauthenticated GET, written to evidence/ with a timestamp, immediately before the first paid request of this stage
    avail = availability_from_snapshot(Path(a.snapshot)) if a.snapshot else None
    if live:
        if not avail or not (avail["listed"] and avail["status"] == 0 and avail["tools"] and avail["tool_choice"]):
            print("REFUSING: pre-spend availability snapshot missing or the pinned provider (Xiaomi) not listed / status != 0 / tools+tool_choice unsupported. Nothing spent.", file=sys.stderr); return 2
    if not live:
        for f in out.glob("*"):
            if f.is_file(): f.unlink()
        if (out / "raw").exists():
            for f in (out / "raw").glob("*"): f.unlink()
        ledger.unlink(missing_ok=True)
    start = pilot_start_spent(out, ledger, live)
    if live and BudgetGuard(ledger, live=True).spent() >= P.EFFECTIVE_CAP_USD:
        print("REFUSING: cumulative cap reached", file=sys.stderr); return 2

    def mk_up(srv=None):
        return P.Upstream(True, P.LIVE_ROOT, key=os.environ[P.KEY_ENV]) if live else P.Upstream(False, srv.url.rsplit("/v1", 1)[0], mock_opts={"provider": PIN_NAME})
    stages = [a.stage] if a.stage else ["connectivity", "disconnect", "smoke", "families"]
    rc = 0
    with configured():
        srv_cm = None
        if not live:
            from .mock_upstream.app import create_app
            from .servers import LocalServer
            srv_cm = LocalServer(create_app()); srv = srv_cm.__enter__()
        try:
            for s in stages:
                if s == "report":
                    continue
                if not live and s == "connectivity":
                    pass
                retry = (8, 1800.0) if s in ("connectivity", "smoke") else (3, 900.0)
                P.log(f"== MiMo pilot stage: {s} ==")
                col = run_stage(s, live=live, out=out, ledger=ledger, up=mk_up(srv if not live else None), retry_attempts=retry[0], retry_wall=retry[1], start_spent=start,
                                sleep=(lambda x: None) if not live else None)
                col.client.close()
                if col.stages.get("anomaly") or col.stages.get("budget_refusal"):
                    rc = 3; P.log(f"stage {s} ended with anomaly/refusal; not continuing"); break
        finally:
            if srv_cm:
                srv_cm.__exit__(None, None, None)
    # report (also after aborts)
    up = P.Upstream(live, P.LIVE_ROOT, key=os.environ[P.KEY_ENV]) if live else P.Upstream(False, "http://127.0.0.1:1")
    ku = None
    if live:
        tmp = P.Collector(P.Config(True, out, ledger), up, BudgetGuard(ledger, live=True))
        ku = PP.key_usage_stable(tmp); tmp.client.close()
    rp = (out / ATTEMPT3_SECTION) if live else out / "PHASE2A_MIMO_PILOT_REPORT.MOCK.md"
    write_mimo_report(out, ledger, mock=not live, report_path=rp, start_spent=start, ku_now=ku, avail=avail)
    scan = P.secret_scan([out, rp] + ([ledger] if live else []), os.environ.get(P.KEY_ENV) if live else None)
    rp.write_text(rp.read_text().replace("(filled by the runner)", scan["text"]))
    print("secret scan:", "CLEAN" if scan["clean"] else "!! FOUND: " + str(scan["hits"]))
    print("report:", rp)
    g = BudgetGuard(ledger, live=live)
    print(f"spent (cumulative): ${g.spent():.6f}; pilot: ${g.spent() - start:.6f}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
