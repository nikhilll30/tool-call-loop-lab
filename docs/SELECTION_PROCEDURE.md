# Selection and freeze procedure - pre-registered (Phase 1.5). Committed BEFORE any detector/policy was run on held-out v1.

Held-out v1 dataset sha256 (built, no detector run yet): `a39c0cf82d37c3a3c78b162fd3e5a972421f6602eced6b336ba01ef5b8c69a7b`
(`data/heldout/heldout_v1.jsonl`, 200 traces: 78 flood, 122 legitimate; regenerate with `python -m floodlab.heldout`).

## 1. Candidate policies (fixed now; no others will be evaluated for selection)
Selectable (13):
| id | definition |
|---|---|
| exact_dup | Phase 1 baseline `exact_dup` (>=2 repeats of an exact call within one generation) |
| adjacent3 | Phase 1 baseline: last 3 calls identical |
| cap64 | intervene at the 65th call of any generation |
| cap128 | intervene at the 129th call of any generation |
| S0, S0+cap64, S0+cap128 | `state_aware` with the Phase 1 dev config `draft-0.1` (hash `b1baa129b8d2`), alone / with a cap |
| S1, S1+cap64, S1+cap128 | `state_aware` "moderate": as S0 but near_dup.window=96, near_dup.min_repeats=24, cycle.min_len=24, distinct_ratio.window=128, cross_turn.min_streak=4 |
| S2, S2+cap64, S2+cap128 | `state_aware` "patient": as S0 but near_dup.window=128, near_dup.min_repeats=48, cycle.min_len=48, distinct_ratio.window=192, cross_turn.min_streak=6 |

`state_aware` = the four new detectors (near_dup, cycle, distinct_ratio, cross_turn) with result-hash state suppression on
(`state_change_frac`=0.5), policy intervention = earliest firing among them. "+capN" = earliest of that and the cap.
S1/S2 were designed from the dev results and general reasoning (longer required repetition => fewer plateau false positives, more latency);
they were NOT tuned on held-out data, which nobody has run.

Diagnostics only (reported, NEVER selectable, regardless of results): raw `near_dup`, raw `cycle`, raw `distinct_ratio`, raw `cross_turn`,
`combined_raw` (four new detectors without state) under `draft-0.1`, and `state_blind` variants nowhere else. Per the brief raw near_dup and raw cycle
are diagnostic signals, not standalone guards, "unless further evidence supports them"; the evidence would have to come from a new
pre-registered validation, not from this one.

## 2. Target (stated in advance)
The **upper bound of the Clopper-Pearson two-sided 95% CI on the legitimate interruption rate** (= FP rate) must be **<= 5.0%**.
With n_legit = 122: 0 FPs -> UB ~ 3.0%, 1 FP -> ~4.5% (qualifies), 2 FPs -> ~5.8% (does not qualify). Computed exactly by code.
Minimum utility floor: point estimate of flood detection >= **30%** (a policy that qualifies on FP by never firing is not frozen).

## 3. Selection rule
1. Compute, for each selectable candidate, the four primary metrics on held-out v1 exactly as in `docs/PRIMARY_METRICS.md`.
2. Keep candidates with legit interruption UB <= 5.0% AND detection >= 30%. ("qualifying")
3. Among qualifying candidates choose the one with the **highest flood detection rate** (point estimate over all 78 floods).
   Tie-breaks in order: (a) lower median `latency_after_start` (misses counted as trace length); (b) fewer components (a cap counts as one);
   (c) lexicographically smaller id.
4. Freeze the chosen candidate: `python -m floodlab.freeze freeze` after writing the chosen suite/cap into
   `configs/frozen/detector_guard.DRAFT.yaml` and the target into `frozen_fp_threshold.DRAFT.json` (`max_fp_rate` = 0.05, plus the UB method).
   `MANIFEST.json` records hashes. Then verify `python -m floodlab.ab_online` accepts it and refuses after a modification (tested).
5. Caveats stated in advance: 13 candidates are compared on one set with no multiplicity correction, so the winner's FP/detection are
   optimistically biased ("winner's curse"); dependence within structures (see PRIMARY_METRICS); flood detection for the winner is measured on the
   same flood set used in the ranking. The numbers are offline validation on synthetic traces, not evidence of real-world performance.

## 4. If none qualifies
Report exactly that. **Do not freeze anything into `configs/frozen/`** (the online A/B gate keeps refusing), do not retune, and do not
present a "least bad" candidate as validated. Any later change to detectors/thresholds/candidate grid after seeing held-out v1 results makes
**held-out v1 BURNED**: its numbers may be shown only as "diagnostic, post-tuning, not clean", and a clean confirmation requires a NEW held-out split
(new seeds AND new structures) with its own pre-registration committed before it is run. The freeze tooling itself is still exercised in a temporary
directory by the tests. Deciding whether to build such a v2 is left to the user.

## 5. Things that will NOT be done
No editing of ground-truth labels or loop_start after seeing results (label errors found later are reported as such, listed, and NOT corrected in the
scored data). No dropping of traces. No changing the target, floor, candidates or tie-breaks.

## 6. Independence of dev and held-out
Dev = Phase 1 generators (`floodlab/gen/`), seeds 0-9 / 100-109, `data/traces/`. Held-out = `floodlab/heldout/`, seeds 1000-1009,
`data/heldout/`, trace `split == "heldout"`. `floodlab/evaluate.py` (dev evaluation) refuses traces with `split == "heldout"`; a test checks it and that
no module in `floodlab/heldout/` imports detectors.
