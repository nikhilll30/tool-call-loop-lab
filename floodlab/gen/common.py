"""Helper to build a synthetic trace from a list of generations of (name, args, result_text) triples."""
from __future__ import annotations
from ..trace import make_call, make_generation, make_trace, make_provenance, SIM_T0

DEV_SEEDS = list(range(0, 10))        # detector thresholds may be inspected/tuned on these
TEST_SEEDS = list(range(100, 110))    # held out: reported separately, never used for tuning


def split_of(seed: int) -> str:
    return "dev" if seed in DEV_SEEDS else "test" if seed in TEST_SEEDS else "none"   # "none" = hand-written set


def build(run_id, *, shape, label, seed, gens, scenario="synthetic", cancelled=None, note=""):
    """gens: list of lists of (name, args, result_text|None). One generation per turn."""
    turns, t, idx = [], SIM_T0, 0
    cancelled = cancelled or set()
    for k, g in enumerate(gens):
        calls = []
        for i, (name, args, res) in enumerate(g):
            calls.append(make_call(i, name, args, ts=round(t + 0.02 * i, 3), result=res))
        t_end = t + 0.02 * len(g) + 0.5
        fr = "cancelled" if k in cancelled else "tool_calls"
        turns.append({"turn": k, "messages": [{"role": "assistant", "content": "", "n_tool_calls": len(g)}],
                      "generations": [make_generation(0, calls, t, t_end, finish_reason=fr, cancelled=k in cancelled)]})
        t = t_end + 0.1
    return make_trace(run_id, make_provenance(model="synthetic-generator", endpoint="none", scenario=scenario, seed=seed,
                                              prompt_version="n/a", tool_schema_version="n/a"),
                      turns, label=label, shape=shape, synthetic=True, split=split_of(seed),
                      latency_s=round(t - SIM_T0, 3), cost_usd=0.0, termination_reason="synthetic", notes=note or "SYNTHETIC")
