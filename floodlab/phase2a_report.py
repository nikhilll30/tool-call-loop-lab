"""PHASE2A_REPORT.md generator. Pure formatting of collected data: no detectors, no tuning, descriptive only."""
from __future__ import annotations
import json, statistics
from collections import Counter, defaultdict
from pathlib import Path
from . import criteria as CR
from .budget import BudgetGuard, HARD_CAP_USD
from .phase2a_common import load_jsonl


def _pin():
    from .phase2a import PINNED_NAME
    return PINNED_NAME


def _q(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return "n/a"
    return f"min {xs[0]:.2f} / median {statistics.median(xs):.2f} / max {xs[-1]:.2f} (n={len(xs)})"


def excerpt(t: dict, n_first=10) -> str:
    calls = [c for tu in t["turns"] for g in tu["generations"] for c in g["tool_calls"]]
    sigs = [CR.signature(c["name"], c["arguments"]) for c in calls]
    lines = [f"  first {min(n_first, len(calls))} calls:"]
    lines += [f"    {i:>3}. {s[:150]}" for i, s in enumerate(sigs[:n_first])]
    lines.append("  repeating pattern (descriptive):")
    lines += [f"    {p[:170]}" for p in CR.repeating_pattern(sigs)]
    lines.append(f"  shape (descriptive): {CR.describe_shape(sigs)};  calls={len(sigs)} distinct={len(set(sigs))} ratio={CR.distinct_ratio(sigs):.3f}")
    lines.append(f"  terminated: {t['termination_reason']}")
    return "\n".join(lines)


def write_report(out_dir: Path, ledger_path: Path, *, mock: bool, report_path: Path) -> Path:
    out_dir = Path(out_dir)
    traces = load_jsonl(out_dir / "traces.jsonl")
    reqs = load_jsonl(out_dir / "requests.jsonl")
    st = json.loads((out_dir / "stages.json").read_text()) if (out_dir / "stages.json").exists() else {}
    guard = BudgetGuard(ledger_path, live=not mock)
    rows = guard.rows()
    label = "MOCK RUN (loopback mock upstream, $0, NOT live data)" if mock else "LIVE RUN"
    L: list[str] = []
    A = L.append
    A(f"# PHASE 2A REPORT - {label}\n")
    A("**EXPLORATORY: must NOT be used as untouched confirmatory data for Guard v2.** Unguarded live trace collection, model `openai/gpt-oss-20b`, "
      f"provider pinned to {_pin()} (`allow_fallbacks:false`). Flood definition frozen in `docs/FROZEN_CRITERIA_PHASE2.md` "
      f"(criteria id `{CR.CRITERIA_ID}`, hash `{CR.CRITERIA_HASH}`): >= {CR.MIN_CALLS} calls AND distinct-signature ratio <= {CR.MAX_DISTINCT_RATIO}. "
      "No detector or guard was run; nothing frozen was changed; Guard v2 was not implemented or evaluated.\n")
    if mock:
        A("> This is a dry-run report generated against the mock upstream to test the report generator. Numbers below are NOT evidence about any model.\n")
    A("## 1. Summary\n")
    elicit = [t for t in traces if t["stats"]["stage"] == "elicit"]
    quals = [t for t in traces if t["flood_qualifying_machine"]]
    spent = guard.spent()
    A(f"- mode: {st.get('mode')}, started {st.get('started_at')}, finished {st.get('finished_at')}")
    A(f"- runs total: {len(traces)} (elicitation: {len(elicit)}); flood-qualifying by frozen machine definition: **{len(quals)}** (human confirmation pending)")
    A(f"- collection stop reason: {st.get('collection_stop_reason', 'n/a')}")
    A(f"- **anomaly / early stop:** {json.dumps(st.get('anomaly')) if st.get('anomaly') else 'none'}")
    if st.get("budget_refusal"):
        A(f"- budget guard refusal: {st['budget_refusal']}")
    A(f"- **actual spend (ledger sum): ${spent:.6f}** (hard cap ${HARD_CAP_USD:.2f}, effective cap ${guard.cap:.2f})")
    ku0, ku1 = st.get("key_usage_start_usd"), st.get("key_usage_end_usd")
    if ku0 is not None and ku1 is not None:
        A(f"- OpenRouter key usage counter (GET /api/v1/key, `usage` field only): start ${ku0:.6f} -> end ${ku1:.6f}; delta ${ku1 - ku0:.6f}")
    A("")
    A("## 2. Spend ledger and reconciliation\n")
    A("Ledger rows (`spend_ledger.jsonl`, `live_call: %s`; `usd` per row is a delta: precharge = worst case BEFORE launch, settle = actual - precharge, "
      "reconcile = /generation total_cost - current charge). Sum of rows = spend.\n" % (not mock))
    A("| kind | n rows | sum usd |\n|---|---|---|")
    byk = defaultdict(lambda: [0, 0.0])
    for r in rows:
        byk[r["kind"]][0] += 1; byk[r["kind"]][1] += r.get("usd", 0.0)
    for k, (n, s) in byk.items():
        A(f"| {k} | {n} | {s:.6f} |")
    A(f"| **total** | {len(rows)} | **{spent:.6f}** |\n")
    A("Per request (settled cost from streamed `usage.cost` vs OpenRouter `/api/v1/generation` `total_cost`):\n")
    A("| request | stage | provider | prompt tok | completion tok (incl. reasoning) | usage.cost | /generation total_cost | cancelled |\n|---|---|---|---|---|---|---|---|")
    sum_usage = sum_gen = 0.0; n_pair = 0; unrec = []
    for r in reqs:
        g = r.get("generation") or {}
        u = r.get("usage") or {}
        uc, gc = r.get("usd_settled"), g.get("total_cost")
        if uc is not None and gc is not None:
            sum_usage += uc; sum_gen += gc; n_pair += 1
        if gc is None:
            unrec.append(r["request_key"])
        A(f"| {r['request_key']} | {r['stage']} | {r.get('provider')} | {u.get('prompt_tokens')} | {u.get('completion_tokens')} | "
          f"{'' if uc is None else f'{uc:.6f}'} | {'' if gc is None else f'{gc:.6f}'} | {r.get('cancelled')} |")
    A("")
    if n_pair:
        dev = abs(sum_usage - sum_gen) / sum_gen if sum_gen else 0.0
        A(f"- reconciliation over {n_pair} requests having both numbers: sum usage.cost ${sum_usage:.6f} vs sum /generation ${sum_gen:.6f} (deviation {dev:.1%}; P2-A tolerance 20%)")
    A(f"- requests without a /generation record retrievable: {len(unrec)} {unrec[:5]}")
    A("")
    A("## 3. Runs by mode\n")
    A("| stage | mode | runs | calls (median / max) | flood-qualifying | repetition signs (>=10 calls, ratio <= 0.6) | terminations |\n|---|---|---|---|---|---|---|")
    grp = defaultdict(list)
    for t in traces:
        grp[(t["stats"]["stage"], t["stats"]["mode"])].append(t)
    for (stg, mode), ts in sorted(grp.items()):
        calls = [t["stats"]["n_calls"] for t in ts]
        signs = sum(1 for t in ts if t["stats"]["n_calls"] >= 10 and (t["stats"]["distinct_ratio"] or 1) <= 0.6)
        terms = Counter(t["termination_reason"] for t in ts)
        A(f"| {stg} | {mode} | {len(ts)} | {statistics.median(calls):g} / {max(calls)} | {sum(1 for t in ts if t['flood_qualifying_machine'])} | {signs} | {dict(terms)} |")
    A("")
    zero = [m for m in ("history_primed", "rotating_argument", "ab_alternating", "cross_turn")
            if grp.get(("elicit", m)) and not any(t["flood_qualifying_machine"] for t in grp[("elicit", m)])]
    A(f"- modes with ZERO flood-qualifying runs (reported honestly): {zero or 'none'}\n")
    A("Per-run table:\n")
    A("| run id | scenario | mode | turns | calls | distinct | ratio | flood-qualifying | termination | cost usd | latency s |\n|---|---|---|---|---|---|---|---|---|---|---|")
    for t in traces:
        s = t["stats"]
        A(f"| {t['run_id']} | {s['scenario']} | {s['mode']} | {s['n_turns']} | {s['n_calls']} | {s['n_distinct']} | {s['distinct_ratio']} | "
          f"{t['flood_qualifying_machine']} | {t['termination_reason']} | {t['cost_usd']:.6f} | {t['latency_s']} |")
    A("")
    A(f"## 4. Flood-qualifying runs: {len(quals)} - HUMAN CONFIRMATION NEEDED (maintainer)\n")
    if not quals:
        A("none.\n")
    for t in quals:
        A(f"### `{t['run_id']}`  (split `{t['split']}`, human confirmation: {t['human_confirmation']})\n```")
        A(excerpt(t)); A("```\n")
    A("### Flood shapes seen (descriptive only)\n")
    if quals:
        for shp, c in Counter(CR.describe_shape([CR.signature(c['name'], c['arguments']) for tu in t['turns'] for g in tu['generations'] for c in g['tool_calls']]) for t in quals).items():
            A(f"- {shp}: {c} run(s)")
    else:
        A("- none observed")
    A("")
    A("### Statement on P2-B (elicitation)\n")
    if len(quals) < 5:
        A(f"**NULL RESULT for this exploratory collection:** {len(quals)} flood-qualifying run(s) (< 5) in {len(elicit)} elicitation runs "
          f"(model gpt-oss-20b, provider {_pin()} pinned, modes {sorted({t['stats']['mode'] for t in elicit})}, caps per run: max_tokens {st.get('caps', {}).get('max_tokens_per_request')}/request, "
          f"{st.get('caps', {}).get('max_turns')} turns, {st.get('caps', {}).get('max_calls')} calls). Per docs/FROZEN_CRITERIA_PHASE2.md this means "
          "**no flood was elicited under these conditions**. It is NOT evidence that the model cannot flood, that floods are rare in the world, or that "
          "the guard works. This small-N exploratory collection (N << 100) also cannot satisfy the pre-registered P2-B sample size.\n")
    else:
        A(f"{len(quals)} flood-qualifying run(s) by the machine definition (>= 5), pending human confirmation. This is an exploratory collection with N = {len(elicit)} "
          "(pre-registered P2-B needs N >= 100 unguarded runs); no rate claims are made.\n")
    A("## 5. Cancel and billing observations\n")
    obs = st.get("cancel_observations", [])
    if not obs:
        A("no cancelled stream was observed.\n")
    for o in obs:
        A("```\n" + json.dumps(o, indent=1) + "\n```")
    if obs:
        A("`est_completion_tokens_received(chars/4)` is a client-side estimate (visible reasoning + content + tool-call text; a tokenizer would differ). "
          "`generation_tokens_completion` is what OpenRouter reports after the disconnect; a ratio >> 1 means the provider kept generating/billing after our disconnect.\n")
    A("## 6. Delta-shape observations\n")
    shapes = [r["shape"] for r in reqs if r.get("shape")]
    if shapes:
        A(f"- delta style per request (whole / incremental / mixed / none): {dict(Counter(s['delta_style'] for s in shapes))}")
        A(f"- reasoning field names seen: {dict(Counter(f for s in shapes for f in s['reasoning_fields_seen']))}; reasoning_details seen in {sum(1 for s in shapes if s['reasoning_details_seen'])} request(s)")
        A(f"- id/index collisions (index reused with a different id): {sum(s['id_index_collisions'] for s in shapes)}; max deltas per call: {max(s['max_deltas_per_call'] for s in shapes)}; "
          f"first delta carried arguments in {sum(s['first_delta_carries_arguments'] for s in shapes)} of {sum(s['calls'] for s in shapes)} calls")
        A(f"- distinct provider `index` values per request (max): {max(s['provider_indices_distinct'] for s in shapes)}")
    A(f"- usage chunk placement: has choices={Counter(str(r.get('usage_chunk_has_choices')) for r in reqs if r.get('stage') != 'connectivity')}; after finish_reason={Counter(str(r.get('usage_after_finish')) for r in reqs if r.get('stage') != 'connectivity')}")
    A(f"- SSE comment lines ignored (e.g. `: OPENROUTER PROCESSING`): total {sum(r.get('sse_comment_lines') or 0 for r in reqs)}; unparseable data lines: {sum(r.get('bad_sse_lines') or 0 for r in reqs)}; "
      f"streams ended with [DONE]: {sum(1 for r in reqs if r.get('done_seen'))} of {len([r for r in reqs if r.get('stage') != 'connectivity'])}")
    fr = Counter(r.get('finish_reason') for r in reqs if r.get('stage') != 'connectivity')
    A(f"- finish reasons (streamed requests): {dict(fr)}")
    quirks = Counter()
    for t in traces:
        for tu in t["turns"]:
            for g in tu["generations"]:
                for k, v in (g.get("quirks") or {}).items():
                    quirks[k] += v
                quirks["truncated_last_call_dropped"] += 1 if g.get("truncated_last_call_dropped") else 0
    A(f"- id quirks (missing/duplicate tool-call ids, truncated final call): {dict(quirks)}")
    calls_per_gen = [len(g["tool_calls"]) for t in traces for tu in t["turns"] for g in tu["generations"]]
    A(f"- tool calls per generation: {_q(calls_per_gen)}\n")
    A("## 7. Latency\n")
    A(f"- time to first chunk (s): {_q([r.get('ttfb_s') for r in reqs])}")
    A(f"- per streamed request latency (s): {_q([r.get('latency_s') for r in reqs])}")
    A(f"- per run latency (s): {_q([t['latency_s'] for t in traces])}\n")
    A("## 8. Provenance and data handling\n")
    provs = Counter(p for t in traces for p in t["provenance"].get("provider_served", []))
    A(f"- provider actually served (from stream chunks): {dict(provs) or 'not reported in chunks'}; /generation provider_name: "
      f"{dict(Counter((r.get('generation') or {}).get('provider_name') for r in reqs if r.get('generation')))}")
    A(f"- model returned: {dict(Counter(r.get('model_returned') for r in reqs if r.get('model_returned')))}")
    A(f"- traces: `{out_dir.name}/traces.jsonl` (split `exploratory-2A`, note field: '{traces[0]['notes'].split(';')[0] if traces else ''}'), raw SSE per request in `raw/*.sse.gz`, per-request records `requests.jsonl`")
    A("- dev evaluation (`floodlab.evaluate`) and held-out evaluation (`floodlab.heldout_eval`) refuse exploratory-2A traces (tests in tests/test_phase2a.py).")
    A(f"- the key (`OPENROUTER_API_KEY`) was read by the process from the environment only, never printed, logged or written; Authorization headers are never saved; every saved string passes a redactor; "
      f"a post-run grep of the output directory and report for key-shaped strings is recorded in section 9.\n")
    A("## 9. Secret scan\n")
    A("(filled by the runner's post-run scan)\n")
    report_path.write_text("\n".join(L))
    return report_path
