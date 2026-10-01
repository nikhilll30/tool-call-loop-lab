# Four evaluation stages (kept separate in code)

| Stage | What | Code | Status |
|---|---|---|---|
| 1 Trace collection | mock/live runs -> JSONL with provenance | `floodlab/harness.py`, `mock_upstream/`, `gen/` (synthetic) | tooling done; only synthetic + mock-upstream traces exist. **No live traces.** |
| 2 Offline detector dev/eval | detectors run over traces; dev/test seed split | `floodlab/detectors/`, `floodlab/evaluate.py` | done on SYNTHETIC data only |
| 3 Freeze | versioned config + `frozen_fp_threshold`, hash-verified | `floodlab/freeze.py`, `configs/frozen/` | tooling done; **config is a DRAFT, nothing is frozen** |
| 4 Online guard A/B | guard off vs on with frozen config only | `floodlab/guard/` (skeleton), `floodlab/ab_online.py` (gate only) | skeleton + gate only; **A/B not implemented, not run** |

## Dev/test split (synthetic circularity)
* Dev seeds `0-9`: thresholds may be inspected/tuned. Test seeds `100-109`: held out; reported separately.
  Hand-written legit set (6 traces): split `none`, reported on its own.
* **Honest caveat:** the generators are structurally identical across seeds (seed changes names/ids/lengths, not the shape),
  so dev and test results are near-identical by construction. The split guards against per-seed overfitting only;
  it does NOT make synthetic results evidence about real models. The draft thresholds were set by hand from the documented
  shapes (period <= 128, >=3 reps, window 96, ...) and then inspected on dev; they have not been fit to test seeds.
  Real validity requires Stage 1 live traces (Phase 2) evaluated with the config frozen first.
* Legit families were written knowing the detectors' state-awareness; a zero FP for the state-aware detector on them is
  partly by construction. The hand-written HARD case (poll plateau) shows the residual failure mode.

## Freezing rules
`python -m floodlab.freeze freeze` copies `*.DRAFT.*` -> `*.frozen.*` and writes `MANIFEST.json` (sha256s + config hash).
`floodlab.ab_online` (Stage 4) and `require_frozen()` refuse to run if the manifest is missing or any file changed.
Do not freeze until (a) Stage 2 on real traces is done and (b) `frozen_fp_threshold` (max FP rate on the legitimate suite)
is fixed. The guard is to be judged only against that pre-frozen threshold.
