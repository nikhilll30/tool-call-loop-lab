"""Phase 2A continuation: (1) early-disconnect billing test, (3) small pilot over the redesigned prompt families, (4) PHASE2A_PILOT_REPORT.md.

    python -m floodlab.phase2a_pilot --mock                 # whole flow against the loopback mock ($0) -> results/tmp/phase2a_pilot_mock/
    python -m floodlab.phase2a_pilot --live --disconnect    # live step 1 only
    python -m floodlab.phase2a_pilot --live --pilot         # live step 3 only
    python -m floodlab.phase2a_pilot --live                 # both (disconnect test first)
Same guard, ledger, pin, redaction and flood-qualifying cancel as floodlab.phase2a. No detector / guard logic is run. Never scales beyond the pilot.
"""
from __future__ import annotations
import argparse, json, os, statistics, sys, time
from collections import Counter
from pathlib import Path
from . import criteria as CR
from .budget import Anomaly, BudgetGuard, BudgetRefused, EFFECTIVE_CAP_USD, HARD_CAP_USD
from .phase2a import (DEFAULT_RETRY_ATTEMPTS, DEFAULT_RETRY_WALL_S, DEFAULT_RETRY_BASE_S, DEFAULT_RETRY_CAP_S, DEFAULT_RETRY_GLOBAL_WALL_S,
                      Collector, Config, Upstream, KEY_ENV, LIVE_ROOT, LIVE_LEDGER, LIVE_OUT, MODEL, PINNED_NAME, PROVIDER_PIN, ROOT,
                      log, preflight_key_present, secret_scan)
from .phase2a_common import load_jsonl
from .phase2a_families import FAMILIES, DisconnectScenario, make
from .phase2a_report import excerpt

PILOT_OUT = LIVE_OUT / "pilot_darkbloom"        # Darkbloom-pinned continuation; earlier DeepInfra data (data/exploratory_2A/*, pilot/) untouched
HISTORY_DOC = ROOT / "docs" / "PHASE2A_DEEPINFRA_BLOCKED_HISTORY.md"
MOCK_OUT = ROOT / "results" / "tmp" / "phase2a_pilot_mock"
DISCONNECT_POINTS = (30, 120, 400)          # chunks received before closing the stream
DISCONNECT_MAX_TOKENS = 2000
DISCONNECT_BUDGET_USD = 0.05


def key_usage_stable(col: Collector, tries=6, gap=4.0) -> float | None:
    """GET /api/v1/key `usage` (free); re-read until two consecutive reads agree (allows for counter lag)."""
    prev = None
    for _ in range(tries):
        cur = col.fetch_key_usage()
        if cur is not None and prev is not None and abs(cur - prev) < 1e-12:
            return cur
        prev = cur
        time.sleep(gap if col.up.live else 0.01)
    return prev


