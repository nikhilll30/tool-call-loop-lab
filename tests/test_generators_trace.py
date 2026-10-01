import json
from floodlab.gen import floods, legit, suites
from floodlab.gen.handwritten import handwritten_legit
from floodlab.detectors import max_adjacent_run
from floodlab.trace import validate, flat_calls, generations, write_jsonl, read_jsonl
from floodlab.gen.common import DEV_SEEDS, TEST_SEEDS


def test_deterministic():
    assert floods.rotating35_one_gen(3) == floods.rotating35_one_gen(3)
    assert floods.rotating35_one_gen(3) != floods.rotating35_one_gen(4)
    assert legit.pagination_cursor(5) == legit.pagination_cursor(5)


def test_rotating35_shape():
    t = floods.rotating35_one_gen(0)
    calls = flat_calls(t)
    assert len(calls) == 4120 and len({(c.name, c.args) for c in calls}) == 35
    assert max_adjacent_run(t) == 1 and len(generations(t)) == 1
    assert t["synthetic"] and "SYNTHETIC" in t["notes"]


def test_start_done_and_2509_shapes():
    t = floods.start_done_alternation(0)
    assert max_adjacent_run(t) == 1
    t = floods.cancel_retry_2509(0)
    gens = generations(t)
    assert len(gens) == 10 and all(len(g) == 17 for g in gens)
    assert all([(c.name, c.args) for c in g] == [(c.name, c.args) for c in gens[0]] for g in gens)
    assert all(g["cancelled"] for tu in t["turns"] for g in tu["generations"])


def test_all_valid_and_labeled_and_split():
    ts = suites.all_traces()
    assert len(ts) == 2 * 10 * (8 + 7) + 6
    assert all(not validate(t) for t in ts)
    assert {t["label"] for t in ts} == {"flood", "legitimate"}
    assert {t["split"] for t in ts} == {"dev", "test", "none"}
    assert not set(DEV_SEEDS) & set(TEST_SEEDS)
    assert all(t["synthetic"] for t in ts)
    assert len(handwritten_legit()) == 6


def test_legit_fanout_size():
    for s in range(10):
        n = len(flat_calls(legit.parallel_fanout(s)))
        assert 20 <= n <= 40


def test_provenance_fields_and_jsonl_roundtrip(tmp_path):
    t = floods.abc_cycle_one_gen(0)
    for k in ("model", "endpoint", "scenario", "seed", "detector_config", "guard_config", "prompt_version", "tool_schema_version"):
        assert k in t["provenance"]
    p = tmp_path / "x.jsonl"
    write_jsonl(p, [t]); assert read_jsonl(p) == [t]
