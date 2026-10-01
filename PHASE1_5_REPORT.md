# PHASE 1.5 REPORT - calibration and freeze pass (offline, $0)

> **Historical report of an earlier phase.** Test counts, file listings and paths in this document describe that phase and may differ from the current repository (current test count: see `README.md`). References to files that are not in this repository (for example `spend_ledger.jsonl`, `evidence/`, `PHASE0_REPORT.md`) point to private material that is not published.

Date 2026-09-29 (ET). Repo `<repo>`. All data SYNTHETIC. **No live/paid calls; no external network; $0.00 spent.**

## 0. Headline
**No pre-registered policy met the pre-registered criterion (legit-interruption Clopper-Pearson upper bound <= 5.0% AND flood detection >= 30%). Per the pre-registered rule, NOTHING WAS FROZEN.**
`configs/frozen/` still holds only DRAFT files and no `MANIFEST.json`; `python -m floodlab.ab_online` refuses (exit 2). Phase 1 `state_aware` (S0) is *not* validated: on held-out data it detected 61.5% of floods but interrupted 29.5% of legitimate traces.

## 1. Frozen detector configuration
**None.** Reference hashes only: Phase 1 dev suite `draft-0.1` (S0) = `b1baa129b8d2`; repo draft guard config `guard-draft-0.1` = `40f1ef0a81be` (unchanged, DRAFT). Freeze tooling works (section 9) but was exercised only on a temp copy of S0, explicitly not a selection.

## 2. Tuning statement / burn status
* **Nothing was tuned after seeing held-out results.** No detector, threshold, candidate, label, loop_start, target or floor was changed after the first held-out run (commit `baca59a`). The run was repeated once to confirm determinism (identical).
* Held-out v1 is **NOT burned** (no tuning). It was, however, **viewed in detail** for error analysis (section 6), so it cannot serve as a clean confirmation of any *future* change. Any redesign needs a NEW split + NEW pre-registration (recommended below; not done).
* Disclosures: (a) the F8 `loop_start` in the generator was corrected 4->5 to match HELDOUT_DESIGN.md *before* the dataset was committed/run; (b) after the results I added `--frozen-dir` to `floodlab/ab_online.py` (gate testing hook, no detector logic) and read-only analysis scripts; (c) candidates S1/S2 were designed from Phase 1 dev results/reasoning before any held-out run and are in the pre-registration; (d) the author wrote both generators and detectors, so labels are author judgement (esp. plateaus: labelled legitimate for any length <= 40; F4 noisy repeats labelled flood).

## 3. Held-out dataset design (`docs/HELDOUT_DESIGN.md`, dataset sha256 `a39c0cf82d37c3a3c78b162fd3e5a972421f6602eced6b336ba01ef5b8c69a7b` pre-registered in SELECTION_PROCEDURE.md)
200 traces, seeds 1000-1009, new generators in `floodlab/heldout/` (no detector imports; tests enforce), `split="heldout"`, each with `ground_truth{label, loop_start_index, structure}`.
* **78 floods** (9 structures x 8 + 6 hand-written): F1 offset drift, F2 timestamp drift (same result), F3 4-tool lcm cycle, F4 identical query with noisy results, F5 low-rate loop with unique heartbeat, F6 flood after 12-30 legit calls, F7 start/done with re-permuted ids, F8 oscillating edit + same failure, F9 growing repeated batch.
* **122 legitimate** (11 structures x 10 + 12 hand-written): L1 poll plateaus 9-40 (dev hard case was 8), L2 backoff/token-refresh retries, L3 cursor quirks, L4 repeated sub-calls with differing results, L5 write then double re-read, L6 test-fix-rerun, L7 noisy results/unchanged state, L8 24-100 call fan-out, L9 tree crawl, L10 alternating distinct search/doc, L11 batch polling of multi-job status; plus 60-poll plateau, 70-call fan-out etc.