def disconnect_test(col: Collector, points=DISCONNECT_POINTS, control=True) -> list[dict]:
    """Step 1. Streamed long-output request; close the stream after N chunks; compare with /generation and the key-usage counter."""
    obs_all: list[dict] = []
    col.stages["disconnect_tests"] = obs_all
    start_spent = col.guard.spent()
    plan = [(n, i) for i, n in enumerate(points)] + ([(None, len(points))] if control else [])
    for n, i in plan:
        if col.guard.spent() - start_spent > DISCONNECT_BUDGET_USD:
            log("disconnect test budget reached; stopping this step"); break
        sc = DisconnectScenario(seed=4000 + i, max_tokens=DISCONNECT_MAX_TOKENS)
        ku0 = key_usage_stable(col)
        before = len(col.requests)
        t_req = time.time()
        tr = col.run_scenario_live("disconnect", sc, cancel_after_chunks=n)
        rr = col.requests[before]
        gid = rr["gen_id"]
        # /generation may lag: fetch with retries, then re-read after a wait to see whether the record keeps growing (= provider still generating/billing)
        g1 = col.fetch_generation(gid, retries=10) if gid else None
        t1 = time.time()
        time.sleep(12 if col.up.live else 0.05)
        g2 = col.fetch_generation(gid, retries=3) if gid else None
        ku1 = key_usage_stable(col)
        col.reconcile(final=True)
        gen = tr["turns"][0]["generations"][0]
        stop = gen.get("stop") or {}
        usage = rr.get("usage") or {}
        pt = (g2 or g1 or {}).get("tokens_prompt") or 0
        full_cost_est = col.guard.cost(pt, DISCONNECT_MAX_TOKENS)
        o = {"test": "disconnect_after_%s_chunks" % n if n else "control_full_generation", "run_id": tr["run_id"], "gen_id": gid,
             "requested_disconnect_chunks": n, "max_tokens": DISCONNECT_MAX_TOKENS,
             "client": {"chunks_received": rr.get("chunks"), "chars_received": rr.get("chars_received"), "est_tokens_received_chars_div_4": rr.get("est_tokens_received"),
                        "reasoning_chars": len(gen.get("reasoning_content") or ""), "content_chars": len(gen.get("content") or ""),
                        "cancelled": rr.get("cancelled"), "termination_reason": tr["termination_reason"], "stop_record": stop,
                        "finish_reason_seen_by_client": rr.get("finish_reason"), "streamed_usage": usage or None, "error": None},
             "generation_first_read": _g(g1), "generation_second_read_after_12s": _g(g2),
             "generation_record_grew_between_reads": (g1 and g2 and (g2.get("tokens_completion") != g1.get("tokens_completion") or g2.get("total_cost") != g1.get("total_cost"))),
             "generation_lag_note": "record available on first read" if g1 else "record NOT available after retries",
             "key_usage_before": ku0, "key_usage_after_stable": ku1, "key_usage_delta": (ku1 - ku0) if (ku0 is not None and ku1 is not None) else None,
             "cost_of_full_max_tokens_generation_estimate_usd": round(full_cost_est, 8),
             "billed_fraction_of_full": (round((g2 or g1)["total_cost"] / full_cost_est, 4) if (g2 or g1) and full_cost_est else None)}
        obs_all.append(o)
        col.stages["disconnect_tests"] = obs_all
        col.save()
        log(f"[disconnect {n}] chunks={o['client']['chunks_received']} est_tok={o['client']['est_tokens_received_chars_div_4']} gen_tokens={o['generation_second_read_after_12s'].get('tokens_completion')} "
            f"cost={o['generation_second_read_after_12s'].get('total_cost')} key_delta={o['key_usage_delta']} spent=${col.guard.spent():.6f}")
    return obs_all


def _g(g):
    if not g:
        return {}
    return {k: g.get(k) for k in ("cancelled", "tokens_prompt", "tokens_completion", "native_tokens_prompt", "native_tokens_completion", "native_tokens_reasoning",
                                  "total_cost", "provider_name", "finish_reason", "streamed", "latency", "generation_time")}


def repetition_sign(t: dict) -> bool:
    s = t["stats"]
    return bool(t["flood_qualifying_machine"] or (s["n_calls"] >= 10 and s["distinct_ratio"] is not None and s["distinct_ratio"] <= 0.6))


def pilot(col: Collector, families=None, n_initial=3, n_max=5, stop_at_floods=5) -> dict:
    """Step 3. 3 runs per family; extend to at most 5 only for families showing repetition signs. Never scales beyond this."""
    families = families or list(FAMILIES)
    counts = {f: 0 for f in families}
    seed = [5000]

    def one(f):
        counts[f] += 1; seed[0] += 1
        tr = col.run_scenario_live("pilot", make(f, seed[0]))
        col.reconcile()
        return tr

    def quals():
        return sum(1 for t in col.traces if t["stats"]["stage"] == "pilot" and t["flood_qualifying_machine"])
    for _ in range(n_initial):
        for f in families:
            one(f)
            if quals() >= stop_at_floods:
                break
        if quals() >= stop_at_floods:
            break
    extended = {}
    if quals() < stop_at_floods:
        for f in families:
            ts = [t for t in col.traces if t["stats"]["mode"] == f and t["stats"]["stage"] == "pilot"]
            if any(repetition_sign(t) for t in ts):
                extended[f] = 0
                while counts[f] < n_max and quals() < stop_at_floods:
                    one(f); extended[f] += 1
    stop = ("enough evidence: >= %d flood-qualifying runs" % stop_at_floods) if quals() >= stop_at_floods else \
        ("all families run at N=%d; extended to <=%d only for families with repetition signs: %s; no further runs (pilot only, no escalation)" % (n_initial, n_max, sorted(extended) or "none"))
    col.stages["pilot_stop_reason"] = stop
    col.stages["pilot_extended"] = extended
    col.stages["pilot_counts"] = counts
    col.reconcile(final=True)
    return {"stop": stop, "counts": counts, "extended": extended}


