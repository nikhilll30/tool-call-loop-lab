# Held-out validation set v1 - design (written BEFORE any detector was run on it)

Status: Phase 1.5. Phase 1 detector settings (`draft-0.1`, hash `b1baa129b8d2`) are **development settings**. The Phase 1 generators and
seeds (0-9, 100-109) are **dev data** and stay dev. This held-out set uses **new generators with structures that do not
appear in dev**, new seed range `1000-1009`, and hand-written cases. It lives in `floodlab/heldout/` and `data/heldout/` and
must never be used by a dev path (enforced by `tests/test_heldout_isolation.py`).

All traces are SYNTHETIC. Labels are assigned **by construction** by the author (a limitation: ground truth is our judgement of
what is "productive", not an external oracle; authors also know the detectors, so this set is harder than dev but not adversarial-independent).

## Ground truth rules
* `legitimate`: every call either has arguments not previously used for that purpose, or is a repeat whose purpose is served
  because external state changed / a bounded wait that ends in a change / a verification re-read / a retry after an error. The trace
  reaches a natural end (completion).
* `flood`: from `loop_start` on, the trace contains no call that adds information the agent did not already have; it is repetition
  (exact, drifting, cyclic or noisy) that would continue until a cap. `loop_start` = 0-based global call index (emission order)
  of the **first call that is an unproductive repeat** (definition per structure below). Latency is measured from it.
* Poll plateaus: a poll sequence whose result does not change for L polls and then changes is labelled **legitimate** for any L <= 40
  (author judgement: bounded waits for real jobs). This is the largest source of expected detector disagreement and is intentional.

## Flood structures (9 generated x 8 seeds = 72, + 6 hand-written = 78)
| id | structure | what makes it hard | loop_start |
|---|---|---|---|
| F1 slow_drift_offset | `read_file{path, offset}` with `offset` incrementing by 4096 each call, result always the same EOF | args all distinct; drift is in a non-volatile numeric field | 1 |
| F2 slow_drift_timestamp | `search{query, since}` with `since` incrementing 300 s per call, result always empty | drifting field is called `since` (not in the default volatile list) | 1 |
| F3 mixed_tool_lcm_cycle | lap of 4 tools, each with a small argument pool (sizes from {2,3,4}) so the joint period is lcm (6 or 12 laps = 24-48 calls), multi-turn | cycle across 4 tools, long period, no adjacent/in-turn duplicate structure | first exact repeat |
| F4 noisy_result_repeat | identical `web_search{query}` repeated 30-60 times; each result differs (ordering/ads/timestamps) | result hashes differ, so state-aware logic is expected to be blinded | 1 |
| F5 low_rate_with_heartbeat | 1 call per turn over ~100 turns: lap = poll A, poll B, `log_message{text: unique}`, poll D; A,B,D results unchanged | repetition diluted by unique calls; low rate per generation | 4 |
| F6 flood_after_legit_prefix | 12-30 distinct legitimate calls (pagination or reads), then a rotating loop over 6-10 inputs (~100 calls) | detectors must not fire on the prefix; latency measured from loop start | prefix length + period |
| F7 startdone_rotating_permuted_ids | one generation: `start_job(id_j)` / `get_job_status(id_{j-1})` alternating over 18-30 ids, ids re-permuted every lap, results constant | no fixed period (permuted), 36-60 distinct signatures | 2 x n_ids |
| F8 oscillating_edit_same_failure | `edit_file` alternates between two contents, `run_tests` returns the same failure every time (2 calls/turn) | test command rerun after "real" edits looks legitimate locally | 5 |
| F9 growing_batch_repeat | each turn re-issues the previous batch plus one new call (batch 8-14 growing by 1), repeated results constant | near-identical, not identical, batches across turns | first batch size |

## Legitimate structures (11 generated x 10 seeds = 110, + 12 hand-written = 122)
| id | structure | why it is a hard negative |
|---|---|---|
| L1 poll_long_plateau | `get_job_status` polled 1/turn; identical result for a plateau of 9-40 polls, then progress/done | plateau **longer than the dev hard case (8)**; genuinely indistinguishable from a flood until it changes |
| L2 retries_backoff_refresh | `fetch{source, attempt, wait_s, token}` with backoff params and refreshed tokens; identical 503 results until success | args change each attempt while results are identical |
| L3 paginated_cursor_quirks | opaque hex cursors, empty pages with a next cursor, a cursor retried after a 429, one restart from `null` with changed data | identical calls appear 2-3 times with different results |
| L4 batch_fanout_repeated_subcalls | one generation of 30-50 `query_metric{name}` calls over 6 names, each repeated 5-8 times with **different results** | in-generation exact duplicates that are legitimate (repeated measurement) |
| L5 idempotent_reread_after_write | write, then read the same file twice (verification), per round, 6-14 rounds over 2-3 files | identical reads; some with no change between (verification double-read) |
| L6 test_fix_rerun | per turn: `run_tests(cmd)`, `read_file`, `edit_file`, with failing count non-increasing and stagnating for stretches; 8-16 rounds | same test command reruns, results often unchanged for 2-3 reruns |
| L7 noisy_results_unchanged_state | `get_status{service}` polled 8-25 times, state unchanged until the last poll, each result carries fresh `server_time`, `request_id`, `load` | volatile results although state is unchanged (stresses state-aware honestly: it should suppress, for the wrong reason) |
| L8 large_fanout_distinct | one generation of 24-100 distinct `read_file` calls | large batches; those > 64 exceed a per-generation cap of 64 by design |
| L9 tree_crawl | breadth-first `list_dir`/`read_file` batches of 2-12 calls, ending with a re-list of the root after a write | many generations, mostly distinct, one state-changed repeat |
| L10 alternating_two_tool_distinct | `search(q_i)` / `get_doc(id_i)` alternating, 1 call per turn, 20-45 pairs, distinct args | period-2 tool pattern with distinct arguments |
| L11 batch_polling_multi_job | every turn re-issues the same batch of 4-6 `get_job_status(job_k)`; jobs finish at different times then stay `done` | identical batches across turns, results partly unchanged (finished jobs) |

## Hand-written subset
`floodlab/heldout/handwritten.py`: 6 floods (literal 3-tool lcm cycle, oscillating edit, query-creep, poll-then-reread, same-error retry,
3-id start/done) and 12 legitimate (60-poll plateau, backoff-capped plateau, token-refresh retry, duplicate-page pagination, 45-call
repeated-subcall fan-out, write-read verification, test rerun stagnation, noisy poll, 70-distinct fan-out, single retry after error,
alternating distinct search/doc, 4-service monitor).

## Determinism / bookkeeping
Seeds 1000-1007 (floods) and 1000-1009 (legit); `random.Random(f"{structure}:{seed}")`. Trace field `split="heldout"`,
`ground_truth = {label, loop_start_index, structure, rationale}`. Dataset written to `data/heldout/heldout_v1.jsonl`; its sha256 is
recorded in `docs/SELECTION_PROCEDURE.md` before any detector run. Generator tests check structure (sizes, labels, determinism) only and import no detector.