## 4. Pre-registered candidates, target, metrics
Selectable: exact_dup, adjacent3, cap64, cap128, S0/S1/S2 each alone and +cap64/+cap128 (13). Diagnostics only: raw near_dup, cycle, distinct_ratio, cross_turn, combined_raw. Target: CP-95% upper bound of legit interruption rate <= 5.0%, detection point estimate >= 30%. Metrics per `docs/PRIMARY_METRICS.md`: detection rate, per-trace FP, latency (calls after objective loop start; total calls before intervention), legit interruption rate (= FP for a policy) with mean fraction of calls not executed. CIs: Clopper-Pearson 95%. Caveat: traces within a structure are template-generated, not independent; CIs understate uncertainty.

## 5. Final offline metrics on held-out v1 (first and only run; `results/phase1_5/results_table.md`)
| policy | sel | detect (CP 95% CI) | FP = interruption (CP 95% CI) | latency after start: median [IQR] max | latency total: median max | frac. calls lost when interrupted |
|---|---|---|---|---|---|---|
| exact_dup | Y | 9/78 = 11.5% [5.4, 20.8] | 11/122 = 9.0% [4.6, 15.6] | 1 [1-1] max 1 (misses as len: 68) | 43 max 55 | 0.82 |
| adjacent3 | Y | 9/78 = 11.5% [5.4, 20.8] | 23/122 = 18.9% [12.3, 26.9] | 1 [1-1] max 1 (misses as len: 77) | 2 max 2 | 0.87 |
| cap64 | Y | 8/78 = 10.3% [4.5, 19.2] | 4/122 = 3.3% [0.9, 8.2] | 22 [21-24] max 26 (misses as len: 68) | 64 max 64 | 0.23 |
| cap128 | Y | 2/78 = 2.6% [0.3, 9.0] | 0/122 = 0.0% [0.0, 3.0] | 78 [76-80] max 82 (misses as len: 76) | 128 max 128 | 0.00 |
| S0 | Y | 48/78 = 61.5% [49.8, 72.3] | 36/122 = 29.5% [21.6, 38.4] | 23 [10-29] max 83 (misses as len: 36) | 34 max 95 | 0.53 |
| S0+cap64 | Y | 54/78 = 69.2% [57.8, 79.2] | 40/122 = 32.8% [24.6, 41.9] | 22 [11-26] max 83 (misses as len: 25) | 38 max 95 | 0.50 |
| S0+cap128 | Y | 50/78 = 64.1% [52.4, 74.7] | 36/122 = 29.5% [21.6, 38.4] | 24 [11-34] max 83 (misses as len: 36) | 36 max 128 | 0.53 |
| S1 | Y | 44/78 = 56.4% [44.7, 67.6] | 19/122 = 15.6% [9.6, 23.2] | 45 [18-88] max 117 (misses as len: 54) | 54 max 127 | 0.44 |
| S1+cap64 | Y | 51/78 = 65.4% [53.8, 75.8] | 23/122 = 18.9% [12.3, 26.9] | 22 [18-64] max 117 (misses as len: 48) | 64 max 127 | 0.40 |
| S1+cap128 | Y | 45/78 = 57.7% [46.0, 68.8] | 19/122 = 15.6% [9.6, 23.2] | 45 [18-88] max 117 (misses as len: 54) | 54 max 128 | 0.44 |
| S2 | Y | 33/78 = 42.3% [31.2, 54.0] | 11/122 = 9.0% [4.6, 15.6] | 42 [41-92] max 133 (misses as len: 62) | 70 max 143 | 0.24 |
| S2+cap64 | Y | 41/78 = 52.6% [40.9, 64.0] | 15/122 = 12.3% [7.0, 19.5] | 42 [38-80] max 133 (misses as len: 50) | 67 max 143 | 0.23 |
| S2+cap128 | Y | 35/78 = 44.9% [33.6, 56.6] | 11/122 = 9.0% [4.6, 15.6] | 42 [42-89] max 133 (misses as len: 62) | 70 max 143 | 0.24 |
| diag:near_dup | diag | 43/78 = 55.1% [43.4, 66.4] | 50/122 = 41.0% [32.2, 50.3] | 24 [10-42] max 54 (misses as len: 48) | 28 max 86 | 0.45 |
| diag:cycle | diag | 37/78 = 47.4% [36.0, 59.1] | 44/122 = 36.1% [27.6, 45.3] | 6 [6-17] max 133 (misses as len: 62) | 11 max 143 | 0.64 |
| diag:distinct_ratio | diag | 28/78 = 35.9% [25.3, 47.6] | 0/122 = 0.0% [0.0, 3.0] | 83 [67-86] max 91 (misses as len: 67) | 95 max 95 | 0.00 |
| diag:cross_turn | diag | 8/78 = 10.3% [4.5, 19.2] | 11/122 = 9.0% [4.6, 15.6] | 25 [22-27] max 30 (misses as len: 68) | 36 max 44 | 0.69 |
| diag:combined_raw | diag | 56/78 = 71.8% [60.5, 81.4] | 60/122 = 49.2% [40.0, 58.4] | 17 [6-26] max 83 (misses as len: 24) | 28 max 95 | 0.55 |

