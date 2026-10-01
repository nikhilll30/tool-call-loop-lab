"""Phase 2A F3 follow-up (run set id "f3-followup"): family F3_pagination_backtrack ONLY, prompt + mock tools UNCHANGED, turn cap raised
(default 34; CLI parameter for this follow-up only), <= 10 runs, follow-up budget $0.05, pinned provider Darkbloom, cumulative caps unchanged.

    python -m floodlab.phase2a_f3_followup --mock      # $0 dry run against the loopback mock
    python -m floodlab.phase2a_f3_followup --live      # live (needs OPENROUTER_API_KEY)
A run stops (stream cancelled) as soon as it is flood-qualifying by the FROZEN definition; a run whose model exits normally / hits the turn cap
ends there. No prompt/detector/guard/criteria change. Guard v2 OFF.
"""
from __future__ import annotations
import argparse, json, os, statistics, sys, time
from collections import Counter
from pathlib import Path
from . import criteria as CR
from .budget import Anomaly, BudgetGuard, BudgetRefused
from .canon import canonical_json
from .phase2a import (DEFAULT_RETRY_ATTEMPTS, DEFAULT_RETRY_WALL_S, DEFAULT_RETRY_BASE_S, DEFAULT_RETRY_CAP_S, DEFAULT_RETRY_GLOBAL_WALL_S,
                      Collector, Config, Upstream, KEY_ENV, LIVE_ROOT, LIVE_LEDGER, LIVE_OUT, MODEL, PINNED_NAME, PROVIDER_PIN, ROOT,
                      log, preflight_key_present, secret_scan)
from .phase2a_common import load_jsonl
from .phase2a_families import make
from .phase2a_pilot import key_usage_stable
from .phase2a_report import excerpt

RUN_SET = "f3-followup"
FAMILY = "F3_pagination_backtrack"
OUT = LIVE_OUT / "f3_followup"
MOCK_OUT = ROOT / "results" / "tmp" / "phase2a_f3_followup_mock"
DEFAULT_TURN_CAP = 34
MAX_RUNS = 10
FOLLOWUP_BUDGET_USD = 0.05
FOLLOWUP_PROMPT_CEILING = 8000       # tokens; F3 prompts stay far below this even at 34 turns (~4-5k); per-request estimates still use the real prompt


def make_scenario(seed: int, turn_cap: int):
    sc = make(FAMILY, seed)
    sc.max_turns = turn_cap                       # the ONLY change vs the pilot
    sc.provenance_extra = {"run_set": RUN_SET, "turn_cap": turn_cap, "turn_cap_pilot": 12, "family_prompt_changed": False}
    return sc


