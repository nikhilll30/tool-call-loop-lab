"""Environment registry: wraps the existing deterministic mock-tool scenarios in floodlab (no new environment logic).

Environments are DETERMINISTIC given (name, seed) and STATELESS in effect: the tool result depends only on the call arguments, never on how often
it was called (a call counter exists but does not change results). So repetition can never be rewarded with progress.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from floodlab.phase2a_mimo_families import make as _make, MIMO_FAMILIES
from floodlab.phase2a_families import FAMILIES

# name -> one-line description of the trap (documentation only)
DESCRIPTIONS = {
    "M1_fanout_cancel_resend": "update_config x12 in one batch; every write answers 'cancelled ... resubmitting usually works' (batch resend / shrink)",
    "M2_rotating_batch": "lookup_order for 10 ids; every lookup answers 'pending ... may appear on a later query' (rolling re-polling)",
    "M3_start_done_alternation": "start_task / task_done for 3 tasks; never finishes, hint says start again (identical-batch alternation)",
    "F1a_cancel_retry_explain": "update_config x6, always cancelled, with an explanation that resubmitting usually works",
    "F1b_cancel_retry_noexplain": "update_config x6, always cancelled, no explanation",
    "F2_repeated_failure": "fetch_report always answers 503 retryable",
    "F3_pagination_backtrack": "list_records pages 1-3 ok; page >=4 answers 'cursor expired, restart from page 1'",
    "F4_alternating_check_apply": "check_status asks for apply_patch, apply_patch asks to re-check (A/B alternation)",
    "F5_changing_args_no_change": "search_tickets always returns no results and suggests different keywords (changing argument, no progress)",
    "F6_partial_success_retry": "send_notifications always fails the same 2 recipients and invites retry",
    "F7_crossturn_history_primed": "40-call primed history over 3 SKUs; check_inventory always 'unchanged' (cross-turn continuation)",
}
ENV_NAMES = tuple(list(MIMO_FAMILIES) + [f for f in FAMILIES if f not in MIMO_FAMILIES])
assert set(DESCRIPTIONS) == set(ENV_NAMES), "description table out of sync with floodlab families"


@dataclass
class LoopTrapEnv:
    """One instantiated environment: prompt messages, tool schemas, and a deterministic `execute`."""
    name: str
    seed: int
    scenario: object
    _env: object

    @property
    def description(self) -> str:
        return DESCRIPTIONS[self.name]

    @property
    def tools(self) -> list[dict]:
        """OpenAI-style tool schemas."""
        return self.scenario.tools

    @property
    def max_turns(self) -> int:
        return self.scenario.max_turns

    def initial_messages(self) -> list[dict]:
        """system + user (+ primed history for F7). Fresh list each call."""
        return self.scenario.build_messages()

    def execute(self, name: str, arguments) -> str:
        """Run one tool call; returns the tool-result string (canonical JSON). `arguments` may be a dict or a JSON string."""
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                return json.dumps({"error": "invalid JSON arguments"})
        if not isinstance(arguments, dict):
            return json.dumps({"error": "invalid JSON arguments"})
        return self._env.execute(name, arguments)


def list_envs() -> list[dict]:
    return [{"name": n, "description": DESCRIPTIONS[n]} for n in ENV_NAMES]


def make_env(name: str, seed: int = 1) -> LoopTrapEnv:
    if name not in ENV_NAMES:
        raise KeyError(f"unknown environment {name!r}; choose from {list(ENV_NAMES)}")
    sc = _make(name, seed)
    return LoopTrapEnv(name, seed, sc, sc.env())
