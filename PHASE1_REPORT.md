# PHASE 1 REPORT - Tool-Call Flood and Repetition Lab (zero-cost, offline portion)

> **Historical report of an earlier phase.** Test counts, file listings and paths in this document describe that phase and may differ from the current repository (current test count: see `README.md`). References to files that are not in this repository (for example `spend_ledger.jsonl`, `evidence/`, `PHASE0_REPORT.md`) point to private material that is not published.

Generated 2026-09-29 16:47 EDT. Repo: `<repo>/` (git, local commits only, no remote).
**No live API calls were made and $0.00 was spent.** Everything below ran offline against a local mock upstream on 127.0.0.1.
All flood/legitimate traces are **SYNTHETIC**; no number here is a real-world rate. Vendor figures in the Phase 0 background report (not published) are vendor-reported.

## 1. What was built
* **Trace format** `floodlab.trace/1` (JSONL, `docs/TRACE_SCHEMA.md`): provenance (model, endpoint, scenario, seed, detector config id/hash, guard config id/hash or `off`, prompt + tool-schema version), per-turn messages, per-generation tool calls (name, canonical args, timestamp, result hash), latency, cost, termination reason.
* **Mock tools + scenarios** (`floodlab/tools.py`, `scenarios.py`): pagination, error-fallback, fan-out, fix-loop, missing-path, multi-hop; modes plain / history-primed / rotating-argument / A-B alternating / cross-turn; deterministic per seed with simulated external state (job progress, file edits).
* **Synthetic floods** (`gen/floods.py`): rotating-35 (4120 calls, one generation), rotating-35 across generations, start/done alternation, A,B,C cycles (1 gen and multi-gen), near-duplicate with incrementing timestamp, cross-turn identical batches, cancel-then-identical-retry (#2509: 17-call batch x10).
* **Legitimate negative controls** (`gen/legit.py`, `gen/handwritten.py`): 7 generated families (cursor pagination, retries with changing args, 20-40 call parallel fan-out, polling with changing state, alternating run_tests/edit_file, identical reads with state change, batched polling) x 20 seeds + 6 hand-written traces (2 are deliberately hard).
* **Detectors** (`floodlab/detectors/`): baselines (Xiaomi-style within-generation exact-dup; last-N-identical), near-duplicate (volatile-field-aware), cycle (period <=128 within/across generations), distinct-ratio/entropy, cross-turn, state-aware suppression by result hashes. Structured result: flag, first index, reason code, evidence. Dataclass configs with stable hash.
* **Offline eval** (`floodlab/evaluate.py`): per-shape detection, FP per family, baseline-miss table, plot; dev seeds 0-9 / test seeds 100-109 recorded in `docs/EVALUATION_STAGES.md`.
* **Freeze tooling** (`floodlab/freeze.py`, `configs/frozen/`): DRAFT config + DRAFT `frozen_fp_threshold`, sha256 manifest, `ab_online` gate that refuses to run. **Nothing is frozen.**
* **Mock upstream** (`mock_upstream/app.py`): FastAPI `/v1/chat/completions` SSE; whole-call and incremental tool-call deltas; `reasoning_content`; SSE comment lines; `usage` chunk before `[DONE]`; enforces reasoning pass-back (HTTP 400 if missing); records tokens "generated" at client disconnect.
* **Harness** (`floodlab/harness.py`): any OpenAI-compatible base_url (mock by default; non-loopback refused without `--allow-network` and a positive budget); turn/call/token caps; budget guard; spend ledger; stop-early hook; provenance traces.
* **Guard proxy skeleton** (`floodlab/guard/`): buffers tool-call deltas, per-generation cap, detector-based cancel (closes upstream), `finish_reason` + structured `floodlab_guard` object, hard stop after N identical batches (#2509). Tested only against the mock.

## 2. Project and file structure
```
./.gitignore
./Makefile
./PHASE0_REPORT.md   (not published in this repository)
./README.md
./configs/frozen/detector_guard.DRAFT.yaml
./configs/frozen/frozen_fp_threshold.DRAFT.json
./cost_model.py
./cost_model_output.json
./docs/EVALUATION_STAGES.md
./docs/TRACE_SCHEMA.md
./floodlab/__init__.py
./floodlab/ab_online.py
./floodlab/canon.py
./floodlab/config.py
./floodlab/detectors/__init__.py
./floodlab/detectors/base.py
./floodlab/detectors/baselines.py
./floodlab/detectors/cross_turn.py
./floodlab/detectors/cycle.py
./floodlab/detectors/distinct_ratio.py
./floodlab/detectors/near_dup.py
./floodlab/detectors/stream.py
./floodlab/evaluate.py
./floodlab/freeze.py
./floodlab/gen/__init__.py
./floodlab/gen/common.py
./floodlab/gen/floods.py
./floodlab/gen/handwritten.py
./floodlab/gen/legit.py
./floodlab/gen/suites.py
./floodlab/guard/__init__.py
./floodlab/guard/__main__.py
./floodlab/guard/proxy.py
./floodlab/harness.py
./floodlab/mock_upstream/__init__.py
./floodlab/mock_upstream/__main__.py
./floodlab/mock_upstream/app.py
./floodlab/run_offline_demo.py
./floodlab/scenarios.py
./floodlab/servers.py
./floodlab/smoke.py
./floodlab/sse.py
./floodlab/tools.py
./floodlab/trace.py
./pytest.ini
./requirements.txt
./results/baseline_vs_new.png
./results/demo_output.txt
./results/eval_report.md
./results/example_outputs.txt
./results/per_trace.csv
./results/pytest_verbose.txt
./results/smoke_traces.jsonl
./results/summary.json
./scripts/__init__.py
./scripts/example_outputs.py
./spend_ledger.jsonl   (not published in this repository)
./tests/conftest.py
./tests/test_detectors.py
./tests/test_generators_trace.py
./tests/test_guard_freeze.py
./tests/test_harness.py
./tests/test_mock_upstream.py
./tests/test_tools_scenarios.py
```
(`data/traces/*.jsonl` are regenerated by the demo and git-ignored; `or_*.json`, `ep_tmp.json`, `evidence/` are Phase 0 artifacts (not published in this repository).)

## 3. Exact commands used
```bash
cd <repo>
python3 -m venv .venv && . .venv/bin/activate
pip install fastapi uvicorn httpx pytest matplotlib pyyaml numpy     # then pinned in requirements.txt (fastapi==0.142.0, uvicorn==0.54.0, httpx==0.28.1, ...)
python -m pytest -q                              # tests
python -m floodlab.run_offline_demo              # ONE-COMMAND DEMO (also: make demo, if make is installed - it was NOT on this box, I ran the python command)
python -m scripts.example_outputs > results/example_outputs.txt     # sections 5-7 below
python -m floodlab.ab_online                     # Stage 4 gate -> refuses (exit 2)
```
Demo output (real, `results/demo_output.txt`):
```
== Stage 1' - synthetic trace generation (SYNTHETIC; not real-world) ==
wrote 306 traces to data/traces/synthetic_all.jsonl (flood=160, legitimate=146)

== Stage 2 - offline detector evaluation ==
suite=draft-0.1 hash=b1baa129b8d2; wrote results/eval_report.md, per_trace.csv, summary.json, baseline_vs_new.png

False-positive rate on legitimate suite (all splits, n=146):
  exact_dup       0.137
  adjacent        0.288
  near_dup        0.562
  cycle           0.281
  distinct_ratio  0.000
  cross_turn      0.000
  combined_raw    0.562
  state_aware     0.007

Baseline-miss table (TEST seeds, SYNTHETIC):
| shape | n | max_adjacent_run(median) | exact_dup | adjacent | new_detectors_raw | state_aware | both_baselines_miss | caught_by_new_raw | caught_by_state_aware | median_first_idx_exact_dup | median_first_idx_state_aware |
|---|---|---|---|---|---|---|---|---|---|---|---|
| abc_cycle_multi_gen | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 8 |
| abc_cycle_one_gen | 10 | 1 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 4 | 8 |
| cancel_retry_2509 | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 50 |
| cross_turn_identical_batches | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 35 |
| near_dup_counter | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 7 |
| rotating35_multi_gen | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 95 |
| rotating35_one_gen | 10 | 1 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 36 | 95 |
| start_done_alternation | 10 | 1 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 71 | 209 |

== Stage 3 - freeze tooling status (DRAFT only; nothing is frozen) ==
NOT FROZEN (no <repo>/configs/frozen/MANIFEST.json: config is NOT frozen; refusing to run online A/B).
  draft config guard-draft-0.1 hash=40f1ef0a81be (DRAFT: online A/B will refuse to run)

== Stage 4 tooling smoke test: mock upstream + harness + guard (loopback only, $0) ==
  normal run   : completed, turns=10, valid=True
  flood, guard OFF (incremental deltas): 300 calls executed, termination=completed
  flood, guard ON: 0 calls reached tools, termination=guard_stop:MAX_CALLS_PER_GENERATION, guard reason=MAX_CALLS_PER_GENERATION via cap after 65 calls
  upstream saw 1 client disconnect(s); tokens 'generated' at disconnect: [1070] (planned [4772])
  wrote results/smoke_traces.jsonl (mock-upstream runs; SYNTHETIC)

DONE. No live API calls were made. Spend: $0.00
```

## 4. Tests executed and results
`python -m pytest` (real output):
```
testpaths: tests
plugins: anyio-4.15.1
collected 87 items

tests/test_detectors.py ...............................                  [ 35%]
tests/test_generators_trace.py ......                                    [ 42%]
tests/test_guard_freeze.py ............                                  [ 56%]
tests/test_harness.py ......................                             [ 81%]
tests/test_mock_upstream.py ......                                       [ 88%]
tests/test_tools_scenarios.py ..........                                 [100%]

============================= 87 passed in 11.85s ==============================
```
Tests per file (`pytest --co`):
```
     31 tests/test_detectors.py
      6 tests/test_generators_trace.py
     12 tests/test_guard_freeze.py
     22 tests/test_harness.py
      6 tests/test_mock_upstream.py
     10 tests/test_tools_scenarios.py
```
Full per-test list in `results/pytest_verbose.txt` (87 PASSED, 0 failed). A conftest fixture fails any test that tries a non-loopback socket connect.
Initial run had 7 failures (a `multi_hop` oracle bug - kwarg named `name` collided with a tool argument `name`, two test-assumption bugs); all fixed before the final run above. Notably, the first hard-stop test showed the cross-turn/cycle detectors fire *before* the batch counter under default config, so the counter test disables the detectors to isolate it, and a second test asserts the detectors alone stop the #2509 loop.

## 5. Example pathological loop trace
Two SYNTHETIC excerpts (full traces: `data/traces/synthetic_all.jsonl` after the demo). **A** is the rotating-35 shape spread over 20 generations (evades BOTH baselines). **B** is the #2482 one-generation shape (4120 calls; evades the adjacent guard, but is caught by within-generation exact-dup counting).

```
=== PATHOLOGICAL A: rotating-35 over 20 generations (evades exact-dup AND adjacent)
==============================================================================================================
run_id=flood-rot35-mg-100 label=flood shape=rotating35_multi_gen split=test synthetic=True
note=SYNTHETIC: 35 rotating inputs spread over generations short enough that no generation contains an exact duplicate
provenance={"detector_config": {"hash": null, "id": null}, "endpoint": "none", "guard_config": "off", "model": "synthetic-generator", "prompt_version": "n/a", "scenario": "synthetic", "seed": 100, "tool_schema_version": "n/a"}
turns=20 generations=20 total_calls=400 distinct(name,args)=35
generation sizes: [20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20, 20] ...
first calls (gidx turn gen idx | name args | result_hash):
     0 t0 g0 #0  | list_dir {"path":"list_dir_0_7528"} | 1a5bdb28f69f7ad2
     1 t0 g0 #1  | get_doc {"id":"get_doc_1_2863"} | f57d5787b9889374
     2 t0 g0 #2  | get_doc {"id":"get_doc_2_5730"} | 7aa90b0a90127af4
     3 t0 g0 #3  | get_doc {"id":"get_doc_3_8304"} | 77306456334d5612
     4 t0 g0 #4  | read_file {"path":"read_file_4_8731"} | 6daf82c7c7944463
     5 t0 g0 #5  | read_file {"path":"read_file_5_1313"} | 9cca6200befc1c4a
     6 t0 g0 #6  | get_doc {"id":"get_doc_6_4315"} | f2b16f0ae8dfc2d0
     7 t0 g0 #7  | read_file {"path":"read_file_7_3350"} | 1a7692b387df6d5f
     8 t0 g0 #8  | search {"query":"search_8_3763"} | bab02e765d1f71ef
     9 t0 g0 #9  | search {"query":"search_9_3340"} | 0a58e6bae00eb498
  ...
   397 t19 g0 #17 | search {"query":"search_12_6712"} | 9a4f115ab1efaedc
   398 t19 g0 #18 | list_dir {"path":"list_dir_13_6603"} | 5ac8b8a3b84f2083
   399 t19 g0 #19 | get_doc {"id":"get_doc_14_9099"} | 0546d29277a6c1a5
raw JSONL record (first turn, truncated to first 2 tool calls):
{"cost_usd": 0.0, "label": "flood", "latency_s": 20.0, "notes": "SYNTHETIC: 35 rotating inputs spread over generations short enough that no generation contains an exact duplicate", "provenance": {"detector_config": {"hash": null,  …[line truncated for width]

detector        flag  first_idx  reason / evidence
exact_dup       False      None  OK {"max_dups_in_a_generation": 0}
adjacent        False      None  OK {"max_adjacent_run": 1}
near_dup        False      None  OK {"suppressed_candidates": 0}
cycle           True        104  CYCLE {"pattern": ["list_dir|{\"path\":\"list_dir_0_7528\"}", "get_doc|{\"id\":\"get_doc_1_2863\"}", "get_doc|{\"id\":\"get_doc_2_5730\"}", "get_doc|{\"id\":\"get_doc_3_8304\"}", "read_file|{\"path …[line truncated for width]
distinct_ratio  True         95  LOW_DISTINCT_RATIO {"distinct": 35, "norm_entropy": 0.776, "ratio": 0.365, "suppressed_before": 0, "window": 96}
cross_turn      False      None  OK {"max_similarity": 0.143, "suppressed_candidates": 0}
combined_raw    True         95  LOW_DISTINCT_RATIO {"earliest": "distinct_ratio", "fired": {"cycle": 104, "distinct_ratio": 95}}
state_aware     True         95  LOW_DISTINCT_RATIO {"earliest": "distinct_ratio", "fired": {"cycle": 104, "distinct_ratio": 95}, "suppressed": {"cross_turn": 0, "cycle": 0, "distinct_ratio": 0, "near_dup": 0}}

```
(Block B's trace excerpt and detector output are in section 7.)

## 6. Example legitimate repeated-work trace
SYNTHETIC polling trace: the identical call `get_job_status {"job":"build"}` repeated 10 times, external state changing (distinct result hashes).
```
=== LEGITIMATE: polling with changing external state (one call per turn)
==============================================================================================================
run_id=legit-polling-100 label=legitimate shape=polling_state_changes split=test synthetic=True
note=SYNTHETIC: identical poll each turn; external state (progress) changes
provenance={"detector_config": {"hash": null, "id": null}, "endpoint": "none", "guard_config": "off", "model": "synthetic-generator", "prompt_version": "n/a", "scenario": "synthetic", "seed": 100, "tool_schema_version": "n/a"}
turns=10 generations=10 total_calls=10 distinct(name,args)=1
generation sizes: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1] 
first calls (gidx turn gen idx | name args | result_hash):
     0 t0 g0 #0  | get_job_status {"job":"build"} | 8f7a842d87172e65
     1 t1 g0 #0  | get_job_status {"job":"build"} | 2eb07e45236d7d61
     2 t2 g0 #0  | get_job_status {"job":"build"} | 38b1080ca2cb4494
     3 t3 g0 #0  | get_job_status {"job":"build"} | 108277431fcdcbd4
     4 t4 g0 #0  | get_job_status {"job":"build"} | a7b475a1da877632
     5 t5 g0 #0  | get_job_status {"job":"build"} | 58768ca524aa7fdf
     6 t6 g0 #0  | get_job_status {"job":"build"} | 9c5f6267b541ad91
     7 t7 g0 #0  | get_job_status {"job":"build"} | 275046b3bc28b40e
     8 t8 g0 #0  | get_job_status {"job":"build"} | a20ee5156184401c
     9 t9 g0 #0  | get_job_status {"job":"build"} | 27927a8d408465ed
  ...
     7 t7 g0 #0  | get_job_status {"job":"build"} | 275046b3bc28b40e
     8 t8 g0 #0  | get_job_status {"job":"build"} | a20ee5156184401c
     9 t9 g0 #0  | get_job_status {"job":"build"} | 27927a8d408465ed
raw JSONL record (first turn, truncated to first 2 tool calls):
{"cost_usd": 0.0, "label": "legitimate", "latency_s": 6.2, "notes": "SYNTHETIC: identical poll each turn; external state (progress) changes", "provenance": {"detector_config": {"hash": null, "id": null}, "endpoint": "none", "guard …[line truncated for width]

detector        flag  first_idx  reason / evidence
exact_dup       False      None  OK {"max_dups_in_a_generation": 0}
adjacent        True          2  ADJACENT_IDENTICAL_RUN {"call": "get_job_status", "run": 3}
near_dup        True          7  NEAR_DUPLICATE_ARGS {"max_dist": 0.1, "near_dups_in_window": 8, "suppressed_before": 0, "tool": "get_job_status", "window": 64}
cycle           True          7  CYCLE {"pattern": ["get_job_status|{\"job\":\"build\"}"], "period": 1, "repeats": 8.0, "span_calls": 8, "start_index": 0, "suppressed_before": 0}
distinct_ratio  False      None  OK {"note": "fewer calls than window"}
cross_turn      False      None  OK {"max_similarity": 0.0, "suppressed_candidates": 0}
combined_raw    True          7  NEAR_DUPLICATE_ARGS {"earliest": "near_dup", "fired": {"cycle": 7, "near_dup": 7}}
state_aware     False      None  OK {"suppressed": {"cross_turn": 0, "cycle": 3, "distinct_ratio": 0, "near_dup": 3}}

```

## 7. Detector output on both traces (real)
See the `detector` tables directly under each trace in sections 5 and 6. Additionally, the #2482 one-generation shape (B) and the paginate control:
```
=== PATHOLOGICAL B: #2482 shape, ONE generation, 4120 calls, 35 rotating inputs
==============================================================================================================
run_id=flood-rot35-1g-100 label=flood shape=rotating35_one_gen split=test synthetic=True
note=SYNTHETIC #2482 shape: one generation, 35 rotating distinct inputs, max adjacent-identical run 1
provenance={"detector_config": {"hash": null, "id": null}, "endpoint": "none", "guard_config": "off", "model": "synthetic-generator", "prompt_version": "n/a", "scenario": "synthetic", "seed": 100, "tool_schema_version": "n/a"}
turns=1 generations=1 total_calls=4120 distinct(name,args)=35
generation sizes: [4120] 
first calls (gidx turn gen idx | name args | result_hash):
     0 t0 g0 #0  | list_dir {"path":"list_dir_0_7528"} | 1a5bdb28f69f7ad2
     1 t0 g0 #1  | get_doc {"id":"get_doc_1_2863"} | f57d5787b9889374
     2 t0 g0 #2  | get_doc {"id":"get_doc_2_5730"} | 7aa90b0a90127af4
     3 t0 g0 #3  | get_doc {"id":"get_doc_3_8304"} | 77306456334d5612
     4 t0 g0 #4  | read_file {"path":"read_file_4_8731"} | 6daf82c7c7944463
     5 t0 g0 #5  | read_file {"path":"read_file_5_1313"} | 9cca6200befc1c4a
     6 t0 g0 #6  | get_doc {"id":"get_doc_6_4315"} | f2b16f0ae8dfc2d0
     7 t0 g0 #7  | read_file {"path":"read_file_7_3350"} | 1a7692b387df6d5f
     8 t0 g0 #8  | search {"query":"search_8_3763"} | bab02e765d1f71ef
     9 t0 g0 #9  | search {"query":"search_9_3340"} | 0a58e6bae00eb498
  ...
  4117 t0 g0 #4117| get_doc {"id":"get_doc_22_2074"} | 1c84b193695cb8d8
  4118 t0 g0 #4118| read_file {"path":"read_file_23_9979"} | 483b31cfa4cfbb6e
  4119 t0 g0 #4119| list_dir {"path":"list_dir_24_8308"} | c44752a284059d3c
raw JSONL record (first turn, truncated to first 2 tool calls):
{"cost_usd": 0.0, "label": "flood", "latency_s": 83.0, "notes": "SYNTHETIC #2482 shape: one generation, 35 rotating distinct inputs, max adjacent-identical run 1", "provenance": {"detector_config": {"hash": null, "id": null}, "end …[line truncated for width]

detector        flag  first_idx  reason / evidence
exact_dup       True         36  EXACT_DUP_WITHIN_GENERATION {"dups_at_fire": 2, "gen": 0, "generation_len": 4120, "turn": 0}
adjacent        False      None  OK {"max_adjacent_run": 1}
near_dup        False      None  OK {"suppressed_candidates": 0}
cycle           True        104  CYCLE {"pattern": ["list_dir|{\"path\":\"list_dir_0_7528\"}", "get_doc|{\"id\":\"get_doc_1_2863\"}", "get_doc|{\"id\":\"get_doc_2_5730\"}", "get_doc|{\"id\":\"get_doc_3_8304\"}", "read_file|{\"path …[line truncated for width]
distinct_ratio  True         95  LOW_DISTINCT_RATIO {"distinct": 35, "norm_entropy": 0.776, "ratio": 0.365, "suppressed_before": 0, "window": 96}
cross_turn      False      None  OK {"max_similarity": 0.0, "suppressed_candidates": 0}
combined_raw    True         95  LOW_DISTINCT_RATIO {"earliest": "distinct_ratio", "fired": {"cycle": 104, "distinct_ratio": 95}}
state_aware     True         95  LOW_DISTINCT_RATIO {"earliest": "distinct_ratio", "fired": {"cycle": 104, "distinct_ratio": 95}, "suppressed": {"cross_turn": 0, "cycle": 0, "distinct_ratio": 0, "near_dup": 0}}


=== LEGITIMATE: paginate with changing cursor
==============================================================================================================
run_id=legit-pagination-100 label=legitimate shape=pagination_cursor split=test synthetic=True
note=SYNTHETIC: one call per turn, changing cursor
provenance={"detector_config": {"hash": null, "id": null}, "endpoint": "none", "guard_config": "off", "model": "synthetic-generator", "prompt_version": "n/a", "scenario": "synthetic", "seed": 100, "tool_schema_version": "n/a"}
turns=28 generations=28 total_calls=28 distinct(name,args)=28
generation sizes: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1] ...
first calls (gidx turn gen idx | name args | result_hash):
     0 t0 g0 #0  | list_items {"cursor":"0"} | af9600d5fb8d01a7
     1 t1 g0 #0  | list_items {"cursor":"5"} | 630066d5b58a2bb2
     2 t2 g0 #0  | list_items {"cursor":"10"} | 7b278520d129f768
     3 t3 g0 #0  | list_items {"cursor":"15"} | b92258e13d45c956
     4 t4 g0 #0  | list_items {"cursor":"20"} | c0391459529bea3b
     5 t5 g0 #0  | list_items {"cursor":"25"} | 3eb27e9e3f958c36
     6 t6 g0 #0  | list_items {"cursor":"30"} | a39323e24bb6ae6d
     7 t7 g0 #0  | list_items {"cursor":"35"} | f66c3a4e40338c61
     8 t8 g0 #0  | list_items {"cursor":"40"} | 4284053ffe305ef5
     9 t9 g0 #0  | list_items {"cursor":"45"} | ea28d2b7559d2cad
  ...
    25 t25 g0 #0  | list_items {"cursor":"125"} | 159f37d88b50b311
    26 t26 g0 #0  | list_items {"cursor":"130"} | ffd9fe2f6590ced2
    27 t27 g0 #0  | list_items {"cursor":"135"} | e01f6119aafd14b3
raw JSONL record (first turn, truncated to first 2 tool calls):
{"cost_usd": 0.0, "label": "legitimate", "latency_s": 17.36, "notes": "SYNTHETIC: one call per turn, changing cursor", "provenance": {"detector_config": {"hash": null, "id": null}, "endpoint": "none", "guard_config": "off", "model …[line truncated for width]

detector        flag  first_idx  reason / evidence
exact_dup       False      None  OK {"max_dups_in_a_generation": 0}
adjacent        False      None  OK {"max_adjacent_run": 1}
near_dup        False      None  OK {"suppressed_candidates": 0}
cycle           False      None  OK {"suppressed_candidates": 0}
distinct_ratio  False      None  OK {"note": "fewer calls than window"}
cross_turn      False      None  OK {"max_similarity": 0.0, "suppressed_candidates": 0}
combined_raw    False      None  OK {}
state_aware     False      None  OK {"suppressed": {"cross_turn": 0, "cycle": 0, "distinct_ratio": 0, "near_dup": 0}}
```

Interpretation: on the pathological trace A both baselines are silent (exact_dup max dups 0; adjacent max run 1) while distinct_ratio (idx 95) and cycle (period 35, idx 104) fire and the state-aware combination keeps the flag (all results identical for identical calls, so nothing to suppress). On the legitimate polling trace the raw near_dup/cycle/adjacent detectors all false-positive, and the state-aware combination correctly suppresses (results differ between calls). Suppression counts are in the `suppressed` evidence.

### Full offline results (SYNTHETIC; TEST seeds 100-109, n=10 per shape/family)
Flood detection rate:
| shape | n | exact_dup | adjacent | near_dup | cycle | distinct_ratio | cross_turn | combined_raw | state_aware |
|---|---|---|---|---|---|---|---|---|---|
| abc_cycle_multi_gen | 10 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| abc_cycle_one_gen | 10 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 |
| cancel_retry_2509 | 10 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| cross_turn_identical_batches | 10 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 |
| near_dup_counter | 10 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 |
| rotating35_multi_gen | 10 | 0.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 |
| rotating35_one_gen | 10 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 |
| start_done_alternation | 10 | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 | 1.00 | 1.00 |
| **OVERALL** | 80 | 0.38 | 0.00 | 0.38 | 1.00 | 0.38 | 0.38 | 1.00 | 1.00 |

False-positive rate on legitimate families:
| family | n | exact_dup | adjacent | near_dup | cycle | distinct_ratio | cross_turn | combined_raw | state_aware |
|---|---|---|---|---|---|---|---|---|---|
| alternating_read_write | 10 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| batched_polling_state_changes | 10 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| identical_calls_state_changed | 10 | 0.00 | 0.00 | 1.00 | 0.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| pagination_cursor | 10 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| parallel_fanout | 10 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| polling_state_changes | 10 | 0.00 | 1.00 | 1.00 | 1.00 | 0.00 | 0.00 | 1.00 | 0.00 |
| retries_changing_args | 10 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **OVERALL** | 70 | 0.14 | 0.29 | 0.57 | 0.29 | 0.00 | 0.00 | 0.57 | 0.00 |

Hand-written legit set (True = false positive):
| trace | exact_dup | adjacent | near_dup | cycle | distinct_ratio | cross_turn | combined_raw | state_aware |
|---|---|---|---|---|---|---|---|---|
| hw-legit-paginate | False | False | False | False | False | False | False | False |
| hw-legit-fanout25 | False | False | False | False | False | False | False | False |
| hw-legit-backoff | False | False | False | False | False | False | False | False |
| hw-legit-hard-poll-plateau | False | True | True | True | False | False | True | True |
| hw-legit-rwt-cycle | False | False | True | False | False | False | True | False |
| hw-legit-repeat-search | False | True | False | False | False | False | False | False |

Baseline-miss table (TEST seeds):
| shape | n | max_adjacent_run(median) | exact_dup | adjacent | new_detectors_raw | state_aware | both_baselines_miss | caught_by_new_raw | caught_by_state_aware | median_first_idx_exact_dup | median_first_idx_state_aware |
|---|---|---|---|---|---|---|---|---|---|---|---|
| abc_cycle_multi_gen | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 8 |
| abc_cycle_one_gen | 10 | 1 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 4 | 8 |
| cancel_retry_2509 | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 50 |
| cross_turn_identical_batches | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 35 |
| near_dup_counter | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 7 |
| rotating35_multi_gen | 10 | 1 | 0.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | None | 95 |
| rotating35_one_gen | 10 | 1 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 36 | 95 |
| start_done_alternation | 10 | 1 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 71 | 209 |

False-positive rate on legitimate suite (all splits, n=146):
  exact_dup       0.137
  adjacent        0.288
  near_dup        0.562
  cycle           0.281
  distinct_ratio  0.000
  cross_turn      0.000
  combined_raw    0.562
  state_aware     0.007


DEV-seed and TEST-seed numbers are identical here because the generators are structurally the same across seeds (see `docs/EVALUATION_STAGES.md`); the split is a hygiene measure, not independent validation.

## 8. Known limitations
* All data synthetic; the shapes were written by us from the issue descriptions, and detector defaults were set by hand knowing those shapes. 100% detection on synthetic floods is expected and is **not** evidence of real-world performance. No real trace has been evaluated.
* The single-generation #2482 shape is caught by the Xiaomi-style exact-dup baseline (35 distinct inputs => 4,085 repeats); it defeats only the last-N-adjacent guard. The exact-dup baseline is blind to cross-generation, near-duplicate, and cancelled-retry shapes (5 of 8 shapes here). Online, exact-dup can fire earlier than the new detectors on rotating-35 (idx 36 vs 95), because new detectors need a full window / 3 reps. Detection latency (calls wasted) is a real trade-off not yet tuned.
* Raw near_dup / cycle / adjacent have large FP rates on legitimate suites (0.56 / 0.28 / 0.29). The low FP of `state_aware` (0.007) relies on result hashes that differ when state changes, and on legit families built with that property. Legit work with unchanged observable state (hand-written "poll plateau": 8 identical 'running' polls) is flagged - a genuine residual FP, and also indistinguishable from a real flood without more context. If a tool returns volatile output for unchanged state (timestamps in results), state-awareness will over-suppress (miss floods); this is untested.
* Volatile-field list is a static name list; near-dup treats short-string changes as full changes (so incrementing-id floods with the id in a non-volatile field will not be near-dups, though cycle/distinct-ratio may still fire).
* Mock "disconnect tokens generated" is a simulation; real provider billing after disconnect is unknown until measured.
* Guard skeleton: streaming only; tool calls are buffered until generation end (adds latency and defeats streaming of tool calls); conversation identity = hash of first system/user message; detectors re-run over a trimmed history (<=400 calls) after each completed call (O(n) per call, fine for the mock, not tuned); usage in the guard's final chunk is zeros. Not load-tested. Mock upstream reproduces OpenAI/SGLang *documented* delta shapes as understood from Phase 0; actual provider behavior (incl. OpenRouter normalization) is unverified.
* Scenarios' flood-inducing modes only alter prompts/history; against the scripted mock they are inert (the mock replays the requested behavior). Whether they provoke real floods is exactly what Phase 2 must test. No claim that gpt-oss-20b floods at all.
* Cost/price figures for Phase 2 use Phase 0's OpenRouter-listed prices (fetched 2026-09-29), token counts are assumptions.
* `make` is not installed on this box; the Makefile is untested (the python command is the tested path).

## 9. What Phase 2 would require (NOT started; needs approval and an OpenRouter key)
Prerequisites: user places `OPENROUTER_API_KEY` in the box env (never pasted in chat); explicit written approval of the run plan; a hard `--budget-usd` on every run; provider pinned via `provider: {order:["DeepInfra"], allow_fallbacks:false}`; ledger entries per run. No self-hosting.

Plan (Stage 1 trace collection only; detectors stay at DRAFT until Stage 3):
1. **Smoke (needs approval only if >$1; est. $0.02):** 12 runs of `openai/gpt-oss-20b` @ DeepInfra on plain scenarios; verify real delta shapes (whole vs fragments), comment lines, usage chunk, reasoning field naming; adapt `sse.py` if needed.
2. **Disconnect-billing check (est. <$0.01):** start a long generation, cut the stream, compare provider `generation` stats vs tokens received.
3. **Main small-N collection (est. $0.5-$1.0):** ~150 runs (6 scenarios x 5 modes x 5 seeds), `max_tokens` 8K/request, turn cap 12, run completion cap 20K, **stop-early on detector fire** using the DRAFT suite via `DetectorStopHook` (so a flood costs only ~100 calls of output). Logged as guard `off` traces with the stop hook only for cost control (record it in provenance), so the flood *rate* estimate is truncated but the onset is preserved.
4. Optional (needs its own approval): history-primed fingerprint probe on MiMo-V2.6-Flash providers, ~72 short tasks, est. $0.25 per provider at Flash prices.
5. Evaluate Stage 2 on the real traces, then decide whether to freeze (Stage 3). Only then Phase 4 A/B.

Estimated cost (arithmetic in this session, gpt-oss-20b @ DeepInfra $0.03 in / $0.14 out per 1M tokens, assumed 60K in + 10K out per run):
| Item | Runs | Est. USD |
|---|---|---|
| Smoke | 12 | 0.02 |
| Disconnect check | 3 | <0.01 |
| Main collection (150 runs) | 150 | 0.48 (0.90 if reasoning tokens triple output) |
| Worst-case unguarded floods (40 runs at 32K out, 80K in) | 40 | 0.28 |
| Optional MiMo Flash provenance probe | 72 | 0.24 per provider |
| **Phase 2 total (expected / high)** | | **~$0.5-$1.5 / ~$2.5** |
Well under the **$10 target / $15 max**; the budget is dominated by uncertainty on reasoning-token volume and context growth, so the harness budget guard stays hard-capped (suggest $3 for Phase 2). **Approval is required before any single experiment expected to exceed $1**, and before using any model other than gpt-oss-20b @ DeepInfra (deepseek-v4-flash @ DeepInfra is the listed backup). Risk: gpt-oss-20b may simply not flood; then Phase 2 reports that null result and falls back to history-primed MiMo probes (small $) or replay of mock floods only.

## Spend ledger (real, `spend_ledger.jsonl`)
```
{"completion_tokens":177,"endpoint_kind":"mock-loopback","live_call":false,"model":"mock","phase":"1-offline","prompt_tokens":4921,"run_id":"run-pagination-plain-3-auto-whole","usd":0.0}
{"completion_tokens":4783,"endpoint_kind":"mock-loopback","live_call":false,"model":"mock","phase":"1-offline","prompt_tokens":18129,"run_id":"run-fan_out-rotating_argument-3-rotating35-incremental","usd":0.0}
{"completion_tokens":0,"endpoint_kind":"mock-loopback","live_call":false,"model":"mock","phase":"1-offline","prompt_tokens":0,"run_id":"run-fan_out-rotating_argument-3-rotating35-whole","usd":0.0}
```
Total: $0.00, `live_call: false` on every row. No network request left the machine during tests or demo other than loopback.
