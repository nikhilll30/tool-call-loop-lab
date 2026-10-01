# Phase 1 (zero-cost, offline) status

> **Historical report of an earlier phase.** Test counts, file listings and paths in this document describe that phase and may differ from the current repository (current test count: see `README.md`). References to files that are not in this repository (for example `spend_ledger.jsonl`, `evidence/`, `PHASE0_REPORT.md`) point to private material that is not published.

**Spend: $0.00. Live/paid API calls: none. Network: loopback only** (tests install a socket guard that fails any non-loopback connect;
`spend_ledger.jsonl` holds only `usd: 0.0, live_call: false` rows).

## Built
Trace schema + provenance (`docs/TRACE_SCHEMA.md`); deterministic mock tools with simulated state; 6 scenarios x 5 prompt modes;
8 synthetic flood generators (#2482, #2509 shapes etc.); 7 legitimate families x 20 seeds + 6 hand-written legit traces;
detector library (exact-dup and last-N baselines; near-dup, cycle, distinct-ratio/entropy, cross-turn; state-aware suppression),
dataclass configs with stable hashes; offline evaluation with dev/test seeds; freeze tooling + Stage-4 gate; FastAPI mock upstream
(whole-call and incremental deltas, reasoning_content, usage chunk before [DONE], disconnect/"tokens generated" recording);
replay harness (caps, budget guard, ledger, stop-early hook, reasoning pass-back); guard-proxy skeleton (per-generation cap,
detector-based cancel, structured `floodlab_guard` field, hard stop after N identical batches).

## Test results
`pytest`: **87 passed** in ~12 s (detectors 31, harness 22, guard/freeze 12, tools/scenarios 10, generators/trace 6, mock upstream 6).
Full list: `results/pytest_verbose.txt`.

## Baseline-miss table (TEST seeds 100-109, n=10/shape, SYNTHETIC)
Copied from `results/eval_report.md` (regenerate with the demo):

| shape | max adjacent run | exact_dup | last-3 adjacent | new detectors (raw) | new + state-aware | both baselines miss | median first idx: exact_dup | state_aware |
|---|---|---|---|---|---|---|---|---|
| abc_cycle_multi_gen | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | - | 8 |
| abc_cycle_one_gen | 1 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 4 | 8 |
| cancel_retry_2509 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | - | 50 |
| cross_turn_identical_batches | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | - | 35 |
| near_dup_counter | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | - | 7 |
| rotating35_multi_gen | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | - | 95 |
| rotating35_one_gen (#2482 shape) | 1 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 36 | 95 |
| start_done_alternation | 1 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 71 | 209 |

**Read this plainly:** the single-generation 4,120-call rotating-35 shape defeats the *adjacent* guard (run = 1) but is **not** missed by
exact-duplicate counting (it has 4,085 within-generation repeats); the same holds for start/done alternation and A,B,C in one
generation. The exact-dup baseline is blind only to floods whose repetition is spread across generations/turns, to near-duplicates
with a changing volatile field, and to cancelled-batch retries (#2509) - 5 of the 8 shapes here. This is by construction of
the baseline's scope (within-generation, byte-exact), and because we wrote the shapes; it says nothing about how often these happen in real models.
The new detectors additionally fire earlier than post-hoc counting only in the sense of a first-index; both are much later than a
sensible client cap for the #2482 shape (index 95 vs 36 - exact-dup can fire earlier when used as an online guard).

## Offline false-positive rates on the legitimate suite (146 traces = 140 generated + 6 hand-written; SYNTHETIC)
| detector | FP rate |
|---|---|
| exact_dup (baseline) | 0.137 |
| adjacent (baseline) | 0.288 |
| near_dup | 0.562 |
| cycle | 0.281 |
| distinct_ratio | 0.000 |
| cross_turn | 0.000 |
| combined_raw (4 new, no state) | 0.562 |
| **state_aware** (4 new + result-hash suppression) | **0.007** (1/146: the hand-written hard plateau-polling trace) |

The draft `frozen_fp_threshold` is 0.05 (DRAFT). Raw near-dup/cycle detectors are unusable alone: legit polling and read/edit loops look repetitive.
State-awareness carries the FP control, and it depends on tool-result hashes being available to the guard (the proxy reconstructs them
from `tool` messages in the request) and on the legitimate suite containing state changes by construction.

## Not done / needs live calls (none performed; awaiting an OpenRouter key and explicit approval)
1. Streamed tool-call delta shapes at the real providers (whole-call vs fragments; comment lines; usage chunk placement; mid-stream errors).
2. Disconnect billing measurement (do provider tokens keep billing after client disconnect?). The mock's "tokens at disconnect" is only a simulation.
3. History-primed provider fingerprint probe (which providers serve RL vs MOPD weights).
4. Any real flood traces at all; Stage-2 re-evaluation on them; Stage-3 freeze; Stage-4 A/B (not implemented).
