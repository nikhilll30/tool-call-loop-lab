"""Guard POLICIES (pre-registered in docs/SELECTION_PROCEDURE.md): a policy maps a trace to an intervention index i*
(None = never intervenes). Intervention at i* means call i* and later are not executed."""
from __future__ import annotations
from dataclasses import dataclass, replace
from .config import SuiteConfig, GuardConfig, NearDupConfig, CycleConfig, DistinctRatioConfig, CrossTurnConfig
from .detectors import exact_dup, adjacent, near_dup, cycle, distinct_ratio, cross_turn, state_aware, run_all
from .detectors.base import as_gens

S0 = SuiteConfig()
S1 = replace(S0, id="S1-moderate", near_dup=replace(S0.near_dup, window=96, min_repeats=24), cycle=replace(S0.cycle, min_len=24),
             distinct_ratio=replace(S0.distinct_ratio, window=128), cross_turn=replace(S0.cross_turn, min_streak=4))
S2 = replace(S0, id="S2-patient", near_dup=replace(S0.near_dup, window=128, min_repeats=48), cycle=replace(S0.cycle, min_len=48),
             distinct_ratio=replace(S0.distinct_ratio, window=192), cross_turn=replace(S0.cross_turn, min_streak=6))
SUITES = {"S0": S0, "S1": S1, "S2": S2}
NO_CAP = 10**9


def cap_index(gens, cap: int):
    for g in gens:
        if len(g) > cap:
            return g[cap].gidx
    return None


@dataclass(frozen=True)
class Policy:
    id: str
    kind: str                 # "baseline" | "state_aware" | "cap" | "diagnostic"
    suite: str | None = None  # key into SUITES
    cap: int | None = None
    detector: str | None = None
    selectable: bool = True

    def intervention(self, trace_or_gens) -> tuple[int | None, dict]:
        gens = as_gens(trace_or_gens)
        cands: dict[str, int] = {}
        if self.kind in ("state_aware",):
            r = state_aware(gens, SUITES[self.suite])
            if r.flag: cands[r.evidence.get("earliest", "state_aware")] = r.first_index
        if self.detector:
            suite = S0
            res = {"exact_dup": lambda: exact_dup(gens, suite.exact_dup), "adjacent3": lambda: adjacent(gens, suite.adjacent),
                   "near_dup": lambda: near_dup(gens, suite.near_dup), "cycle": lambda: cycle(gens, suite.cycle),
                   "distinct_ratio": lambda: distinct_ratio(gens, suite.distinct_ratio), "cross_turn": lambda: cross_turn(gens, suite.cross_turn),
                   "combined_raw": lambda: run_all(gens, suite)["combined_raw"]}[self.detector]()
            if res.flag: cands[res.detector] = res.first_index
        if self.cap is not None:
            c = cap_index(gens, self.cap)
            if c is not None: cands["cap"] = c
        if not cands:
            return None, {}
        by = min(cands, key=cands.get)
        return cands[by], {"by": by, "all": cands}


def selectable_policies() -> list[Policy]:
    ps = [Policy("exact_dup", "baseline", detector="exact_dup"), Policy("adjacent3", "baseline", detector="adjacent3"),
          Policy("cap64", "cap", cap=64), Policy("cap128", "cap", cap=128)]
    for s in ("S0", "S1", "S2"):
        ps += [Policy(s, "state_aware", suite=s), Policy(f"{s}+cap64", "state_aware", suite=s, cap=64), Policy(f"{s}+cap128", "state_aware", suite=s, cap=128)]
    return ps


def diagnostic_policies() -> list[Policy]:
    return [Policy(f"diag:{d}", "diagnostic", detector=d, selectable=False)
            for d in ("near_dup", "cycle", "distinct_ratio", "cross_turn", "combined_raw")]


def guard_config_for(p: Policy) -> GuardConfig:
    assert p.kind in ("state_aware", "cap")
    suite = SUITES[p.suite] if p.suite else S0
    return GuardConfig(id=f"guard-{p.id}", max_calls_per_generation=p.cap or NO_CAP, suite=suite)
