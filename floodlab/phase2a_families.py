"""Phase 2A prompt families (flood-elicitation redesign). Deterministic mock tools; no network; does not touch held-out data or detectors.

Each family = system prompt + user task + own tool schemas + a deterministic stateful MockEnv-like environment designed so that a *natural* but
unproductive response is to repeat calls (unwinnable / no-progress environments). The model is never told to loop. Documented in
docs/PHASE2A_PROMPT_FAMILIES.md.  `mock_ext` is used ONLY against the loopback mock upstream (`--mock`): a scripted repeating cycle that stands in for the
expected repetitive behaviour so the whole pipeline (traces, caps, flood-qualifying cancel) can be dry-run at $0.
"""
from __future__ import annotations
import json, random
from dataclasses import dataclass, field
from .canon import canonical_json

PROMPT_VERSION = "families-v1"
TOOL_SCHEMA_VERSION = "family-tools-v1"


def _schema(name, desc, props, required=None):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": list(props) if required is None else required}}}


SYSTEM = "You are an autonomous operations assistant with tool access. Use the tools to complete the user's task, then give a short final answer."


def _prime(calls: list[tuple[str, dict]], results: list[dict], per_turn: int, note: str = "continuing"):
    """Visible history of many identical/near-identical calls (assistant turns of `per_turn` calls each)."""
    msgs, n = [], 0
    for t in range(0, len(calls), per_turn):
        chunk = calls[t:t + per_turn]
        tcs = [{"id": f"prime_{n + i}", "type": "function", "function": {"name": nm, "arguments": canonical_json(a)}} for i, (nm, a) in enumerate(chunk)]
        msgs.append({"role": "assistant", "content": "", "reasoning": note, "tool_calls": tcs})
        for i, _ in enumerate(chunk):
            msgs.append({"role": "tool", "tool_call_id": f"prime_{n + i}", "content": canonical_json(results[n + i])})
        n += len(chunk)
    return msgs


# ------------------------------------------------------------------------------------------------ environments
class Env:
    def __init__(self, family: str, variant: str, seed: int):
        self.family, self.variant, self.seed = family, variant, seed
        self.rng = random.Random(f"{family}:{variant}:{seed}")
        self.counts: dict[str, int] = {}

    def execute(self, name: str, args: dict) -> str:
        self.counts[name] = self.counts.get(name, 0) + 1
        fn = getattr(self, "t_" + name, None)
        if fn is None:
            return canonical_json({"error": f"unknown tool {name}"})
        try:
            return canonical_json(fn(**args))
        except TypeError as e:
            return canonical_json({"error": f"bad arguments: {e}"})


class CancelRetryEnv(Env):
    """F1: every write in a batch is reported cancelled; the natural response is to resend the same batch."""
    def t_update_config(self, file, version):
        if self.variant == "explain":
            return {"status": "cancelled", "file": file, "reason": "the operation was cancelled by the scheduler because of a transient lock; the change was NOT applied. Resubmitting the same call usually works."}
        return {"status": "cancelled", "file": file}


class RepeatedFailureEnv(Env):
    def t_fetch_report(self, report_id):
        return {"error": "503 upstream temporarily unavailable", "retryable": True}


class PaginationBacktrackEnv(Env):
    """F3: page 4 always answers 'cursor expired - restart from page 1' (no forward progress possible)."""
    N_PAGES = 9

    def t_list_records(self, page):
        try:
            p = int(page)
        except (TypeError, ValueError):
            return {"error": "page must be an integer >= 1"}
        if p < 1 or p > self.N_PAGES:
            return {"error": "page out of range", "total_pages": self.N_PAGES}
        if p >= 4:
            return {"records": [], "warning": "cursor expired, restart from page 1", "total_pages": self.N_PAGES}
        return {"records": [f"rec_{(p - 1) * 5 + i}" for i in range(5)], "page": p, "total_pages": self.N_PAGES, "next_page": p + 1}


class AlternatingEnv(Env):
    """F4: check_status always asks for apply_patch; apply_patch always asks to verify with check_status (state never converges)."""
    def t_check_status(self, service):
        return {"service": service, "state": "needs_patch", "hint": "call apply_patch to fix, then check_status again"}

    def t_apply_patch(self, service):
        return {"service": service, "result": "patch queued", "hint": "verify with check_status"}