Latency "misses as len" = median with undetected floods counted as (trace length - loop_start). No selectable policy qualifies: the only one under the FP bound (cap128, 0/122, UB 3.0%) detects 2.6% < the 30% floor; every detector-based policy has FP-UB 15.6% or worse. **Selection outcome: NONE (`results/phase1_5/metrics.json`).**

## 6. False negatives / false positives (every one is in `results/phase1_5/errors.md` and `per_trace_outcomes.csv`; grouped here by structure; explanations are POST-HOC and were not used to change anything)
* **exact_dup** — FN (69): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F3_mixed_tool_lcm_cycle 8, F4_noisy_result_repeat 8, F5_low_rate_with_heartbeat 8, F6_flood_after_legit_prefix 8, F8_oscillating_edit_same_failure 8, F9_growing_batch_repeat 8, HW:hw_flood_3tool_cycle 1, HW:hw_flood_oscillating_edit 1, HW:hw_flood_query_creep 1, HW:hw_flood_poll_then_reread 1, HW:hw_flood_same_error_retry 1
  FP (11): L4_batch_fanout_repeated_subcalls 10, HW:hw_legit_repeated_subcalls_fanout 1
* **adjacent3** — FN (69): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F3_mixed_tool_lcm_cycle 8, F5_low_rate_with_heartbeat 8, F6_flood_after_legit_prefix 8, F7_startdone_rotating_permuted_ids 8, F8_oscillating_edit_same_failure 8, F9_growing_batch_repeat 8, HW:hw_flood_3tool_cycle 1, HW:hw_flood_oscillating_edit 1, HW:hw_flood_query_creep 1, HW:hw_flood_poll_then_reread 1, HW:hw_flood_startdone_3ids 1
  FP (23): L1_poll_long_plateau 10, L7_noisy_results_unchanged_state 10, HW:hw_legit_poll_plateau60 1, HW:hw_legit_backoff_capped_plateau 1, HW:hw_legit_noisy_poll 1
* **cap64** — FN (70): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F3_mixed_tool_lcm_cycle 8, F4_noisy_result_repeat 8, F5_low_rate_with_heartbeat 8, F6_flood_after_legit_prefix 8, F8_oscillating_edit_same_failure 8, F9_growing_batch_repeat 8, HW:hw_flood_3tool_cycle 1, HW:hw_flood_oscillating_edit 1, HW:hw_flood_query_creep 1, HW:hw_flood_poll_then_reread 1, HW:hw_flood_same_error_retry 1, HW:hw_flood_startdone_3ids 1
  FP (4): L8_large_fanout_distinct 3, HW:hw_legit_fanout70_distinct 1