# ------------------------------------------------------------------------------------------------ report
def _stat(xs, fmt="{:.2f}"):
    xs = [x for x in xs if x is not None]
    return "n/a" if not xs else f"{fmt.format(statistics.mean(xs))} ({fmt.format(min(xs))}-{fmt.format(max(xs))})"


def _calls(t):
    return [c for tu in t["turns"] for g in tu["generations"] for c in g["tool_calls"]]


def write_pilot_report(out_dir: Path, ledger_path: Path, *, mock: bool, report_path: Path, base_traces: list[dict], stages: dict, ku_now: float | None) -> Path:
    traces = load_jsonl(out_dir / "traces.jsonl")
    reqs = load_jsonl(out_dir / "requests.jsonl")
    pil = [t for t in traces if t["stats"]["stage"] == "pilot"]
    guard = BudgetGuard(ledger_path, live=not mock)
    L = []; A = L.append
    A(f"# PHASE 2A PILOT REPORT - {'MOCK DRY RUN ($0, not live data)' if mock else 'LIVE PILOT'}\n")
    A(f"**EXPLORATORY: must NOT be used as untouched confirmatory data for Guard v2.** Model `openai/gpt-oss-20b`, provider pinned to {PINNED_NAME} "
      "(`allow_fallbacks:false`), no BYOK, no model/provider change. Guard v2 OFF; no detector, guard or frozen criterion was changed or run "
      f"(flood-qualifying = >= {CR.MIN_CALLS} calls AND distinct-call ratio <= {CR.MAX_DISTINCT_RATIO}, criteria hash `{CR.CRITERIA_HASH}`, human confirmation by the maintainer).\n")
    # ---------------- 1 summary / spend
    spent_all = guard.spent()
    start = stages.get("spent_before_usd", 0.0)
    A(f"## 0. Provider (all results below are **{PINNED_NAME}'s**, model `openai/gpt-oss-20b`, fp8; NOT DeepInfra's and not general)\n")
    A("- chosen and why: see `docs/PHASE2A_PROVIDER_CHOICE.md` (cheapest endpoint excluding DeepInfra with tools + tool_choice, status OK, uptime 99.5%/99.85%); runner-up for the record only (NOT used): **AkashML**. Endpoint snapshot: `evidence/openrouter_gpt-oss-20b_endpoints.json`.")
    A("- pin: `" + json.dumps(PROVIDER_PIN) + "`; no automatic failover; every stream chunk's `provider` and every `/generation` `provider_name` is checked against the pin (mismatch = stop).")
    A(f"- providers actually returned (chunks): {dict(Counter(p for t in traces for p in t['provenance'].get('provider_served', [])))}; /generation provider_name: {dict(Counter((r.get('generation') or {}).get('provider_name') for r in reqs if r.get('generation')))}\n")
    A("## 1. Spend\n")
    A(f"- cumulative spend (ledger sum, live_call rows): **${spent_all:.6f}** (hard cap ${HARD_CAP_USD:.2f}, effective ${guard.cap:.2f}); this continuation: **${spent_all - start:.6f}** (before: ${start:.6f})")
    if ku_now is not None:
        A(f"- OpenRouter key usage counter now (`GET /api/v1/key`, `usage` only): ${ku_now:.6f} (counter at start of this continuation ${stages.get('key_usage_start_usd')}) -> delta ${ku_now - (stages.get('key_usage_start_usd') or 0):.6f}")
    g_sum = sum((r.get("generation") or {}).get("total_cost") or 0 for r in reqs)
    u_sum = sum(r.get("usd_settled") or 0 for r in reqs if (r.get("generation") or {}).get("total_cost") is not None and not r.get("cancelled"))
    g_sum_nc = sum((r.get("generation") or {}).get("total_cost") or 0 for r in reqs if not r.get("cancelled"))
    A(f"- sum of /generation total_cost over this continuation's requests: ${g_sum:.6f} ({len(reqs)} requests); streamed usage.cost vs /generation on non-cancelled requests: ${u_sum:.6f} vs ${g_sum_nc:.6f}")
    rows = [r for r in guard.rows() if r["run_id"].startswith(("p2a-pilot", "p2a-disconnect", "p2a-mock-pilot", "p2a-mock-disconnect"))] if guard.rows() and all("run_id" in r for r in guard.rows()) else []
    byk = Counter()
    for r in rows:
        byk[r["kind"]] += r.get("usd", 0.0)
    A("- ledger rows for this continuation by kind (usd sums): " + ", ".join(f"{k} {v:.6f}" for k, v in byk.items()))
    A(f"- anomaly / early stop: {json.dumps(stages.get('anomaly')) if stages.get('anomaly') else 'none'}\n")
    # ---------------- 2 disconnect
    A("## 2. Early-disconnect test (Step 1)\n")
    dts = stages.get("disconnect_tests") or []
    if not dts:
        A("not run.\n")
    for o in dts:
        c, g1, g2 = o["client"], o["generation_first_read"], o["generation_second_read_after_12s"]
        A(f"### {o['test']} (`{o['run_id']}`, gen `{o['gen_id']}`)\n")
        A(f"- client: {c['chunks_received']} SSE chunks / ~{c['est_tokens_received_chars_div_4']} tokens (chars/4; reasoning chars {c['reasoning_chars']}, content chars {c['content_chars']}) received; "
          f"cancelled={c['cancelled']}; trace termination_reason=`{c['termination_reason']}`; stop record: {json.dumps(c['stop_record'])}; client error: {c['error']}")
        A(f"- /generation ({o['generation_lag_note']}): cancelled={g1.get('cancelled')}, tokens_completion={g1.get('tokens_completion')} (native {g1.get('native_tokens_completion')}, reasoning {g1.get('native_tokens_reasoning')}), "
          f"tokens_prompt={g1.get('tokens_prompt')}, total_cost=${g1.get('total_cost')}, finish_reason={g1.get('finish_reason')}, provider={g1.get('provider_name')}")
        A(f"- second read 12 s later: tokens_completion={g2.get('tokens_completion')}, total_cost=${g2.get('total_cost')}; record grew between reads: {o['generation_record_grew_between_reads']}")
        A(f"- key usage counter: before ${o['key_usage_before']} -> after (stable) ${o['key_usage_after_stable']}; delta {o['key_usage_delta']}")
        A(f"- requested max_tokens {o['max_tokens']}; estimated cost of a full max_tokens generation ${o['cost_of_full_max_tokens_generation_estimate_usd']}; billed fraction of full: {o['billed_fraction_of_full']}\n")
    if dts:
        canc = [o for o in dts if o["requested_disconnect_chunks"]]
        A("**Findings (descriptive):**\n")
        for o in canc:
            tc = (o["generation_second_read_after_12s"] or o["generation_first_read"]).get("tokens_completion")
            est = o["client"]["est_tokens_received_chars_div_4"]
            A(f"- disconnect after {o['requested_disconnect_chunks']} chunks: client saw ~{est} tokens; OpenRouter billed {tc} completion tokens "
              f"(ratio billed/received-estimate {round(tc / est, 2) if tc and est else 'n/a'}; vs max_tokens {o['max_tokens']}: {round(100 * tc / o['max_tokens'], 1) if tc else 'n/a'}%); "
              f"generation flagged cancelled={(o['generation_second_read_after_12s'] or o['generation_first_read']).get('cancelled')}; record stable after 12 s: {not o['generation_record_grew_between_reads']}.")
        A("")
    # ---------------- 3 families
    A("## 3. Prompt-family pilot (Step 3)\n")
    A(f"- stop reason: {stages.get('pilot_stop_reason', 'n/a')}; runs per family: {stages.get('pilot_counts')}; extended: {stages.get('pilot_extended')}")
    b_calls = [len(_calls(t)) for t in base_traces if t["stats"]["stage"] in ("elicit", "smoke")][:6]
    b_ratio = [t["stats"]["distinct_ratio"] for t in base_traces if t["stats"]["stage"] in ("elicit", "smoke")][:6]
    b_gens = [sum(len(g["tool_calls"]) for tu in t["turns"] for g in tu["generations"]) / max(1, sum(1 for tu in t["turns"] for g in tu["generations"] if g["tool_calls"])) for t in base_traces if t["stats"]["stage"] in ("elicit", "smoke")][:6]
    A(f"- BASELINE (first six earlier runs, unchanged prompts): calls/run {b_calls}, distinct ratio {b_ratio}, calls per tool-calling generation ~{_stat(b_gens)}\n")
    A("| family | runs | calls/run mean (min-max) | generations/run | calls per generation | distinct ratio mean (min-max) | max repeats of one call | flood-qualifying | terminations |\n|---|---|---|---|---|---|---|---|---|")
    fam_rows = {}
    for f in FAMILIES:
        ts = [t for t in pil if t["stats"]["mode"] == f]
        if not ts:
            continue
        calls = [t["stats"]["n_calls"] for t in ts]
        gens = [t["stats"]["n_turns"] for t in ts]
        cpg = [t["stats"]["n_calls"] / max(1, sum(1 for tu in t["turns"] for g in tu["generations"] if g["tool_calls"])) for t in ts]
        ratios = [t["stats"]["distinct_ratio"] for t in ts if t["stats"]["n_calls"]]
        maxrep = []
        for t in ts:
            c = Counter(CR.signature(x["name"], x["arguments"]) for x in _calls(t))
            maxrep.append(max(c.values()) if c else 0)
        fam_rows[f] = {"calls": statistics.mean(calls), "min_ratio": min(ratios) if ratios else 1.0, "maxrep": max(maxrep)}
        A(f"| {f} | {len(ts)} | {_stat(calls, '{:.1f}')} | {_stat(gens, '{:.1f}')} | {_stat(cpg)} | {_stat(ratios, '{:.3f}')} | {max(maxrep)} | {sum(1 for t in ts if t['flood_qualifying_machine'])} | {dict(Counter(t['termination_reason'] for t in ts))} |")
    A("")
    A("Per-run table:\n\n| run id | family | gens | calls | distinct | ratio | flood-qualifying | termination | cost usd | latency s |\n|---|---|---|---|---|---|---|---|---|---|")
    for t in pil:
        s = t["stats"]
        A(f"| {t['run_id']} | {s['mode']} | {s['n_turns']} | {s['n_calls']} | {s['n_distinct']} | {s['distinct_ratio']} | {t['flood_qualifying_machine']} | {t['termination_reason']} | {t['cost_usd']:.6f} | {t['latency_s']} |")
    A("")
    A("### Repeated / cyclic patterns observed (descriptive; runs with >= 4 calls and any repeated call)\n")
    shown = 0
    for t in pil:
        sigs = [CR.signature(x["name"], x["arguments"]) for x in _calls(t)]
        if len(sigs) >= 4 and len(set(sigs)) < len(sigs):
            top = Counter(sigs).most_common(2)
            A(f"- `{t['run_id']}`: {len(sigs)} calls, {len(set(sigs))} distinct; shape: {CR.describe_shape(sigs)}; top: " + "; ".join(f"{s[:90]} x{c}" for s, c in top))
            shown += 1
    if not shown:
        A("- none: no run repeated a call in a pattern of >= 4 calls.")
    A("")
    ranked = sorted(fam_rows.items(), key=lambda kv: (-kv[1]["calls"], kv[1]["min_ratio"]))
    A("### Strongest signal vs baseline\n")
    if ranked:
        A("Ranked by mean calls/run then lowest distinct ratio: " + "; ".join(f"{f} (mean calls {v['calls']:.1f}, min ratio {v['min_ratio']:.2f}, max repeats {v['maxrep']})" for f, v in ranked))
        A(f"\nBaseline for comparison: 1-8 calls/run, ratio ~1.0, 1 call/generation.\n")
    quals = [t for t in traces if t["flood_qualifying_machine"]]
    A(f"## 4. Flood-qualifying runs (frozen definition): {len(quals)} - HUMAN CONFIRMATION NEEDED (maintainer)\n")
    if not quals:
        A("none.\n")
    for t in quals:
        A(f"### `{t['run_id']}` (split `{t['split']}`, human confirmation {t['human_confirmation']})\n```\n{excerpt(t)}\n```\n")
    A("## 5. Escalation statement\n")
    if not pil:
        A("**no evidence collected; escalation question undecidable.** There are no live pilot runs in this report, so nothing can be said about whether any family "
          "justifies escalation (this is not a finding about the families). Decision belongs to the maintainer; I did not escalate.\n")
    elif len(quals) >= 5:
        A(f"{len(quals)} runs meet the machine definition (pending human confirmation). This report does not escalate; whether to scale is for the maintainer to decide.\n")
    elif quals:
        A(f"{len(quals)} run(s) meet the machine definition (< 5; pending human confirmation). Whether any family justifies escalation is for the maintainer to decide; I did not escalate.\n")
    else:
        A("No family produced a flood-qualifying run and none shows materially more repetition than baseline (see table). On these numbers no family justifies escalation; the decision belongs to the maintainer. I did not escalate.\n")
    A("**P2-B null-result statement:** " + ("no live pilot runs were made in this report, so no null result is claimed. " if not pil else "") + (f"{len(quals)} flood-qualifying runs (< 5) in {len(pil)} pilot runs -> " if len(quals) < 5 and pil else "") +
      f"a null result means **no flood was elicited under these conditions** (model gpt-oss-20b, {PINNED_NAME} pinned, these 8 prompt families, caps 12 turns / 4000 max_tokens per request / 120 calls, N small); "
      "it is NOT evidence that the model cannot flood, that floods are rare in the world, or that the guard works. This pilot is far below the pre-registered N >= 100.\n")
    A("## 6. Observations and anomalies\n")
    shapes = [r["shape"] for r in reqs if r.get("shape")]
    if shapes:
        A(f"- delta style: {dict(Counter(s['delta_style'] for s in shapes))}; reasoning fields: {dict(Counter(f for s in shapes for f in s['reasoning_fields_seen']))}; id/index collisions {sum(s['id_index_collisions'] for s in shapes)}")
    A(f"- calls per generation across pilot: {dict(Counter(len(g['tool_calls']) for t in pil for tu in t['turns'] for g in tu['generations']))}")
    A(f"- latency per request (s): {_stat([r.get('latency_s') for r in reqs])}; ttfb (s): {_stat([r.get('ttfb_s') for r in reqs])}")
    A(f"- 429 retries/stops: {json.dumps(stages.get('retries'))}")
    A(f"- providers served: {dict(Counter(p for t in traces for p in t['provenance'].get('provider_served', [])))}")
    A("- F7 note: the primed history's 40 prior calls are NOT counted toward the run's tool calls (only calls the model itself issued are counted).\n")
    A("## 7. Data handling / secret scan\n")
    A(f"- traces `{out_dir.relative_to(ROOT) if str(out_dir).startswith(str(ROOT)) else out_dir}/traces.jsonl` (split `exploratory-2A`, note 'EXPLORATORY: must NOT be used as untouched confirmatory data for Guard v2'), raw SSE per request in `raw/`; earlier Phase 2A data untouched.")
    A("- the key was read from the environment by the process only, never printed, logged or stored; Authorization headers never saved.")
    A("- secret scan: (filled by the runner)\n")
    if HISTORY_DOC.exists() and not mock:
        A("\n" + HISTORY_DOC.read_text())
    report_path.write_text("\n".join(L))
    return report_path


