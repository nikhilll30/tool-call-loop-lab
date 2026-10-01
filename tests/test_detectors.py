"""Detector self-tests: known positives and negative controls."""
import pytest
from floodlab.config import *
from floodlab.detectors import *
from floodlab.detectors import run_all
from floodlab.gen import floods, legit
from floodlab.gen.handwritten import handwritten_legit
from floodlab.gen.common import build


def T(gens):
    return build("t", shape="t", label="x", seed=1, gens=gens)


def c(n, i, res=None):
    return ("read_file", {"path": f"p{i}"}, res if res is not None else f"r{i}")


def test_config_hash_stable_and_sensitive():
    assert SuiteConfig().hash() == SuiteConfig().hash()
    assert SuiteConfig().hash() != SuiteConfig(adjacent=AdjacentConfig(n=4)).hash()
    assert GuardConfig.from_dict(GuardConfig().to_dict()).hash() == GuardConfig().hash()


def test_exact_dup_positive_and_scope():
    t = T([[c(0, i % 3) for i in range(9)]])
    assert exact_dup(t).flag
    # same calls split one per generation: invisible to a within-generation counter
    t2 = T([[c(0, i % 3)] for i in range(9)])
    assert not exact_dup(t2).flag


def test_exact_dup_negative():
    assert not exact_dup(T([[c(0, i) for i in range(40)]])).flag


def test_adjacent_positive_negative():
    assert adjacent(T([[c(0, 1)] * 3])).flag
    assert not adjacent(T([[c(0, i % 2) for i in range(20)]])).flag      # alternation evades last-3-identical
    assert adjacent(T([[c(0, 1)], [c(0, 1)], [c(0, 1)]])).flag           # across generations


def test_near_dup_positive_ignores_volatile():
    gen = [("ping", {"target": "x", "ts": 1000 + i}, "ok") for i in range(20)]
    r = near_dup(T([gen]))
    assert r.flag and r.reason == "NEAR_DUPLICATE_ARGS"
    assert not exact_dup(T([gen])).flag


def test_near_dup_negative_distinct_paths_and_fanout():
    assert not near_dup(T([[c(0, i) for i in range(40)]])).flag


def test_cycle_abc_and_negative():
    r = cycle(T([[c(0, i % 3) for i in range(30)]]))
    assert r.flag and r.evidence["period"] == 3
    assert not cycle(T([[c(0, i) for i in range(200)]])).flag


def test_cycle_across_generations():
    assert cycle(T([[c(0, 0), c(0, 1), c(0, 2)] for _ in range(6)])).flag


def test_cycle_rotating35_first_index():
    t = floods.rotating35_one_gen(0, n_calls=400)
    r = cycle(t)
    assert r.flag and r.evidence["period"] == 35 and r.first_index < 130


def test_distinct_ratio_positive_negative():
    assert distinct_ratio(floods.rotating35_one_gen(1)).flag
    assert not distinct_ratio(legit.parallel_fanout(1)).flag
    assert not distinct_ratio(T([[c(0, i) for i in range(300)]])).flag


def test_cross_turn_positive_negative():
    assert cross_turn(floods.cross_turn_identical_batches(1)).flag
    assert cross_turn(floods.cancel_retry_2509(1)).flag
    assert not cross_turn(legit.pagination_cursor(1)).flag
    # two identical batches only: below streak requirement
    b = [c(0, i) for i in range(5)]
    assert not cross_turn(T([b, b])).flag


def test_state_aware_suppresses_when_results_change():
    same_state = T([[("get_job_status", {"job": "j"}, "running")] for _ in range(12)])
    changing = T([[("get_job_status", {"job": "j"}, f"p{i}")] for i in range(12)])
    assert cycle(changing).flag and cycle(same_state).flag           # raw detectors cannot tell
    r = run_all(changing)
    assert r["combined_raw"].flag and not r["state_aware"].flag
    assert run_all(same_state)["state_aware"].flag


def test_state_aware_cannot_suppress_without_hashes():
    t = T([[("get_job_status", {"job": "j"}, None)] for _ in range(12)])
    assert run_all(t)["state_aware"].flag


@pytest.mark.parametrize("shape", floods.FLOOD_SHAPES)
def test_every_flood_shape_caught_by_state_aware(shape):
    for seed in (0, 100):
        r = run_all(floods.make(shape, seed))
        assert r["state_aware"].flag, shape
        assert r["state_aware"].first_index is not None


def test_baselines_miss_documented_shapes():
    r = run_all(floods.rotating35_one_gen(0))
    assert not r["adjacent"].flag and r["state_aware"].flag          # #2482 shape: max adjacent run 1
    r = run_all(floods.start_done_alternation(0))
    assert not r["adjacent"].flag and r["state_aware"].flag
    r = run_all(floods.cancel_retry_2509(0))
    assert not r["exact_dup"].flag and not r["adjacent"].flag and r["state_aware"].flag
    r = run_all(floods.rotating35_multi_gen(0))
    assert not r["exact_dup"].flag and not r["adjacent"].flag and r["state_aware"].flag


@pytest.mark.parametrize("family", legit.LEGIT_FAMILIES)
def test_state_aware_no_fp_on_legit_families(family):
    for seed in (0, 100):
        assert not run_all(legit.make(family, seed))["state_aware"].flag, family


def test_handwritten_hard_case_documented():
    res = {t["run_id"]: run_all(t) for t in handwritten_legit()}
    assert not any(r["state_aware"].flag for k, r in res.items() if "hard" not in k)
    # known, documented residual FP: plateau polling with unchanged observable state
    assert res["hw-legit-hard-poll-plateau"]["state_aware"].flag


def test_result_is_structured():
    r = run_all(floods.abc_cycle_one_gen(0))["cycle"].to_dict()
    assert set(r) == {"detector", "flag", "first_index", "reason", "evidence"}
