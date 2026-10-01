"""Detector / guard configuration dataclasses with a stable content hash."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict, replace
from .canon import canonical_json, sha

DEFAULT_VOLATILE = ("timestamp", "ts", "time", "counter", "nonce", "request_id", "seq", "iteration", "_t")


class Hashable:
    def to_dict(self) -> dict:
        return asdict(self)

    def hash(self) -> str:
        return sha(canonical_json(self.to_dict()), 12)


@dataclass(frozen=True)
class ExactDupConfig(Hashable):
    """Baseline: Xiaomi-style exact within-generation duplicate counting."""
    min_dups: int = 2          # flag a generation once this many calls repeat an earlier exact call


@dataclass(frozen=True)
class AdjacentConfig(Hashable):
    """Baseline: 'last N identical' guard over the flattened call sequence."""
    n: int = 3


@dataclass(frozen=True)
class NearDupConfig(Hashable):
    window: int = 64
    min_repeats: int = 8       # near-duplicate calls inside the window needed to flag
    max_dist: float = 0.1      # max fraction of differing argument leaves (after dropping volatile fields)
    volatile_fields: tuple = DEFAULT_VOLATILE
    use_state: bool = False
    state_change_frac: float = 0.5  # suppress if >= this fraction of repeated signatures returned differing results


@dataclass(frozen=True)
class CycleConfig(Hashable):
    max_period: int = 128
    min_reps: int = 3          # the period must repeat this many times
    min_len: int = 8           # ... and cover at least this many calls (period*reps)
    volatile_fields: tuple = DEFAULT_VOLATILE
    use_state: bool = False
    state_change_frac: float = 0.5  # suppress if >= this fraction of repeated signatures returned differing results


@dataclass(frozen=True)
class DistinctRatioConfig(Hashable):
    window: int = 96
    max_ratio: float = 0.4     # distinct/window <= this  -> flag
    max_norm_entropy: float = 0.5  # OR normalized Shannon entropy (bits / log2(window)) <= this
    volatile_fields: tuple = DEFAULT_VOLATILE
    use_state: bool = False
    state_change_frac: float = 0.5  # suppress if >= this fraction of repeated signatures returned differing results


@dataclass(frozen=True)
class CrossTurnConfig(Hashable):
    min_batch: int = 3         # only generations with >= this many calls are compared
    min_similarity: float = 0.9  # multiset Jaccard of call signatures between consecutive generations
    min_streak: int = 2        # consecutive similar transitions (=> 3 similar batches in a row)
    volatile_fields: tuple = DEFAULT_VOLATILE
    use_state: bool = False
    state_change_frac: float = 0.5  # suppress if >= this fraction of repeated signatures returned differing results


@dataclass(frozen=True)
class SuiteConfig(Hashable):
    id: str = "draft-0.1"
    exact_dup: ExactDupConfig = field(default_factory=ExactDupConfig)
    adjacent: AdjacentConfig = field(default_factory=AdjacentConfig)
    near_dup: NearDupConfig = field(default_factory=NearDupConfig)
    cycle: CycleConfig = field(default_factory=CycleConfig)
    distinct_ratio: DistinctRatioConfig = field(default_factory=DistinctRatioConfig)
    cross_turn: CrossTurnConfig = field(default_factory=CrossTurnConfig)

    def with_state(self, on: bool = True) -> "SuiteConfig":
        return replace(self,
                       near_dup=replace(self.near_dup, use_state=on),
                       cycle=replace(self.cycle, use_state=on),
                       distinct_ratio=replace(self.distinct_ratio, use_state=on),
                       cross_turn=replace(self.cross_turn, use_state=on))

    @staticmethod
    def from_dict(d: dict) -> "SuiteConfig":
        def tup(x):
            x = dict(x)
            if "volatile_fields" in x:
                x["volatile_fields"] = tuple(x["volatile_fields"])
            return x
        return SuiteConfig(
            id=d["id"], exact_dup=ExactDupConfig(**d["exact_dup"]), adjacent=AdjacentConfig(**d["adjacent"]),
            near_dup=NearDupConfig(**tup(d["near_dup"])), cycle=CycleConfig(**tup(d["cycle"])),
            distinct_ratio=DistinctRatioConfig(**tup(d["distinct_ratio"])),
            cross_turn=CrossTurnConfig(**tup(d["cross_turn"])))


@dataclass(frozen=True)
class GuardConfig(Hashable):
    id: str = "guard-draft-0.1"
    max_calls_per_generation: int = 64
    hard_stop_after_identical_cancelled: int = 3   # #2509: stop retrying an identical cancelled batch
    suite: SuiteConfig = field(default_factory=SuiteConfig)

    @staticmethod
    def from_dict(d: dict) -> "GuardConfig":
        return GuardConfig(id=d["id"], max_calls_per_generation=d["max_calls_per_generation"],
                           hard_stop_after_identical_cancelled=d["hard_stop_after_identical_cancelled"],
                           suite=SuiteConfig.from_dict(d["suite"]))