def cycle_analysis(sigs: list[str]) -> dict:
    """Descriptive: does the sequence follow the period-4 page cycle 1,2,3,4,1,2,...? where does it first deviate?"""
    pages = []
    for s in sigs:
        try:
            pages.append(json.loads(s.split("|", 1)[1]).get("page"))
        except Exception:
            pages.append(None)
    expected = [(i % 4) + 1 for i in range(len(pages))]
    dev = next((i for i, (a, b) in enumerate(zip(pages, expected)) if a != b), None)
    return {"pages": pages, "stable_through": len(pages) if dev is None else dev, "first_deviation_index": dev,
            "full_cycles": (len(pages) if dev is None else dev) // 4}


def run_followup(col: Collector, n_runs=MAX_RUNS, turn_cap=DEFAULT_TURN_CAP, min_runs=5, stop_at_floods=5, budget=FOLLOWUP_BUDGET_USD) -> dict:
    start = col.guard.spent()
    col.stages.update(run_set=RUN_SET, turn_cap=turn_cap, followup_budget_usd=budget, spent_before_usd=start, n_runs_max=min(n_runs, MAX_RUNS))
    done = []
    for i in range(min(n_runs, MAX_RUNS)):
        if col.guard.spent() - start > budget:
            col.stages["followup_stop_reason"] = "follow-up budget reached"; break
        sc = make_scenario(6001 + i, turn_cap)
        try:
            tr = col.run_scenario_live("f3fu", sc)      # launch check: spent + worst-case whole run must fit the follow-up cap; per-request pre-charge inside
        except BudgetRefused as e:
            col.stages["followup_stop_reason"] = f"budget guard refused to launch run {i + 1}: {e}"; break
        col.reconcile()
        done.append(tr)
        if tr["termination_reason"] == "budget_guard":
            col.stages["followup_stop_reason"] = "budget guard refused a request (follow-up cap)"; break
        nq = sum(1 for t in done if t["flood_qualifying_machine"])
        if len(done) >= min_runs and nq >= stop_at_floods:
            col.stages["followup_stop_reason"] = f"enough evidence: >= {stop_at_floods} flood-qualifying runs after {len(done)} runs"; break
    col.stages.setdefault("followup_stop_reason", f"{len(done)} runs done (cap {min(n_runs, MAX_RUNS)}); no scaling")
    col.reconcile(final=True)
    return {"runs": len(done)}


def _calls(t):
    return [c for tu in t["turns"] for g in tu["generations"] for c in g["tool_calls"]]


def _text_at(t, call_index: int):
    """(turn index, content, reasoning tail) of the generation that issued call `call_index` (or the final generation)."""
    n = 0
    for tu in t["turns"]:
        for g in tu["generations"]:
            k = len(g["tool_calls"])
            if n <= call_index < n + max(k, 1):
                return tu["turn"], g.get("content") or "", g.get("reasoning_content") or ""
            n += k
    return None, "", ""


def write_followup_report(out_dir: Path, ledger_path: Path, *, mock: bool, report_path: Path, stages: dict, ku_now, pilot_traces: list[dict]) -> Path:
    traces = load_jsonl(out_dir / "traces.jsonl")
    reqs = load_jsonl(out_dir / "requests.jsonl")
    guard = BudgetGuard(ledger_path, live=not mock)
    L = []; A = L.append
    quals = [t for t in traces if t["flood_qualifying_machine"]]
    n30 = [t for t in traces if t["stats"]["n_calls"] >= 30]
    A(f"# PHASE 2A F3 FOLLOW-UP REPORT ({RUN_SET}) - {'MOCK DRY RUN ($0, NOT live data)' if mock else 'LIVE'}\n")
    A(f"**EXPLORATORY: must NOT be used as untouched confirmatory data for Guard v2.** Results are **{PINNED_NAME}'s** (model `openai/gpt-oss-20b`, fp8, pin `{json.dumps(PROVIDER_PIN)}`), "
      "provider-specific; no rate claims. Family F3 only, prompt and mock tools UNCHANGED vs the pilot; only the turn cap was raised. Guard v2 OFF; no detector, guard or frozen criterion changed or run "
      f"(flood-qualifying = >= {CR.MIN_CALLS} calls AND distinct-call ratio <= {CR.MAX_DISTINCT_RATIO}, criteria hash `{CR.CRITERIA_HASH}`; human confirmation by the maintainer).\n")
    A("## 1. Headline answers\n")
    A(f"- runs: **{len(traces)}** (cap {MAX_RUNS}); turn cap {stages.get('turn_cap')} (pilot: 12); tool-call cap 120; max_tokens/request 4000 (as pilot); stop reason: {stages.get('followup_stop_reason')}")
    A(f"- **runs that reached 30+ tool calls: {len(n30)} of {len(traces)}**; flood-qualifying by the frozen definition (>=30 calls AND ratio <= 0.35): **{len(quals)}**")
    A(f"- **total cost of this follow-up: ${guard.spent() - stages.get('spent_before_usd', 0.0):.6f}**; cumulative ${guard.spent():.6f} (before: ${stages.get('spent_before_usd', 0.0):.6f}; follow-up budget ${FOLLOWUP_BUDGET_USD:.2f}; hard cap $1.00, effective $0.90)")
    stable_all = [cycle_analysis([CR.signature(c['name'], c['arguments']) for c in _calls(t)]) for t in traces]
    A(f"- **did the 1->2->3->4 cycle stay stable?** {sum(1 for a in stable_all if a['first_deviation_index'] is None and a['pages'])} of {len(traces)} runs followed the exact 1,2,3,4,1,2,3,4,... sequence for their whole length; "
      f"{sum(1 for a in stable_all if a['first_deviation_index'] is not None)} deviated at some point (details per run below)")
    A(f"- anomaly / early stop: {json.dumps(stages.get('anomaly')) if stages.get('anomaly') else 'none'}; 429 retries: {json.dumps(stages.get('retries')) if stages.get('retries') else 'none'}\n")
    A("## 2. Per run\n")
    A("| run id | seed | generations | calls | distinct | distinct ratio | pages 1,2,3,4 cycle stable through call # | full cycles | first deviation (call #) | shape (descriptive) | termination | 30+ calls | flood-qualifying | cost usd | latency s |\n|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t, a in zip(traces, stable_all):
        sigs = [CR.signature(c["name"], c["arguments"]) for c in _calls(t)]
        s = t["stats"]
        A(f"| {t['run_id']} | {t['provenance']['seed']} | {s['n_turns']} | {s['n_calls']} | {s['n_distinct']} | {s['distinct_ratio']} | {a['stable_through']} | {a['full_cycles']} | "
          f"{a['first_deviation_index'] if a['first_deviation_index'] is not None else '-'} | {CR.describe_shape(sigs)} | {t['termination_reason']} | {s['n_calls'] >= 30} | {t['flood_qualifying_machine']} | {t['cost_usd']:.6f} | {t['latency_s']} |")
    A("")
    A("## 3. Flood-qualifying runs - HUMAN CONFIRMATION NEEDED (maintainer)\n")
    if not quals:
        A("none.\n")
    for t in quals:
        A(f"### `{t['run_id']}` (split `{t['split']}`, provider {t['provenance'].get('provider_served')}, human confirmation {t['human_confirmation']})\n```\n{excerpt(t)}\n```\n")
    A("## 4. Where and how the cycle broke (descriptive)\n")
    from .phase2a_families import PaginationBacktrackEnv
    any_break = False
    for t, a in zip(traces, stable_all):
        calls = _calls(t)
        if a["first_deviation_index"] is None:
            end = t["termination_reason"]
            A(f"- `{t['run_id']}`: cycle never deviated over {len(calls)} calls; ended by `{end}`" + (" (stream cancelled at the frozen threshold)" if t["flood_qualifying_machine"] else "") + ".")
            if end.startswith(("completed", "max_turns")) or end.startswith("no_calls"):
                tn, content, reasoning = _text_at(t, len(calls))
                A(f"  - final generation text: {content[:400]!r}")
            continue
        any_break = True
        d = a["first_deviation_index"]
        env = PaginationBacktrackEnv(FAMILY, "", 0)
        prev = calls[d - 1] if d else None
        res_prev = env.execute(prev["name"], json.loads(prev["arguments"])) if prev else None
        tn, content, reasoning = _text_at(t, d)
        got = a["pages"][d]
        A(f"- `{t['run_id']}`: broke at call #{d} after {a['full_cycles']} full cycle(s): expected page {(d % 4) + 1}, model called page {got}. Tool result just before (page {a['pages'][d - 1] if d else None}): `{res_prev}`.")
        A(f"  - model text at that generation (turn {tn}): content {content[:400]!r}; reasoning tail {reasoning[-500:]!r}")
        A(f"  - continued afterwards: pages {a['pages'][d:d + 12]}; termination `{t['termination_reason']}`")
    if not any_break:
        A("- no run deviated from the 1,2,3,4 cycle.")
    A("")
    A("## 5. Comparison with the pilot's F3 runs (Darkbloom, turn cap 12)\n")
    pf = [t for t in pilot_traces if t["stats"]["mode"] == FAMILY and t["stats"]["stage"] == "pilot"]
    A("| run | calls | generations | distinct ratio | termination | pages |\n|---|---|---|---|---|---|")
    for t in pf:
        a = cycle_analysis([CR.signature(c["name"], c["arguments"]) for c in _calls(t)])
        A(f"| pilot {t['run_id'].rsplit('-', 1)[-1]} | {t['stats']['n_calls']} | {t['stats']['n_turns']} | {t['stats']['distinct_ratio']} | {t['termination_reason']} | {''.join(str(x) for x in a['pages'])} |")
    for t in traces:
        a = cycle_analysis([CR.signature(c["name"], c["arguments"]) for c in _calls(t)])
        A(f"| follow-up {t['run_id'].rsplit('-', 1)[-1]} | {t['stats']['n_calls']} | {t['stats']['n_turns']} | {t['stats']['distinct_ratio']} | {t['termination_reason']} | {''.join(str(x) for x in a['pages'])} |")
    A("")
    A("## 6. Spend and reconciliation\n")
    g_sum = sum((r.get("generation") or {}).get("total_cost") or 0 for r in reqs)
    A(f"- ledger (live_call rows): follow-up **${guard.spent() - stages.get('spent_before_usd', 0.0):.6f}**, cumulative **${guard.spent():.6f}**")
    A(f"- sum of /generation total_cost over this follow-up's {len(reqs)} requests: ${g_sum:.6f}; requests without a retrievable /generation record: {sum(1 for r in reqs if not r.get('generation'))}")
    A(f"- streamed usage.cost vs /generation on non-cancelled requests: ${sum(r.get('usd_settled') or 0 for r in reqs if not r.get('cancelled') and r.get('generation')):.6f} vs ${sum((r.get('generation') or {}).get('total_cost') or 0 for r in reqs if not r.get('cancelled')):.6f}")
    A(f"- OpenRouter key-usage counter (GET /api/v1/key, `usage` only): start ${stages.get('key_usage_start_usd')} -> end (stable, re-read after a wait) ${ku_now}" + (f"; delta ${ku_now - stages['key_usage_start_usd']:.6f}" if ku_now is not None and stages.get('key_usage_start_usd') is not None else ""))
    A(f"- cancelled streams (flood-qualifying cancels etc.): {sum(1 for r in reqs if r.get('cancelled'))}; their billed tokens (from /generation) are in requests.jsonl\n")
    A("## 7. Observations, anomalies, caveats\n")
    shapes = [r["shape"] for r in reqs if r.get("shape")]
    A(f"- calls per generation: {dict(Counter(len(g['tool_calls']) for t in traces for tu in t['turns'] for g in tu['generations']))} (the model issues at most ONE tool call per generation on Darkbloom; a 30-call run therefore needs >= 30 turns)")
    if shapes:
        A(f"- delta style {dict(Counter(s['delta_style'] for s in shapes))}; reasoning fields {dict(Counter(f for s in shapes for f in s['reasoning_fields_seen']))}; provider served {dict(Counter(p for t in traces for p in t['provenance'].get('provider_served', [])))}; /generation provider_name {dict(Counter((r.get('generation') or {}).get('provider_name') for r in reqs if r.get('generation')))}")
    A(f"- latency per request (s): {statistics.median([r['latency_s'] for r in reqs]) if reqs else 'n/a'} median; per run (s): {[t['latency_s'] for t in traces]}")
    A("- caveats: exploratory-2A, Darkbloom-specific (fp8) and mock-tool-specific; N <= 10, so **no rate claims** and no statement about other models/providers; the pilot's F3 prompt/tools were unchanged; "
      "one call per generation; the human confirmation of any qualifying run is pending (maintainer). Not confirmatory data for Guard v2; Guard v2 was not started.")
    A("- secret scan: (filled by the runner)\n")
    report_path.write_text("\n".join(L))
    return report_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true"); g.add_argument("--live", action="store_true")
    ap.add_argument("--turn-cap", type=int, default=DEFAULT_TURN_CAP); ap.add_argument("--runs", type=int, default=MAX_RUNS)
    ap.add_argument("--min-runs", type=int, default=5); ap.add_argument("--budget-usd", type=float, default=FOLLOWUP_BUDGET_USD)
    ap.add_argument("--out-dir", default=None); ap.add_argument("--ledger", default=None); ap.add_argument("--report", default=None)
    ap.add_argument("--retry-attempts", type=int, default=DEFAULT_RETRY_ATTEMPTS); ap.add_argument("--retry-wall-s", type=float, default=DEFAULT_RETRY_WALL_S)
    ap.add_argument("--retry-base-s", type=float, default=DEFAULT_RETRY_BASE_S); ap.add_argument("--retry-cap-s", type=float, default=DEFAULT_RETRY_CAP_S)
    a = ap.parse_args(argv)
    if a.turn_cap < 30 or a.turn_cap > 40:
        print("REFUSING: turn cap must be 30..40 for this follow-up (just enough to test the 30-call threshold)", file=sys.stderr); return 2
    if a.runs > MAX_RUNS or a.budget_usd > FOLLOWUP_BUDGET_USD + 1e-12:
        print(f"REFUSING: at most {MAX_RUNS} runs and ${FOLLOWUP_BUDGET_USD} budget for this follow-up", file=sys.stderr); return 2
    live = a.live
    if live and not preflight_key_present():
        print(f"REFUSING live run: {KEY_ENV} is not set in the environment (checked by name only). No request was made.", file=sys.stderr); return 2
    out = Path(a.out_dir) if a.out_dir else (OUT if live else MOCK_OUT)
    ledger = Path(a.ledger) if a.ledger else (LIVE_LEDGER if live else out / "spend_ledger.jsonl")
    out.mkdir(parents=True, exist_ok=True)
    start = BudgetGuard(ledger, live=live).spent()
    cap = min(0.90, start + a.budget_usd)                 # follow-up cap enforced by the same guard; never above the effective cap
    guard = BudgetGuard(ledger, live=live, cap=cap, prompt_ceiling=FOLLOWUP_PROMPT_CEILING)
    cfg = Config(live, out, ledger, max_tokens=4000, max_turns=a.turn_cap, retry_max_attempts=a.retry_attempts, retry_total_wall_s=a.retry_wall_s,
                 retry_base_s=a.retry_base_s, retry_cap_s=a.retry_cap_s, retry_global_wall_s=DEFAULT_RETRY_GLOBAL_WALL_S, gen_retries=10 if live else 4)
    pilot_traces = load_jsonl(LIVE_OUT / "pilot_darkbloom" / "traces.jsonl") if live else []

    def go(up):
        col = Collector(cfg, up, guard)
        col.stages.update(mode="live" if live else "mock", model=MODEL, provider_pin=PROVIDER_PIN, started_at=time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                          caps={"max_tokens_per_request": 4000, "max_turns": a.turn_cap, "max_calls": 120})
        col.stages["key_usage_start_usd"] = col.fetch_key_usage()
        try:
            run_followup(col, a.runs, a.turn_cap, a.min_runs, budget=a.budget_usd)
        except (Anomaly, BudgetRefused) as e:
            col.stages["anomaly"] = {"message": up.redact.scrub(str(e))}
            log(f"!! STOP: {up.redact.scrub(str(e))}")
            try:
                col.reconcile(final=False)
            except Anomaly:
                pass
        finally:
            col.stages["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S %Z")
            col.stages["spent_after_usd"] = guard.spent()
            col.save()
        return col

    if live:
        col = go(Upstream(True, LIVE_ROOT, key=os.environ[KEY_ENV]))
        time.sleep(45)                                  # let the key-usage counter catch up (it lags ~1 request/test)
        ku_now = key_usage_stable(col, tries=8, gap=8.0)
        col.client.close()
    else:
        from .mock_upstream.app import create_app
        from .servers import LocalServer
        for f in ("traces.jsonl", "requests.jsonl", "stages.json"):
            (out / f).unlink(missing_ok=True)
        ledger.unlink(missing_ok=True)
        with LocalServer(create_app()) as srv:
            col = go(Upstream(False, srv.url.rsplit("/v1", 1)[0]))
        ku_now = None
    rp = Path(a.report) if a.report else ((ROOT / "PHASE2A_F3_FOLLOWUP_REPORT.md") if live else out / "PHASE2A_F3_FOLLOWUP_REPORT.MOCK.md")
    write_followup_report(out, ledger, mock=not live, report_path=rp, stages=col.stages, ku_now=ku_now, pilot_traces=pilot_traces)
    scan = secret_scan([out, rp] + ([ledger] if live else []), os.environ.get(KEY_ENV) if live else None)
    rp.write_text(rp.read_text().replace("(filled by the runner)", scan["text"]))
    print("secret scan:", "CLEAN" if scan["clean"] else "!! FOUND: " + str(scan["hits"]))
    print("report:", rp); print(f"spent (cumulative): ${guard.spent():.6f}")
    return 3 if col.stages.get("anomaly") else 0


if __name__ == "__main__":
    raise SystemExit(main())