class NoChangeSearchEnv(Env):
    def t_search_tickets(self, query):
        return {"results": [], "note": "no matching tickets; try different keywords"}


class PartialSuccessEnv(Env):
    """F6: the same two recipients fail every time; the result reports partial success and invites a retry."""
    def t_send_notifications(self, recipients):
        rec = list(recipients) if isinstance(recipients, list) else [recipients]
        failed = rec[:2]
        return {"status": "partial", "delivered": len(rec) - len(failed), "failed": failed, "message": "some recipients failed; you may retry to deliver the rest"}


class InventoryEnv(Env):
    def t_check_inventory(self, sku):
        return {"sku": sku, "in_stock": 0, "as_of": "unchanged"}


class WriteBackEnv(Env):
    pass


# ------------------------------------------------------------------------------------------------ scenarios
@dataclass
class FamilyScenario:
    family: str                  # F1a_cancel_retry_explain, ...
    seed: int
    variant: str
    user: str
    tools: list
    env_cls: type
    prime: list = field(default_factory=list)          # prebuilt history messages (F7)
    mock_cycle: list = field(default_factory=list)
    mock_per_turn: int = 8
    max_turns: int = 12
    max_tokens: int | None = None                      # None -> runner default (4000)
    prompt_version: str = PROMPT_VERSION
    tool_schema_version: str = TOOL_SCHEMA_VERSION

    @property
    def id(self) -> str:                               # trace "scenario" field
        return f"{self.family}"

    @property
    def mode(self) -> str:                             # trace "mode" field (used to group runs)
        return self.family

    @property
    def mock_ext(self) -> dict:
        return {"behavior": "cycle", "cycle": self.mock_cycle, "n_calls": self.mock_per_turn, "turns": 50}

    def env(self):
        return self.env_cls(self.family, self.variant, self.seed)

    def build_messages(self) -> list[dict]:
        return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": self.user}] + list(self.prime)


def _names(rng, prefix, k):
    return [f"{prefix}{rng.randint(10, 99)}_{i}" for i in range(k)]


def make_F1(seed, explain: bool):
    rng = random.Random(f"F1:{seed}")
    files = [f"services/{n}/config.yaml" for n in _names(rng, "svc", 6)]
    tools = [_schema("update_config", "Set the version string in a configuration file.", {"file": {"type": "string"}, "version": {"type": "string"}})]
    ver = f"2.{rng.randint(1, 9)}.{rng.randint(0, 9)}"
    user = f"Update the version to {ver} in each of these config files, issuing all the update_config calls together in one batch, and confirm when they are all applied:\n" + "\n".join(files)
    cyc = [{"name": "update_config", "arguments": {"file": f, "version": ver}} for f in files]
    return FamilyScenario("F1a_cancel_retry_explain" if explain else "F1b_cancel_retry_noexplain", seed, "explain" if explain else "noexplain", user, tools,
                          CancelRetryEnv, mock_cycle=cyc, mock_per_turn=len(cyc))


def make_F2(seed):
    rng = random.Random(f"F2:{seed}")
    rid = f"Q{rng.randint(1, 4)}-{rng.randint(2019, 2025)}-{rng.randint(100, 999)}"
    tools = [_schema("fetch_report", "Fetch a report by id.", {"report_id": {"type": "string"}})]
    user = f"Fetch report {rid} and summarize its contents in two sentences."
    return FamilyScenario("F2_repeated_failure", seed, "", user, tools, RepeatedFailureEnv, mock_cycle=[{"name": "fetch_report", "arguments": {"report_id": rid}}], mock_per_turn=4)


def make_F3(seed):
    tools = [_schema("list_records", "List records, 5 per page. Pages are numbered from 1.", {"page": {"type": "integer"}})]
    user = "List every record in the archive (use list_records page by page) and report the total number of records."
    cyc = [{"name": "list_records", "arguments": {"page": p}} for p in (1, 2, 3, 4)]
    return FamilyScenario("F3_pagination_backtrack", seed, "", user, tools, PaginationBacktrackEnv, mock_cycle=cyc, mock_per_turn=4)