# ------------------------------------------------------------------------------------------------ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--mock", action="store_true"); g.add_argument("--live", action="store_true")
    ap.add_argument("--disconnect", action="store_true"); ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--out-dir", default=None); ap.add_argument("--ledger", default=None); ap.add_argument("--report", default=None)
    ap.add_argument("--families", default=None, help="comma-separated subset"); ap.add_argument("--n-initial", type=int, default=3); ap.add_argument("--n-max", type=int, default=5); ap.add_argument("--stop-at-floods", type=int, default=5)
    ap.add_argument("--retry-attempts", type=int, default=DEFAULT_RETRY_ATTEMPTS); ap.add_argument("--retry-wall-s", type=float, default=DEFAULT_RETRY_WALL_S)
    ap.add_argument("--retry-base-s", type=float, default=DEFAULT_RETRY_BASE_S); ap.add_argument("--retry-cap-s", type=float, default=DEFAULT_RETRY_CAP_S)
    ap.add_argument("--retry-global-wall-s", type=float, default=DEFAULT_RETRY_GLOBAL_WALL_S)
    a = ap.parse_args(argv)
    do_dis, do_pil = (a.disconnect or not a.pilot), (a.pilot or not a.disconnect)
    live = a.live
    if live and not preflight_key_present():
        print(f"REFUSING live run: {KEY_ENV} is not set in the environment (checked by name only). No request was made.", file=sys.stderr); return 2
    out = Path(a.out_dir) if a.out_dir else (PILOT_OUT if live else MOCK_OUT)
    ledger = Path(a.ledger) if a.ledger else (LIVE_LEDGER if live else out / "spend_ledger.jsonl")
    out.mkdir(parents=True, exist_ok=True)
    base_traces = load_jsonl(LIVE_OUT / "traces.jsonl") if live else []
    cfg = Config(live, out, ledger, max_tokens=4000, max_turns=12, retry_max_attempts=a.retry_attempts, retry_total_wall_s=a.retry_wall_s, retry_base_s=a.retry_base_s, retry_cap_s=a.retry_cap_s,
                 retry_global_wall_s=a.retry_global_wall_s, gen_retries=10 if live else 4)
    guard = BudgetGuard(ledger, live=live)
    if live and guard.spent() >= guard.cap:
        print("REFUSING: cap reached", file=sys.stderr); return 2
    fams = a.families.split(",") if a.families else None

    def go(up):
        col = Collector(cfg, up, guard)
        col.stages.update(mode="live" if live else "mock", spent_before_usd=guard.spent(), model=MODEL, provider_pin=PROVIDER_PIN, caps={"max_tokens_per_request": 4000, "max_turns": 12, "max_calls": 120},
                          started_at=time.strftime("%Y-%m-%d %H:%M:%S %Z"))
        col.stages["key_usage_start_usd"] = col.fetch_key_usage()
        try:
            if do_dis:
                log("== step 1: early-disconnect test =="); disconnect_test(col)
            if do_pil:
                log("== step 3: family pilot =="); pilot(col, fams, a.n_initial, a.n_max, a.stop_at_floods)
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
        ku_now = key_usage_stable(col)
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
    rp = Path(a.report) if a.report else ((ROOT / "PHASE2A_PILOT_REPORT.md") if live else out / "PHASE2A_PILOT_REPORT.MOCK.md")
    write_pilot_report(out, ledger, mock=not live, report_path=rp, base_traces=base_traces, stages=col.stages, ku_now=ku_now)
    scan = secret_scan([out, rp] + ([ledger] if live else []), os.environ.get(KEY_ENV) if live else None)
    rp.write_text(rp.read_text().replace("(filled by the runner)", scan["text"]))
    print("secret scan:", "CLEAN" if scan["clean"] else "!! FOUND: " + str(scan["hits"]))
    print("report:", rp); print(f"spent (cumulative): ${guard.spent():.6f}")
    return 3 if col.stages.get("anomaly") else 0


if __name__ == "__main__":
    raise SystemExit(main())
