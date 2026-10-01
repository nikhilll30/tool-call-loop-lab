import json
import pytest
from floodlab.harness import run_scenario, Caps, Budget, BudgetExceeded, NetworkNotAllowed, DetectorStopHook, is_loopback
from floodlab.scenarios import Scenario, SCENARIOS
from floodlab.config import SuiteConfig
from floodlab.trace import validate, flat_calls


@pytest.mark.parametrize("sid", SCENARIOS)
@pytest.mark.parametrize("dm", ["whole", "incremental"])
def test_normal_completion(upstream, tmp_path, sid, dm):
    t = run_scenario(Scenario(sid, "plain", 2), upstream.url, delta_mode=dm, ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"] == "completed" and not validate(t)
    assert t["cost_usd"] == 0.0


def test_reasoning_passback_needed_and_done(upstream, tmp_path):
    # would 400 if the harness dropped reasoning_content on pass-back
    t = run_scenario(Scenario("multi_hop", "plain", 1), upstream.url, ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"] == "completed"
    t = run_scenario(Scenario("multi_hop", "plain", 1), upstream.url, ledger_path=tmp_path / "l.jsonl", reasoning_passback=False)
    assert t["termination_reason"] == "http_400"


def test_history_primed_mode(upstream, tmp_path):
    t = run_scenario(Scenario("fan_out", "history_primed", 1), upstream.url, ledger_path=tmp_path / "l.jsonl",
                     flood_kwargs={"n_calls": 40, "turns": 2}, caps=Caps(max_turns=5))
    assert t["provenance"]["scenario"] == "fan_out/history_primed"
    assert len(flat_calls(t)) >= 40


def test_provenance_and_ledger(upstream, tmp_path):
    led = tmp_path / "l.jsonl"
    suite = SuiteConfig()
    t = run_scenario(Scenario("pagination", "plain", 7), upstream.url, ledger_path=led, suite=suite, guard_config="off", model="mock-x")
    p = t["provenance"]
    assert p["model"] == "mock-x" and p["seed"] == 7 and p["guard_config"] == "off" and p["detector_config"]["hash"] == suite.hash()
    assert p["prompt_version"] and p["tool_schema_version"]
    e = json.loads(led.read_text().splitlines()[-1])
    assert e["usd"] == 0.0 and e["live_call"] is False


def test_call_cap(upstream, tmp_path):
    t = run_scenario(Scenario("fan_out", "plain", 1), upstream.url, behavior="cross_turn", flood_kwargs={"n_calls": 30, "turns": 50},
                     caps=Caps(max_calls_total=100), ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"] == "call_cap"


def test_max_turn_cap(upstream, tmp_path):
    t = run_scenario(Scenario("fan_out", "plain", 1), upstream.url, behavior="cross_turn", flood_kwargs={"n_calls": 3, "turns": 50},
                     caps=Caps(max_turns=4, max_calls_total=10**6), ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"] == "max_turns" and len(t["turns"]) == 4


def test_token_cap(upstream, tmp_path):
    t = run_scenario(Scenario("fan_out", "plain", 1), upstream.url, behavior="cross_turn", flood_kwargs={"n_calls": 30, "turns": 50},
                     caps=Caps(max_completion_tokens=100, max_calls_total=10**6), ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"] == "token_cap"


def test_network_refused_and_budget_guard(tmp_path):
    assert not is_loopback("https://openrouter.ai/api/v1") and is_loopback("http://127.0.0.1:1/v1")
    with pytest.raises(NetworkNotAllowed):
        run_scenario(Scenario("pagination", "plain", 1), "https://openrouter.ai/api/v1", ledger_path=tmp_path / "l.jsonl")
    with pytest.raises(BudgetExceeded):    # allow_network but zero budget: still refused before any request
        run_scenario(Scenario("pagination", "plain", 1), "https://example.invalid/v1", allow_network=True, ledger_path=tmp_path / "l.jsonl")
    b = Budget(max_usd=0.0001, price_in_per_m=1000, price_out_per_m=1000)
    with pytest.raises(BudgetExceeded):
        b.check_before(1000, 1000)


def test_budget_guard_stops_run(upstream, tmp_path):
    t = run_scenario(Scenario("pagination", "plain", 1), upstream.url, budget=Budget(max_usd=1e-9, price_in_per_m=1e6, price_out_per_m=1e6),
                     ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"] == "budget_guard" and not t["turns"]


def test_stop_early_hook_cancels_stream(upstream, tmp_path):
    hook = DetectorStopHook(SuiteConfig())
    t = run_scenario(Scenario("fan_out", "rotating_argument", 1), upstream.url, behavior="rotating35",
                     flood_kwargs={"n_calls": 2000, "turns": 1, "chunk_delay_s": 0.001}, stop_hook=hook, suite=SuiteConfig(),
                     ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"].startswith("stopped_by_hook")
    n = len(flat_calls(t))
    assert 0 < n < 200
    g = t["turns"][0]["generations"][0]
    assert g["cancelled"] and g["stop"]["reason"]
    import httpx, time
    for _ in range(50):
        d = httpx.get(upstream.url.replace("/v1", "") + "/debug/disconnects").json()
        if d: break
        time.sleep(0.1)
    assert d and d[0]["tokens_generated"] < d[0]["total_planned_tokens"]


def test_stop_hook_does_not_fire_on_legit_fanout(upstream, tmp_path):
    hook = DetectorStopHook(SuiteConfig())
    t = run_scenario(Scenario("fan_out", "plain", 3), upstream.url, stop_hook=hook, ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"] == "completed"
