"""looptraps: deterministic no-spend loop-trap environments and replay fixtures for testing agents / loop guards.

EXPLORATORY-2A packaging only. Thin wrapper over existing `floodlab` code (environments, frozen reporting criteria, existing detector plumbing).
No network, no API key, no new detectors. See looptraps/README.md.
"""
from .envs import ENV_NAMES, LoopTrapEnv, list_envs, make_env
from .runner import RunResult, run_agent, max_calls_guard, suite_guard
from .agents import RepeatBatchAgent, ShrinkAfterFailureAgent, GiveUpAfterAgent, ReplayAgent
from .replay import load_fixtures, get_fixture, summarize_trace, human_label

__all__ = ["ENV_NAMES", "LoopTrapEnv", "list_envs", "make_env", "RunResult", "run_agent", "max_calls_guard", "suite_guard",
           "RepeatBatchAgent", "ShrinkAfterFailureAgent", "GiveUpAfterAgent", "ReplayAgent",
           "load_fixtures", "get_fixture", "summarize_trace", "human_label"]