* **cap128** — FN (76): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F3_mixed_tool_lcm_cycle 8, F4_noisy_result_repeat 8, F5_low_rate_with_heartbeat 8, F6_flood_after_legit_prefix 8, F7_startdone_rotating_permuted_ids 6, F8_oscillating_edit_same_failure 8, F9_growing_batch_repeat 8, HW:hw_flood_3tool_cycle 1, HW:hw_flood_oscillating_edit 1, HW:hw_flood_query_creep 1, HW:hw_flood_poll_then_reread 1, HW:hw_flood_same_error_retry 1, HW:hw_flood_startdone_3ids 1
  FP (0): none
* **S0** — FN (30): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F4_noisy_result_repeat 8, F7_startdone_rotating_permuted_ids 6
  FP (36): L1_poll_long_plateau 10, L5_idempotent_reread_after_write 6, L6_test_fix_rerun 9, L11_batch_polling_multi_job 10, HW:hw_legit_poll_plateau60 1
* **S0+cap64** — FN (24): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F4_noisy_result_repeat 8
  FP (40): L1_poll_long_plateau 10, L5_idempotent_reread_after_write 6, L6_test_fix_rerun 9, L8_large_fanout_distinct 3, L11_batch_polling_multi_job 10, HW:hw_legit_poll_plateau60 1, HW:hw_legit_fanout70_distinct 1
* **S1** — FN (34): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F4_noisy_result_repeat 8, F5_low_rate_with_heartbeat 2, F7_startdone_rotating_permuted_ids 7, HW:hw_flood_query_creep 1
  FP (19): L1_poll_long_plateau 8, L11_batch_polling_multi_job 10, HW:hw_legit_poll_plateau60 1
* **S2** — FN (45): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F4_noisy_result_repeat 8, F5_low_rate_with_heartbeat 8, F7_startdone_rotating_permuted_ids 8, F9_growing_batch_repeat 1, HW:hw_flood_3tool_cycle 1, HW:hw_flood_query_creep 1, HW:hw_flood_poll_then_reread 1, HW:hw_flood_same_error_retry 1
  FP (11): L11_batch_polling_multi_job 10, HW:hw_legit_poll_plateau60 1
* **diag:near_dup** — FN (35): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F3_mixed_tool_lcm_cycle 3, F7_startdone_rotating_permuted_ids 8, F9_growing_batch_repeat 8
  FP (50): L1_poll_long_plateau 10, L4_batch_fanout_repeated_subcalls 1, L5_idempotent_reread_after_write 6, L6_test_fix_rerun 10, L7_noisy_results_unchanged_state 10, L11_batch_polling_multi_job 10, HW:hw_legit_poll_plateau60 1, HW:hw_legit_repeated_subcalls_fanout 1, HW:hw_legit_noisy_poll 1
* **diag:cycle** — FN (41): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F5_low_rate_with_heartbeat 8, F7_startdone_rotating_permuted_ids 8, F9_growing_batch_repeat 8, HW:hw_flood_query_creep 1
  FP (44): L1_poll_long_plateau 10, L4_batch_fanout_repeated_subcalls 10, L7_noisy_results_unchanged_state 10, L11_batch_polling_multi_job 10, HW:hw_legit_poll_plateau60 1, HW:hw_legit_repeated_subcalls_fanout 1, HW:hw_legit_noisy_poll 1, HW:hw_legit_monitor_4_services 1
* **diag:distinct_ratio** — FN (50): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F3_mixed_tool_lcm_cycle 2, F4_noisy_result_repeat 8, F5_low_rate_with_heartbeat 2, F7_startdone_rotating_permuted_ids 6, F8_oscillating_edit_same_failure 8, F9_growing_batch_repeat 2, HW:hw_flood_3tool_cycle 1, HW:hw_flood_oscillating_edit 1, HW:hw_flood_query_creep 1, HW:hw_flood_poll_then_reread 1, HW:hw_flood_same_error_retry 1, HW:hw_flood_startdone_3ids 1
  FP (0): none
