import math
from floodlab.stats import clopper_pearson, wilson
from floodlab.policies import selectable_policies, diagnostic_policies, S0, guard_config_for, cap_index
from floodlab import heldout_eval as H
from floodlab.gen import floods, legit
from floodlab.trace import generations


def test_clopper_pearson_known_values():
    lo, hi = clopper_pearson(0, 122); assert lo == 0 and abs(hi - 0.0298) < 5e-4
    lo, hi = clopper_pearson(1, 122); assert abs(hi - 0.0448) < 1e-3 < 0.05
    assert clopper_pearson(2, 122)[1] > 0.05
    lo, hi = clopper_pearson(5, 10); assert abs(lo - 0.1871) < 1e-3 and abs(hi - 0.8129) < 1e-3
    assert wilson(0, 10)[0] == 0


def test_policy_set_matches_preregistration():
    ids = [p.id for p in selectable_policies()]
    assert ids == ["exact_dup", "adjacent3", "cap64", "cap128", "S0", "S0+cap64", "S0+cap128", "S1", "S1+cap64", "S1+cap128", "S2", "S2+cap64", "S2+cap128"]
    assert all(not p.selectable for p in diagnostic_policies())
    assert S0.hash() == "b1baa129b8d2"          # dev config the pre-registration refers to


def test_cap_and_intervention_index():
    t = floods.rotating35_one_gen(0)
    from floodlab.policies import Policy
    assert Policy("cap64", "cap", cap=64).intervention(t)[0] == 64
    assert Policy("cap64", "cap", cap=64).intervention(legit.pagination_cursor(0))[0] is None


def test_selection_rule_and_none_qualifies():
    mk = lambda pid, det, ub: {"policy": pid, "selectable": True, "detection_rate": det, "interruption_ci_cp": (0, ub), "latency_after_start_median_misses_as_trace_length": 5}
    assert H.select([mk("a", .9, .06), mk("b", .2, .01)])["selected"] is None
    assert H.select([mk("a", .9, .06), mk("b", .5, .04), mk("c", .7, .04)])["selected"] == "c"
    assert H.select([mk("S0+cap64", .7, .04), mk("S0", .7, .04)])["selected"] == "S0"       # fewer components
    assert H.select([{**mk("z", .9, .04), "selectable": False}])["selected"] is None          # diagnostics never selected


def test_guard_config_for_policy():
    p = [q for q in selectable_policies() if q.id == "S1+cap128"][0]
    g = guard_config_for(p); assert g.max_calls_per_generation == 128 and g.suite.id == "S1-moderate"
