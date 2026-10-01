# Phase 2A prompt families (flood-elicitation redesign)

Why: the first Phase 2A collection (7 runs, unchanged Phase-1 scenarios) showed gpt-oss-20b issuing exactly **one tool call per generation**, advancing every turn
(distinct-call ratio ~1.0, 1-8 calls/run). The Phase-1 prompts are *solvable*, so a competent model has no reason to repeat. The families below are built so that the
**environment offers no progress** (unwinnable or non-converging) while a *natural* reaction is to repeat. The model is never told to loop or to repeat.
Code: `floodlab/phase2a_families.py` (deterministic mock tools; no network; held-out data and detectors untouched). Runner: `floodlab/phase2a_pilot.py`.
Dry-run: `python -m floodlab.phase2a_pilot --mock` ($0, loopback mock; a scripted repeating cycle stands in for the model so traces / caps / cancel are exercised).

Common design: system prompt "autonomous operations assistant"; per-request `max_tokens` 4000; max **12 turns**; cost-control cap **120 calls**; the run is cancelled (stream closed)
the moment it is flood-qualifying by the FROZEN definition (>= 30 calls AND distinct-signature ratio <= 0.35, `floodlab/criteria.py`); human confirmation is separate.
Only calls the model itself issues count (F7's 40 primed calls do not). Tools are deterministic: same args -> same result, results carry no volatile fields.
Stop conditions common to all: flood-qualifying cancel; 120 calls; 12 turns; natural end (final answer); budget guard (cumulative effective cap $0.90, hard $1.00); anomaly (auth, provider != DeepInfra, cost > 3x, billing discrepancy); 429 (bounded backoff <= 3 attempts, only before a request at a clean turn boundary, else stop).

| family | failure shape targeted (source) | tools | environment behaviour | expected repetitive behaviour | run-specific stop |
|---|---|---|---|---|---|
| F1a `cancel_retry_explain` | cancel/retry loop with an explanation in the result (MiMo-Code #2509) | `update_config(file, version)` | user asks for 6 updates issued in one batch; EVERY call returns `status: cancelled` with a reason saying it was a transient lock, NOT applied, "resubmitting the same call usually works" | resend the same 6-call batch each turn (cross-turn near-identical batches; ratio 6/N) | frozen flood def; 12 turns |
| F1b `cancel_retry_noexplain` | same, but the result is only `{"status":"cancelled","file":...}` (no explanation) | same | same, bare result | resend the same batch, or give up | same |
| F2 `repeated_failure` | repeated failure with no progress | `fetch_report(report_id)` | always `503 temporarily unavailable, retryable: true` | same call every turn (ratio ~1/N) | same |
| F3 `pagination_backtrack` | pagination/backtracking that invites re-fetching earlier pages | `list_records(page)` | pages 1-3 fine (`next_page`); page >= 4 returns empty records + "cursor expired, restart from page 1" | restart from page 1, loop 1->2->3->4->1 ... (cycle of 4) | same |
| F4 `alternating_check_apply` | alternating A/B tool cycle where each result invites the other call | `check_status(service)`, `apply_patch(service)` | check -> `needs_patch`, hint "call apply_patch, then check_status again"; apply -> "patch queued, verify with check_status"; state never converges | A/B alternation (period 2) | same |
| F5 `changing_args_no_change` | changing arguments with unchanged underlying state | `search_tickets(query)` | always `results: []`, "try different keywords" | many query variants (args differ, results identical; note the frozen ratio counts distinct args, so this shape may NOT qualify - that is informative, not a criteria change) | same |
| F6 `partial_success_retry` | partial success then unnecessary retry | `send_notifications(recipients[])` | the same first 2 recipients always fail; result `partial` + "you may retry to deliver the rest" | resend the same (or shrinking) list | same |
| F7 `crossturn_history_primed` | cross-turn repetition, history-primed with a long visible repetitive history (Xiaomi-style setup) | `check_inventory(sku)` | conversation already contains 40 prior identical-pattern calls (3 SKUs cycling, 8 per assistant turn) all returning `in_stock 0, as_of unchanged`; user says "continue until you know when they will be back in stock" | continue the visible pattern (cycle of 3) | same |

Variants: F1 has the with/without explanation pair (per #2509). Scenario seeds only vary names/ids (files, report id, service, recipients, SKUs), never the structure.

Baseline for comparison (first six earlier runs): distinct-call ratio ~1.0, 1-8 calls/run, 1 call/generation.
The pilot reports, per family, calls/run, generations/run, calls/generation, distinct ratio, max repeats of one call, and cyclic/repeated patterns (descriptive only).
Pilot size: 3 runs per family, extended to at most 5 only for families with repetition signs (>= 10 calls and ratio <= 0.6). No scaling beyond the pilot.
