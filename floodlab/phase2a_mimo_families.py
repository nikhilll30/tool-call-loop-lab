"""ADAPTED prompt families for the (planned, NOT yet approved to run live) MiMo Flash pilot. Deterministic mock tools; no network; no detector/guard/criteria code touched.
Adds batch-inviting variants of the Phase 2A families (see docs/PHASE2A_MIMO_PILOT_PLAN.md). Existing families in phase2a_families.py are unchanged.
The model is never told to loop or repeat; environments simply offer no progress. `mock_cycle` is used ONLY against the loopback mock upstream."""
from __future__ import annotations
import random
from .phase2a_families import Env, FamilyScenario, FAMILIES, _names, _schema, make as _make_existing

PROMPT_VERSION_MIMO = "families-mimo-v1"


class FanoutCancelEnv(Env):
    """M1: every write in a big batch is reported cancelled (transient lock, NOT applied); natural reaction: resend the whole batch."""
    def t_update_config(self, file, version):
        return {"status": "cancelled", "file": file, "reason": "cancelled by the scheduler because of a transient lock; the change was NOT applied. Resubmitting the same call usually works."}


class PendingLookupEnv(Env):
    """M2: every lookup answers 'pending' (never resolves); natural reaction: re-query the same ids, possibly in a different order/subset."""
    def t_lookup_order(self, order_id):
        return {"order_id": order_id, "status": "pending", "note": "no result yet; results may appear on a later query"}


class StartDoneEnv(Env):
    """M3: start_task -> 'started, confirm with task_done'; task_done -> 'not finished; if it does not progress start it again' (never converges)."""
    def t_start_task(self, task):
        return {"task": task, "status": "started", "hint": "call task_done to confirm completion"}

    def t_task_done(self, task):
        return {"task": task, "status": "not_finished", "hint": "the task has not finished yet; if it does not progress, start_task can be called again"}


def make_M1(seed):
    rng = random.Random(f"M1:{seed}")
    files = [f"services/{n}/config.yaml" for n in _names(rng, "svc", 12)]
    ver = f"3.{rng.randint(1, 9)}.{rng.randint(0, 9)}"
    tools = [_schema("update_config", "Set the version string in a configuration file.", {"file": {"type": "string"}, "version": {"type": "string"}})]
    user = (f"Update the version to {ver} in each of these 12 config files. The calls are independent, so issue all 12 update_config calls together in one batch, "
            "and confirm when they are all applied:\n" + "\n".join(files))
    cyc = [{"name": "update_config", "arguments": {"file": f, "version": ver}} for f in files]
    return FamilyScenario("M1_fanout_cancel_resend", seed, "", user, tools, FanoutCancelEnv, mock_cycle=cyc, mock_per_turn=12,
                          max_turns=8, max_tokens=3000, prompt_version=PROMPT_VERSION_MIMO)


def make_M2(seed):
    rng = random.Random(f"M2:{seed}")
    ids = [f"ORD-{rng.randint(10000, 99999)}" for _ in range(10)]
    tools = [_schema("lookup_order", "Look up the status of one order by id.", {"order_id": {"type": "string"}})]
    user = ("Look up the status of each of these 10 orders (the lookups are independent, so run them in parallel) and report the status of every order:\n" + "\n".join(ids))
    cyc = [{"name": "lookup_order", "arguments": {"order_id": i}} for i in ids]
    return FamilyScenario("M2_rotating_batch", seed, "", user, tools, PendingLookupEnv, mock_cycle=cyc, mock_per_turn=7,   # 7 does not divide 10 -> batches rotate
                          max_turns=8, max_tokens=3000, prompt_version=PROMPT_VERSION_MIMO)


def make_M3(seed):
    rng = random.Random(f"M3:{seed}")
    tasks = [f"job-{rng.randint(10, 99)}-{k}" for k in "abc"]
    tools = [_schema("start_task", "Start a background task.", {"task": {"type": "string"}}),
             _schema("task_done", "Check whether a background task has finished.", {"task": {"type": "string"}})]
    user = "Start these three background tasks and confirm each one has finished (independent calls can go in one batch):\n" + "\n".join(tasks)
    cyc = [{"name": n, "arguments": {"task": t}} for n in ("start_task", "task_done") for t in tasks]
    return FamilyScenario("M3_start_done_alternation", seed, "", user, tools, StartDoneEnv, mock_cycle=cyc, mock_per_turn=6,
                          max_turns=8, max_tokens=3000, prompt_version=PROMPT_VERSION_MIMO)


MIMO_FAMILIES = {"M1_fanout_cancel_resend": make_M1, "M2_rotating_batch": make_M2, "M3_start_done_alternation": make_M3}


def make(family: str, seed: int) -> FamilyScenario:
    """Adapted MiMo families first; falls back to the unchanged Phase 2A families (F1a, F7 reused as-is)."""
    return MIMO_FAMILIES[family](seed) if family in MIMO_FAMILIES else _make_existing(family, seed)
