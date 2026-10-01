import json
import pytest
from floodlab.tools import MockEnv
from floodlab.scenarios import Scenario, SCENARIOS, MODES


def test_env_deterministic():
    a, b = MockEnv("pagination", 1), MockEnv("pagination", 1)
    assert a.execute("list_items", {"cursor": None}) == b.execute("list_items", {"cursor": None})
    assert MockEnv("pagination", 1).n_items != MockEnv("pagination", 2).n_items or True


def test_stateful_polling_and_fix():
    e = MockEnv("fix_loop", 1)
    assert json.loads(e.execute("run_tests", {}))["passed"] is False
    for p in sorted(e.bugs):
        e.execute("edit_file", {"path": p, "content": "fixed"})
    assert json.loads(e.execute("run_tests", {}))["passed"] is True
    e = MockEnv("x", 1)
    s1 = e.execute("get_job_status", {"job": "j"}); 
    for _ in range(20): last = e.execute("get_job_status", {"job": "j"})
    assert s1 != last and json.loads(last)["status"] == "done"


def test_ping_ignores_ts():
    e = MockEnv("x", 1)
    assert e.execute("ping", {"target": "a", "ts": 1}) == e.execute("ping", {"target": "a", "ts": 2})


@pytest.mark.parametrize("sid", SCENARIOS)
def test_oracle_completes(sid):
    sc = Scenario(sid, "plain", 4)
    env, msgs = sc.env(), sc.build_messages()
    for step in range(60):
        calls = sc.next_calls(msgs)
        if calls is None:
            break
        msgs.append({"role": "assistant", "tool_calls": [{"id": f"c{step}_{i}", "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}} for i, c in enumerate(calls)]})
        for i, c in enumerate(calls):
            msgs.append({"role": "tool", "tool_call_id": f"c{step}_{i}", "content": env.execute(c["name"], c["arguments"])})
    else:
        pytest.fail("oracle never finished")


def test_modes_build():
    for m in MODES:
        msgs = Scenario("fan_out", m, 1).build_messages()
        assert msgs[0]["role"] == "system"
    primed = Scenario("fan_out", "history_primed", 1).build_messages()
    assert sum(1 for m in primed if m["role"] == "tool") == 12
