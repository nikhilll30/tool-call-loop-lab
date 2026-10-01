# Offline detector evaluation (SYNTHETIC data; suite `draft-0.1` hash `b1baa129b8d2`)

Detection rate per flood shape / false-positive rate per legitimate family. Not real-world rates.

## Flood detection rate - DEV seeds 0-9 (tuning allowed)

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

## False-positive rate on legitimate - DEV seeds 0-9 (tuning allowed)

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

## Flood detection rate - TEST seeds 100-109 (held out)

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

## False-positive rate on legitimate - TEST seeds 100-109 (held out)

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

## Hand-written legitimate set (n=6) - flagged = false positive

| trace | exact_dup | adjacent | near_dup | cycle | distinct_ratio | cross_turn | combined_raw | state_aware |
|---|---|---|---|---|---|---|---|---|
| hw-legit-paginate | False | False | False | False | False | False | False | False |
| hw-legit-fanout25 | False | False | False | False | False | False | False | False |
| hw-legit-backoff | False | False | False | False | False | False | False | False |
| hw-legit-hard-poll-plateau | False | True | True | True | False | False | True | True |
| hw-legit-rwt-cycle | False | False | True | False | False | False | True | False |
| hw-legit-repeat-search | False | True | False | False | False | False | False | False |

## Baseline-miss table (TEST seeds): shapes the exact-dup / last-3-identical baselines miss

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

## Baseline-miss table (DEV seeds)

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

## Explicit baseline-miss cases (TEST): both baselines silent, new detectors fire

| run_id | shape | n_calls | max_adjacent_run | combined_raw_first | state_aware_first |
|---|---|---|---|---|---|
| flood-rot35-mg-100 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-100 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-100 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-100 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-100 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
| flood-rot35-mg-101 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-101 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-101 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-101 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-101 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
| flood-rot35-mg-102 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-102 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-102 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-102 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-102 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
| flood-rot35-mg-103 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-103 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-103 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-103 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-103 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
| flood-rot35-mg-104 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-104 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-104 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-104 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-104 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
| flood-rot35-mg-105 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-105 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-105 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-105 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-105 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
| flood-rot35-mg-106 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-106 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-106 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-106 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-106 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
| flood-rot35-mg-107 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-107 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-107 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-107 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-107 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
| flood-rot35-mg-108 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-108 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-108 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-108 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-108 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
| flood-rot35-mg-109 | rotating35_multi_gen | 400 | 1 | 95 | 95 |
| flood-abc-mg-109 | abc_cycle_multi_gen | 36 | 1 | 8 | 8 |
| flood-neardup-109 | near_dup_counter | 60 | 1 | 7 | 7 |
| flood-xturn-109 | cross_turn_identical_batches | 72 | 1 | 35 | 35 |
| flood-cancelretry-109 | cancel_retry_2509 | 170 | 1 | 50 | 50 |