* **diag:cross_turn** — FN (70): F1_slow_drift_offset 8, F2_slow_drift_timestamp 8, F3_mixed_tool_lcm_cycle 8, F4_noisy_result_repeat 8, F5_low_rate_with_heartbeat 8, F6_flood_after_legit_prefix 8, F7_startdone_rotating_permuted_ids 8, F8_oscillating_edit_same_failure 8, HW:hw_flood_3tool_cycle 1, HW:hw_flood_oscillating_edit 1, HW:hw_flood_query_creep 1, HW:hw_flood_poll_then_reread 1, HW:hw_flood_same_error_retry 1, HW:hw_flood_startdone_3ids 1
  FP (11): L11_batch_polling_multi_job 10, HW:hw_legit_monitor_4_services 1

**Explanations (mechanism, from `results/phase1_5/mechanism_notes.txt`):**
* **FN, every policy: F1/F2 slow drift (16 floods).** Each call has a new `offset`/`since`, so all signatures are distinct; near_dup treats a changed short numeric leaf as a full change (distance 0.5 of 2 leaves > 0.1); cycle/ratio see nothing. No candidate detects them. Only a result-based signal ("same result again") could.
* **FN, state_aware: F4 noisy-result repeat (8).** Results differ each time so result hashes differ; 40 candidate flags were *suppressed* (evidence `suppressed near_dup=40`). Raw near_dup/cycle catch 8/8 - and raw near_dup/cycle/adjacent fire on L7 (10/10), the legit mirror image (noise but unchanged state). **F4 vs L7 cannot be separated by result hashes; this is the honest stress the brief asked for, and state_aware fails it in the flood direction.**
* **FN: F7 permuted start/done ids (S0 6/8, S2 8/8).** 36-60 distinct signatures, permuted every lap, so no fixed period; distinct_ratio(window 96, <=0.4) needs <= 38 distinct and only the smallest-id traces qualify. exact_dup catches all 8 (in-generation duplicates), which S* do not.
* **FN, S1/S2: F5 low-rate (S2 8/8), hw floods (S2), F9 (S2 1).** Longer required repetition trades detection for fewer FPs - the whole point of S2 - at 42 median calls latency after start.
* **FP, S0 and S1/S2: L1 long poll plateaus (S0 10, S1 8, S2 0) and hw 60-poll plateau (all S).** An identical poll with an unchanged result 9-40 times is structurally identical to a flood until the result changes; the first near_dup fire is at call 7 (8 repeats), inside the plateau. Already predicted by the Phase 1 hard case; longer plateaus are only avoided by S2's 48-repeat requirement (L1 max plateau 40 <48, hw 60 > 48 fires).
* **FP, all S: L11 batch polling of multi-job status (10/10, incl. S2 and cross_turn).** The same batch is re-issued each turn; finished jobs return unchanged `done`, so many repeated signatures have constant results and mean per-signature change score falls below 0.5 (probe: 0.11). Arguably a borderline label (we called it legitimate because the batch is bounded and ends), but it is what a monitor looks like; treat as a real FP.
* **FP, S0: L6 test-fix-rerun (9/10) and L5 write+double-read (6/10).** The detector only inspects results of the *repeated call itself*, not the intervening edits: `run_tests` results stagnate for stretches (identical hash at calls 12,15,18,21), so no suppression; in L5 double-reads give result sequences like [h1,h1,h2,h2,...] with change score (k-1)/(2k-1) just under the 0.5 suppression threshold (probe: 0.41). S1/S2 avoid these only via the higher repeat count.
* **FP, baselines/caps:** exact_dup - L4 repeated measurement sub-calls (11); adjacent3 - L1, L7 plateaus/noisy polls (23); cap64 - large fan-outs > 64 (4).
* **Diagnostics:** raw near_dup 50 FPs (41.0%), raw cycle 44 (36.1%) - confirmed unusable as guards; raw distinct_ratio had **0 FPs** (UB 3.0%) and detects 35.9% [25.3, 47.6], i.e. it would have met both numeric criteria - see note.