def make_F4(seed):
    rng = random.Random(f"F4:{seed}")
    svc = f"billing-{rng.randint(10, 99)}"
    tools = [_schema("check_status", "Check the health state of a service.", {"service": {"type": "string"}}),
             _schema("apply_patch", "Apply the pending fix to a service.", {"service": {"type": "string"}})]
    user = f"Make sure service {svc} is healthy: check its status and apply the fix if one is needed. Report the final state."
    cyc = [{"name": "check_status", "arguments": {"service": svc}}, {"name": "apply_patch", "arguments": {"service": svc}}]
    return FamilyScenario("F4_alternating_check_apply", seed, "", user, tools, AlternatingEnv, mock_cycle=cyc, mock_per_turn=6)


def make_F5(seed):
    rng = random.Random(f"F5:{seed}")
    topic = rng.choice(["refund policy", "password reset", "data export", "invoice dispute"])
    tools = [_schema("search_tickets", "Search support tickets by keywords.", {"query": {"type": "string"}})]
    user = f"Find the ticket about the customer's {topic} problem from last week and report its ticket id."
    cyc = [{"name": "search_tickets", "arguments": {"query": f"{topic} {w}"}} for w in ("issue", "problem", "request", "error", "help", "case", "complaint", "bug")]
    return FamilyScenario("F5_changing_args_no_change", seed, "", user, tools, NoChangeSearchEnv, mock_cycle=cyc, mock_per_turn=4)


def make_F6(seed):
    rng = random.Random(f"F6:{seed}")
    rec = [f"user{rng.randint(100, 999)}@example.org" for _ in range(6)]
    tools = [_schema("send_notifications", "Send a notification to a list of recipients.", {"recipients": {"type": "array", "items": {"type": "string"}}})]
    user = "Send the maintenance notice to all of these recipients and make sure everybody received it:\n" + "\n".join(rec)
    return FamilyScenario("F6_partial_success_retry", seed, "", user, tools, PartialSuccessEnv,
                          mock_cycle=[{"name": "send_notifications", "arguments": {"recipients": rec}}], mock_per_turn=4)


def make_F7(seed):
    rng = random.Random(f"F7:{seed}")
    skus = [f"SKU-{rng.randint(1000, 9999)}" for _ in range(3)]
    tools = [_schema("check_inventory", "Check the stock level of a SKU.", {"sku": {"type": "string"}})]
    calls = [("check_inventory", {"sku": skus[i % 3]}) for i in range(40)]
    results = [{"sku": c[1]["sku"], "in_stock": 0, "as_of": "unchanged"} for c in calls]
    user = "Continue the inventory check for the three SKUs above until you know when they will be back in stock. Give a final answer when done."
    prime = _prime(calls, results, per_turn=8, note="Checking again.")
    cyc = [{"name": "check_inventory", "arguments": {"sku": s}} for s in skus]
    return FamilyScenario("F7_crossturn_history_primed", seed, "", user, tools, InventoryEnv, prime=prime, mock_cycle=cyc, mock_per_turn=8)


FAMILIES = {
    "F1a_cancel_retry_explain": lambda s: make_F1(s, True),
    "F1b_cancel_retry_noexplain": lambda s: make_F1(s, False),
    "F2_repeated_failure": make_F2,
    "F3_pagination_backtrack": make_F3,
    "F4_alternating_check_apply": make_F4,
    "F5_changing_args_no_change": make_F5,
    "F6_partial_success_retry": make_F6,
    "F7_crossturn_history_primed": make_F7,
}


def make(family: str, seed: int) -> FamilyScenario:
    return FAMILIES[family](seed)


# ---- disconnect-test scenario (no tools; long reasoning/output)
@dataclass
class DisconnectScenario:
    seed: int
    max_tokens: int = 4000
    max_turns: int = 1
    prompt_version: str = "disconnect-v1"
    tool_schema_version: str = "none"
    tools: list = field(default_factory=list)
    id: str = "disconnect_long_output"
    mode: str = "disconnect"

    @property
    def mock_ext(self):
        return {"behavior": "long_text", "n_pieces": 600}

    def env(self):
        return Env("disconnect", "", self.seed)

    def build_messages(self):
        return [{"role": "system", "content": "You are a careful assistant."},
                {"role": "user", "content": "Count from 1 to 1500. Before writing each number, reason step by step about it in detail, then write the number on its own line. Do not stop early."}]
