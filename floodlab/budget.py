"""Hard budget guard for live spend (Phase 2A). Append-only ledger; spent = sum of `usd` over this phase's rows.

Worst-case pre-charge for ONE request (reasoning tokens are output tokens and count inside max_tokens):
    est_prompt_tokens = ceil(len(canonical_json(messages)) / 3) + ceil(len(canonical_json(tools)) / 3) + 300 (template overhead)      # chars/3 is conservative (real ~4)
    worst_case_usd    = (est_prompt_tokens * price_in + max_tokens * price_out) / 1e6 * margin              # margin 1.25
A request is REFUSED unless  ledger_spent + worst_case_usd <= effective_cap  (0.90; hard cap 1.00 is never approached by design).
A run is only LAUNCHED if the worst case of the whole run (max_turns requests at the prompt ceiling) also fits.
The pre-charge is written to the ledger BEFORE launch. After a request, real cost (usage.cost, else tokens x price) replaces it (settle row,
usd = actual - precharge); a cancelled/failed request keeps its worst-case charge provisionally and is reconciled later against
GET /api/v1/generation total_cost (reconcile row). Sum of `usd` over live rows == current spend."""
from __future__ import annotations
import json, math, time
from pathlib import Path
from .canon import canonical_json

HARD_CAP_USD = 1.00
EFFECTIVE_CAP_USD = 0.90
PRICE_IN_PER_M = 0.02      # gpt-oss-20b via Darkbloom (listing 0.018 / 0.09 $/M, rounded UP; DeepInfra was 0.03 / 0.14) - see docs/PHASE2A_PROVIDER_CHOICE.md
PRICE_OUT_PER_M = 0.10
MARGIN = 1.25
PROMPT_CEILING_TOKENS = 24000
TEMPLATE_OVERHEAD_TOKENS = 300   # chat-template/harmony/system overhead: live probe billed 61 prompt tokens for a ~21-token estimate


class BudgetRefused(RuntimeError):
    pass


class Anomaly(RuntimeError):
    """Stop-and-report condition (auth error, wrong provider, cost >3x estimate, billing discrepancy, mid-stream error, ...)."""


def est_tokens(obj) -> int:
    return math.ceil(len(canonical_json(obj)) / 3)


class BudgetGuard:
    def __init__(self, ledger_path: Path, phase: str = "2A", live: bool = True, cap: float = EFFECTIVE_CAP_USD, price_in: float = PRICE_IN_PER_M,
                 price_out: float = PRICE_OUT_PER_M, margin: float = MARGIN, prompt_ceiling: int = PROMPT_CEILING_TOKENS):
        if cap > EFFECTIVE_CAP_USD + 1e-12:
            raise ValueError(f"effective cap {cap} exceeds {EFFECTIVE_CAP_USD} (hard cap {HARD_CAP_USD})")
        self.path, self.phase, self.live, self.cap = Path(ledger_path), phase, live, cap
        self.price_in, self.price_out, self.margin, self.prompt_ceiling = price_in, price_out, margin, prompt_ceiling
        self.charged: dict[str, float] = {}       # request key -> usd charged so far

    # ---- ledger ----
    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        # spend = ALL rows of the same kind (live vs mock) in the ledger file, whatever their phase: the cap is total across live calls
        return [r for r in (json.loads(l) for l in self.path.read_text().splitlines() if l.strip()) if bool(r.get("live_call")) == self.live]

    def spent(self) -> float:
        return sum(r.get("usd", 0.0) for r in self.rows())

    def hard_check(self) -> None:
        if self.spent() >= HARD_CAP_USD:
            raise BudgetRefused(f"hard cap ${HARD_CAP_USD:.2f} reached")

    def remaining(self) -> float:
        return self.cap - self.spent()

    def append(self, row: dict) -> None:
        row = {"ts": round(time.time(), 3), "phase": self.phase, "live_call": self.live, **row}
        with open(self.path, "a") as f:
            f.write(canonical_json(row) + "\n")

    # ---- worst case ----
    def cost(self, prompt_tokens: float, completion_tokens: float) -> float:
        return (prompt_tokens * self.price_in + completion_tokens * self.price_out) / 1e6

    def worst_case_request(self, messages, tools, max_tokens: int) -> tuple[float, int]:
        p = est_tokens(messages) + est_tokens(tools) + TEMPLATE_OVERHEAD_TOKENS
        return self.cost(p, max_tokens) * self.margin, p

    def worst_case_run(self, max_turns: int, max_tokens: int) -> float:
        return self.cost(self.prompt_ceiling, max_tokens) * self.margin * max_turns

    def check(self, worst_case: float, what: str = "request") -> None:
        s = self.spent()
        if s + worst_case > self.cap + 1e-12:
            raise BudgetRefused(f"{what}: spent ${s:.6f} + worst-case ${worst_case:.6f} = ${s + worst_case:.6f} > effective cap ${self.cap:.2f}")

    # ---- charging ----
    def precharge(self, key: str, worst_case: float, **fields) -> None:
        """Written to the ledger BEFORE the request is launched (so a crash can only over-count spend)."""
        self.check(worst_case, f"precharge {key}")
        self.charged[key] = worst_case
        self.append({"kind": "precharge", "usd": round(worst_case, 8), "usd_source": "worst_case_estimate", "request_key": key, **fields})

    def settle(self, key: str, actual_usd: float, source: str, **fields) -> None:
        """Replace the pre-charge by the real cost (row usd = actual - already charged; negative = refund of over-estimate)."""
        delta = actual_usd - self.charged.get(key, 0.0)
        self.charged[key] = actual_usd
        self.append({"kind": "settle", "usd": round(delta, 8), "usd_source": source, "request_key": key, "actual_usd": actual_usd, **fields})

    def release(self, key: str, reason: str, **fields) -> None:
        """Release the provisional pre-charge of a request that provably never started generation (HTTP 429 before any stream/body):
        real spend is $0, so the ledger row cancels the pre-charge exactly. Callers must cross-check against the key usage counter."""
        delta = 0.0 - self.charged.get(key, 0.0)
        self.charged[key] = 0.0
        self.append({"kind": "release", "usd": round(delta, 8), "usd_source": reason, "request_key": key, "actual_usd": 0.0, **fields})

    def note(self, text: str, **fields) -> None:
        self.append({"kind": "note", "usd": 0.0, "note": text, **fields})

    def reconcile(self, key: str, actual_usd: float, **fields) -> float:
        delta = actual_usd - self.charged.get(key, 0.0)
        self.charged[key] = actual_usd
        self.append({"kind": "reconcile", "usd": round(delta, 8), "usd_source": "generation_total_cost", "request_key": key,
                     "actual_usd": actual_usd, **fields})
        return delta