Note on distinct_ratio: it is registered as *diagnostic only*, so the rule forbids selecting it even though 0/122 FP and 35.9% detection would have satisfied the numbers. I did not promote it (that would be post-hoc rule-changing on burned-in-view data). It is the best candidate for a properly pre-registered v2, together with S2-style patience.

## 7. Frozen Phase 2 success/failure criteria (`docs/FROZEN_CRITERIA_PHASE2.md`, committed before results)
Flood-qualifying run (detector-independent): >=30 tool calls, distinct-signature ratio <=0.35, human-confirmed; cost-control cap 120 calls. Runs: N>=100 unguarded, >=3 scenarios, >=3 modes incl. history-primed.
* **P2-A plumbing:** >=95% valid traces/provenance, ledger within 20% of provider cost, real delta shape recorded; failure -> fix plumbing only.
* **P2-B elicitation:** >=5 flood-qualifying runs. **<5 = NULL RESULT.**
* **P2-C legit safety:** >=60 legit runs and frozen-policy interruption CP-UB <=5.0%; otherwise reported as guard FAILURE on real data.
* **P2-D detection (only if P2-B):** >=80% of flood-qualifying runs intervened, median <=40 calls after loop start; small counts -> no rate claim.
* **P2-E A/B (separate approval, only if P2-B):** >=50% fewer post-loop-start calls vs guard-off, no rise in legit failure rate.
* **Null result meaning:** "no flood elicited under these conditions" (model/provider/scenarios/N/caps reported) - NOT evidence the model cannot flood, that floods are rare, or that the guard works; guard A/B not interpretable for flood reduction; FP/interruption on legit tasks, proxy overhead and plumbing remain reportable; no real-world rate claims.
* **No optimization against Phase 2:** the frozen config will not be modified/re-selected after Phase 2 results arrive. **Because nothing qualified, nothing is frozen, so the guard-related parts of Phase 2 do not proceed without a new user decision.** Unguarded Stage-1 trace collection with cost-control stop could still be proposed separately.

## 8. Commands to reproduce
```
cd <repo> && . .venv/bin/activate           # pip install -r requirements.txt first if new
python -m floodlab.heldout                # regenerate data/heldout/heldout_v1.jsonl (sha256 must equal the one in docs/SELECTION_PROCEDURE.md)
python -m floodlab.phase1_5               # verify sha, run all policies, apply pre-registered selection -> results/phase1_5/
python -m floodlab.phase1_5 --freeze      # freezes ONLY if a policy qualifies (currently prints "Nothing qualifies -> NOT freezing")
python -m floodlab.phase1_5_errors && python -m floodlab.phase1_5_mechanisms   # post-hoc error lists / probes
python -m scripts.gate_demo               # freeze/verify/tamper demo in a temp dir
python -m pytest -q                       # 102 tests
python -m floodlab.run_offline_demo       # Phase 1 demo (dev data only)
```

## 9. Freeze-tooling / gate verification (temp dir; repo left unfrozen) - `results/phase1_5/gate_demo.txt`
```
REFUSING to run online A/B: no /tmp/tmp6wdhjhe5/frozen/MANIFEST.json: config is NOT frozen; refusing to run online A/B
REFUSING to run online A/B: frozen file CHANGED since freeze: detector_guard.frozen.yaml
REFUSING to run online A/B: no <repo>/configs/frozen/MANIFEST.json: config is NOT frozen; refusing to run online A/B
1. before freeze  -> 2 (2 = refuse)
2. manifest: {"status": "frozen", "config_id": "guard-S0", "config_hash": "1fcb0ddcae52", "files": {"detector_guard.frozen.yaml": "1b08faa5a422ab2f44a997472e84fd7690143e1b08961ab3396c2512823cc4f2", "frozen_fp_threshold.frozen.json": "9e6a6a73df83062a094dca96c3062fed8f91f87867362ae981e5e5ed12dd5e85"}}
frozen config guard-S0 (1fcb0ddcae52) verified; A/B runner is a Phase 4 deliverable and is not implemented.
3. after freeze   -> 3 (3 = verified; A/B itself not implemented)
4. after tampering with the frozen file -> 2 (2 = refuse)
5. REAL repo gate  -> 2 (2 = refuse: repo config is NOT frozen)
```
(also `tests/test_guard_freeze.py::test_ab_online_gate_accepts_frozen_and_refuses_tampered`). Stage-4 A/B not implemented or run.

