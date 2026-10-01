import json, shutil, httpx, pytest
from floodlab.guard import create_guard_app
from floodlab.guard.proxy import history_from_messages
from floodlab.config import GuardConfig
from floodlab.harness import run_scenario, Caps
from floodlab.scenarios import Scenario
from floodlab.servers import LocalServer
from floodlab import freeze
from floodlab.trace import flat_calls


@pytest.fixture()
def guard(upstream):
    app = create_guard_app(upstream.url, GuardConfig())
    with LocalServer(app) as g:
        g.app, g.up = app, upstream
        yield g


def test_guard_stops_flood_with_structured_reason(guard, tmp_path):
    t = run_scenario(Scenario("fan_out", "rotating_argument", 1), guard.url, behavior="rotating35",
                     flood_kwargs={"n_calls": 300, "turns": 1}, ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"].startswith("guard_stop:")
    g = t["turns"][0]["generations"][0]["floodlab_guard"]
    assert g["stopped"] and g["reason"] and g["config_hash"] == GuardConfig().hash()
    assert len(flat_calls(t)) == 0          # buffered tool calls were never released to the client
    assert guard.app.state.events


def test_guard_passes_legit_traffic(guard, tmp_path):
    for sid in ("pagination", "fan_out", "fix_loop", "multi_hop"):
        t = run_scenario(Scenario(sid, "plain", 5), guard.url, ledger_path=tmp_path / "l.jsonl")
        assert t["termination_reason"] == "completed", sid


def test_guard_incremental_deltas(guard, tmp_path):
    t = run_scenario(Scenario("fan_out", "plain", 5), guard.url, delta_mode="incremental", ledger_path=tmp_path / "l.jsonl")
    assert t["termination_reason"] == "completed" and len(flat_calls(t)) > 20


def test_guard_cancels_upstream_stream(guard, tmp_path):
    import time
    run_scenario(Scenario("fan_out", "rotating_argument", 2), guard.url, behavior="rotating35",
                 flood_kwargs={"n_calls": 3000, "turns": 1, "chunk_delay_s": 0.001}, ledger_path=tmp_path / "l.jsonl")
    for _ in range(60):
        d = httpx.get(guard.up.url.replace("/v1", "") + "/debug/disconnects").json()
        if d: break
        time.sleep(0.1)
    assert d and d[0]["tokens_generated"] < d[0]["total_planned_tokens"] / 3


def test_hard_stop_after_identical_cancelled_batches(upstream, tmp_path):
    """#2509: byte-identical batch retried; after N the guard refuses without contacting upstream."""
    from dataclasses import replace
    base = GuardConfig()
    # isolate the counter: switch the detectors off so only the batch counter can fire
    suite = replace(base.suite, cross_turn=replace(base.suite.cross_turn, min_streak=50),
                    cycle=replace(base.suite.cycle, min_reps=50, min_len=10**4),
                    near_dup=replace(base.suite.near_dup, min_repeats=10**4),
                    distinct_ratio=replace(base.suite.distinct_ratio, window=10**4))
    cfg = replace(base, max_calls_per_generation=1000, hard_stop_after_identical_cancelled=3, suite=suite)
    app = create_guard_app(upstream.url, cfg)
    with LocalServer(app) as g:
        t = run_scenario(Scenario("fan_out", "cross_turn", 1), g.url, behavior="cancel_retry",
                         flood_kwargs={"n_calls": 17, "turns": 10}, caps=Caps(max_turns=12), ledger_path=tmp_path / "l.jsonl")
    ev = [e["reason"] for e in app.state.events]
    assert "HARD_STOP_IDENTICAL_BATCH_RETRIES" in ev
    assert t["termination_reason"].startswith("guard_stop")
    assert len(t["turns"]) < 10                       # did not run all 10 retries
    hs = [e for e in app.state.events if e["reason"] == "HARD_STOP_IDENTICAL_BATCH_RETRIES"][0]
    assert hs["identical_batches"] >= 3


def test_cross_turn_detector_also_stops_identical_retries(upstream, tmp_path):
    app = create_guard_app(upstream.url, GuardConfig(max_calls_per_generation=1000))
    with LocalServer(app) as g:
        t = run_scenario(Scenario("fan_out", "cross_turn", 1), g.url, behavior="cancel_retry",
                         flood_kwargs={"n_calls": 17, "turns": 10}, caps=Caps(max_turns=12), ledger_path=tmp_path / "l.jsonl")
    assert [e["reason"] for e in app.state.events] == ["CROSS_TURN_BATCH_REPEAT"]
    assert t["termination_reason"] == "guard_stop:CROSS_TURN_BATCH_REPEAT"


def test_history_rebuild_with_results():
    msgs = [{"role": "assistant", "tool_calls": [{"id": "a", "function": {"name": "n", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "a", "content": "res"}]
    h = history_from_messages(msgs)
    assert h[0][0]["name"] == "n" and h[0][0]["result_hash"]


def test_guard_rejects_non_stream(guard):
    r = httpx.post(guard.url + "/chat/completions", json={"messages": []})
    assert r.status_code == 400


# ---- freezing tooling ----
def _mk(tmp_path):
    d = tmp_path / "frozen"; d.mkdir()
    shutil.copy(freeze.DRAFT_CFG, d / freeze.DRAFT_CFG.name); shutil.copy(freeze.DRAFT_FP, d / freeze.DRAFT_FP.name)
    return d


def test_real_repo_is_not_frozen():
    with pytest.raises(freeze.FrozenConfigError):
        freeze.require_frozen()
    from floodlab import ab_online
    assert ab_online.main() == 2


def test_freeze_verify_and_tamper(tmp_path):
    d = _mk(tmp_path)
    with pytest.raises(freeze.FrozenConfigError):
        freeze.require_frozen(d)
    freeze.freeze(d)
    cfg, fp = freeze.require_frozen(d)
    assert cfg.hash() == GuardConfig().hash() and fp["max_fp_rate"] is not None
    (d / freeze.FROZEN_CFG.name).write_text((d / freeze.FROZEN_CFG.name).read_text().replace("max_calls_per_generation: 64", "max_calls_per_generation: 65"))
    with pytest.raises(freeze.FrozenConfigError, match="CHANGED"):
        freeze.require_frozen(d)


def test_missing_frozen_file_refused(tmp_path):
    d = _mk(tmp_path); freeze.freeze(d)
    (d / freeze.FROZEN_FP.name).unlink()
    with pytest.raises(freeze.FrozenConfigError, match="missing"):
        freeze.require_frozen(d)


def test_draft_config_loads_and_matches_defaults():
    assert freeze.load_config().hash() == GuardConfig().hash()


def test_ab_online_gate_accepts_frozen_and_refuses_tampered(tmp_path, capsys):
    from floodlab import ab_online
    d = _mk(tmp_path)
    assert ab_online.main(["--frozen-dir", str(d)]) == 2          # draft only -> refuse
    freeze.freeze(d)
    assert ab_online.main(["--frozen-dir", str(d)]) == 3          # verified (A/B not implemented -> 3)
    f = d / freeze.FROZEN_FP.name
    f.write_text(f.read_text().replace("0.05", "0.5"))
    assert ab_online.main(["--frozen-dir", str(d)]) == 2          # tampered -> refuse
    assert ab_online.main([]) == 2                                 # the repo itself is still unfrozen