## 10. Tests (real output, `results/phase1_5/pytest_summary.txt`)
```
plugins: anyio-4.15.1
collected 102 items

tests/test_detectors.py ...............................                  [ 30%]
tests/test_generators_trace.py ......                                    [ 36%]
tests/test_guard_freeze.py .............                                 [ 49%]
tests/test_harness.py ......................                             [ 70%]
tests/test_heldout_isolation.py .......                                  [ 77%]
tests/test_mock_upstream.py ......                                       [ 83%]
tests/test_phase1_5_reproduce.py ..                                      [ 85%]
tests/test_policies_stats.py .....                                       [ 90%]
tests/test_tools_scenarios.py ..........                                 [100%]

============================= 102 passed in 20.66s =============================
```
102 passed (Phase 1's 87 + 15 new: held-out isolation 7 - detector-free heldout package, dev evaluation raises on held-out traces, no dev import of held-out, sha matches pre-registration, structure/labels; policy/stats/selection-rule 5; reproduction 2; gate 1). Offline demo re-run: exit 0, "No live API calls were made. Spend: $0.00" (`results/phase1_5/demo_output.txt`).

## 11. Git ordering (pre-registration before results)
```
c15aad3 17:10:08 Phase 1.5 [5/5 analysis]: post-hoc error listing + mechanism probe (read-only), gate demo in temp dir + test, tests re-run (102 pass). No config changed; noth
baca59a 17:05:25 Phase 1.5 [4/4 results]: first (and only) held-out v1 run of all pre-registered policies; selection = NONE qualifies; nothing tuned, nothing frozen
0b58213 17:05:03 Phase 1.5 [3/4 tooling]: policies, stats, heldout_eval + runner, isolation tests (tooling smoke-tested on DEV traces only; held-out results NOT yet generated)
78c05e0 17:03:24 Phase 1.5 [2/4 pre-registration]: held-out generators+dataset (no detector run), PRIMARY_METRICS, SELECTION_PROCEDURE (target, candidates, dataset sha256), FR
e8d7a23 16:59:44 Phase 1.5 [1/4 pre-registration]: HELDOUT_DESIGN.md (design only; no held-out generator or detector run yet)
3d3d955 16:47:39 PHASE1_REPORT.md
```
Held-out dataset + pre-registration docs (`78c05e0`, 17:03) precede tooling (`0b58213`) and the first commit containing held-out results (`baca59a`, 17:05). Only the design doc preceded the generators; the dataset sha256 was registered in `78c05e0` before any detector ran on it (tooling was smoke-tested only on 4 dev traces).

## 12. Known limitations / suggested next step (not done)
* All synthetic, author-labelled; structures are templates with 8-10 near-identical seeds; CIs understate uncertainty; 13 candidates on one set (winner's-curse caveat moot since none won).
* Evidence-based directions for a v2 (would need NEW structures/seeds and a NEW pre-registration): promote distinct_ratio-style low-entropy signals to a candidate; make state-awareness model intervening writes and a "result-change fraction" threshold; combine exact_dup with S2-like patience; accept that F1/F2 and F4-vs-L7 need result-content/semantic signals, and consider client caps + human-in-the-loop rather than automated cancel for poll-like tasks.

## 13. Spend / network
`spend_ledger.jsonl`: 9 rows, all `usd: 0.0, live_call: false` (mock loopback). All tests run under a socket guard that fails non-loopback connects. No OpenRouter/MiMo/other provider contacted; no secrets read or requested. **$0.00.**
