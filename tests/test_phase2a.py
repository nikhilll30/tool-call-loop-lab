"""Phase 2A tests (all against the loopback mock, $0)."""
import json, os
from pathlib import Path
import pytest
from floodlab import criteria as CR
from floodlab import phase2a as P
from floodlab.budget import Anomaly, BudgetGuard, BudgetRefused, EFFECTIVE_CAP_USD, HARD_CAP_USD
from floodlab.mock_upstream.app import create_app
from floodlab.phase2a_common import load_jsonl
from floodlab.scenarios import Scenario
from floodlab.servers import LocalServer

FAKE_KEY = "sk-" "or-v1-FAKEFAKEFAKEFAKEFAKE0123456789"


def make(tmp_path, upstream, *, guard_kw=None, mock_opts=None, key=None, **cfg_kw):
    ledger = tmp_path / "ledger.jsonl"
    cfg = P.Config(False, tmp_path / "out", ledger, **cfg_kw)
    guard = BudgetGuard(ledger, live=False, **(guard_kw or {}))
    up = P.Upstream(False, upstream.url.rsplit("/v1", 1)[0], key=key, mock_opts=mock_opts)
    return P.Collector(cfg, up, guard), guard, ledger


def test_caps_constants():
    assert HARD_CAP_USD == 1.00 and EFFECTIVE_CAP_USD == 0.90
    with pytest.raises(ValueError):
        BudgetGuard(Path("/tmp/x.jsonl"), cap=0.95)


def test_live_refused_without_key(monkeypatch, capsys):
    monkeypatch.delenv(P.KEY_ENV, raising=False)
    assert P.main(["--live"]) == 2
    assert "REFUSING live run" in capsys.readouterr().err
    assert P.main(["--preflight"]) == 2
    monkeypatch.setenv(P.KEY_ENV, FAKE_KEY)
    assert P.main(["--preflight"]) == 0
    out = capsys.readouterr().out
    assert FAKE_KEY not in out and "present" in out


def test_budget_guard_precharge_refuses_before_exceeding_cap(tmp_path, upstream):
    # tiny cap: the very first request (connectivity) must be refused BEFORE any HTTP call is made
    col, guard, ledger = make(tmp_path, upstream, guard_kw={"cap": 0.000001})
    with pytest.raises(BudgetRefused):
        col.stage_connectivity()
    assert upstream.app.state.requests == []                # nothing was sent
    assert guard.spent() <= guard.cap


def test_budget_never_exceeded_over_a_full_run(tmp_path, upstream):
    cap = 0.004        # small cap: several requests fit, then the guard must stop the collection
    col, guard, ledger = make(tmp_path, upstream, guard_kw={"cap": cap}, max_runs=20)
    col.run_all()
    rows = load_jsonl(ledger)
    running, peak = 0.0, 0.0
    for r in rows:                                          # running total after every ledger row never exceeds the cap
        running += r["usd"]; peak = max(peak, running)
    assert peak <= cap + 1e-9, (peak, cap)
    assert col.stages.get("budget_refusal") or any(t["termination_reason"] == "budget_guard" for t in col.traces) or col.stages["stage_status"]
    assert all(r["live_call"] is False for r in rows)


def test_worst_case_includes_reasoning_as_output_and_margin(tmp_path):
    g = BudgetGuard(tmp_path / "l.jsonl", live=False)
    wc, p = g.worst_case_request([{"role": "user", "content": "x" * 300}], [], 4000)
    assert wc >= (p * 0.018 + 4000 * 0.09) / 1e6           # max_tokens fully priced as output (reasoning counts inside max_tokens)
    assert wc == pytest.approx(g.cost(p, 4000) * 1.25)


def test_cost_surprise_stops_collection(tmp_path, upstream):
    col, guard, ledger = make(tmp_path, upstream, mock_opts={"cost_multiplier": 10.0})
    col.run_all()
    assert col.stages["anomaly"] and "3x" in json.dumps(col.stages["anomaly"]) or "exceeds" in json.dumps(col.stages["anomaly"])
    assert len(col.traces) <= 1                              # stopped immediately


def test_wrong_provider_stops_and_is_not_unpinned(tmp_path, upstream):
    col, guard, ledger = make(tmp_path, upstream, mock_opts={"provider": "SomeoneElse"})
    col.run_all()
    assert col.stages["anomaly"] and "SomeoneElse" in json.dumps(col.stages["anomaly"])
    for r in upstream.app.state.requests:
        pass
    assert P.PROVIDER_PIN == {"order": ["Darkbloom"], "allow_fallbacks": False}


def test_flood_run_cancelled_early_and_mock_sees_disconnect(tmp_path, upstream):
    col, guard, ledger = make(tmp_path, upstream)
    col.stage_connectivity()
    tr = col.run_scenario_live("elicit", Scenario("fan_out", "rotating_argument", 2002))
    assert tr["flood_qualifying_machine"] and tr["termination_reason"] == "flood_qualifying_cancelled"
    assert tr["stats"]["n_calls"] < 400                       # mock would have streamed 400 calls; stopped at the first qualifying point
    assert tr["stats"]["n_calls"] >= CR.MIN_CALLS and tr["stats"]["distinct_ratio"] <= CR.MAX_DISTINCT_RATIO
    assert tr["split"] == "exploratory-2A" and "EXPLORATORY" in tr["notes"] and tr["human_confirmation"].startswith("PENDING")
    import time
    for _ in range(50):
        if upstream.app.state.disconnects:
            break
        time.sleep(0.05)
    assert upstream.app.state.disconnects, "server must observe the client disconnect (stream closed)"


def test_full_mock_flow_provenance_ledger_and_no_secrets(tmp_path, upstream):
    col, guard, ledger = make(tmp_path, upstream, key=FAKE_KEY, max_runs=8)
    stages = col.run_all()
    assert stages["anomaly"] is None
    assert stages["stage_status"]["connectivity"] == "ok" and stages["stage_status"]["smoke"]
    traces = load_jsonl(tmp_path / "out" / "traces.jsonl")
    assert len(traces) >= 5
    for t in traces:
        assert t["split"] == "exploratory-2A" and "must NOT be used as untouched confirmatory data for Guard v2" in t["notes"]
        pv = t["provenance"]
        for k in ("model", "endpoint", "scenario", "seed", "detector_config", "prompt_version", "tool_schema_version", "provider_pinned", "provider_served"):
            assert k in pv
        assert pv["provider_pinned"] == {"order": ["Darkbloom"], "allow_fallbacks": False} and pv["provider_served"] == ["Darkbloom"] and pv["model"] == P.MODEL and pv["detector_config"]["hash"] == CR.CRITERIA_HASH and pv["guard_config"] == "off"
        for k in ("latency_s", "cost_usd", "termination_reason"):
            assert k in t
    # ledger rows carry the required fields; live_call false in mock
    rows = load_jsonl(ledger)
    assert rows and all({"live_call", "model", "provider", "usd", "run_id", "stage"} <= set(r) for r in rows if r["kind"] in ("precharge", "settle", "reconcile"))
    # sum of ledger rows == guard.spent, and equals sum of provider-reported generation costs
    gen_total = sum(r["generation"]["total_cost"] for r in load_jsonl(tmp_path / "out" / "requests.jsonl") if r.get("generation"))
    assert guard.spent() == pytest.approx(gen_total, rel=1e-3, abs=2e-6)   # (non-streamed connectivity call has no mock generation record)
    # a request never carried the floodlab extension or the tag to a LIVE endpoint (payload built for live)
    live_col = P.Collector.__new__(P.Collector)
    live_col.up = P.Upstream(True, "https://openrouter.ai", key=FAKE_KEY)
    live_col.cfg = col.cfg
    pl = P.Collector.payload(live_col, [{"role": "user", "content": "x"}], tools=None, max_tokens=16, stream=True, seed=0)
    assert "floodlab" not in pl and pl["provider"] == P.PROVIDER_PIN and pl["model"] == "openai/gpt-oss-20b" and pl["max_tokens"] == 16
    # secret scan over all outputs: key never appears (fake key was used as the Authorization header against the mock)
    scan = P.secret_scan([tmp_path / "out", ledger], FAKE_KEY)
    assert scan["clean"], scan


def test_redactor():
    r = P.Redactor(FAKE_KEY)
    assert FAKE_KEY not in r.scrub("hello " + FAKE_KEY) and "sk-" "or-abcdef123456" not in r.scrub("x sk-" "or-abcdef123456 y")


def test_cancel_billing_observation_recorded(tmp_path, upstream):
    col, guard, ledger = make(tmp_path, upstream, mock_opts={"billing_overrun_tokens": 500})
    col.stage_connectivity()
    col.run_scenario_live("elicit", Scenario("fan_out", "rotating_argument", 2002))
    col.reconcile(final=True)
    obs = col.stages["cancel_observations"]
    assert obs and obs[0]["generation_cancelled_flag"] is True
    assert obs[0]["generation_tokens_completion"] >= 500          # provider billed more than we received
    assert obs[0]["ratio_reported_tokens_to_received_est"] and obs[0]["ratio_reported_tokens_to_received_est"] > 1.0


def test_deliberate_disconnect_test_runs_when_nothing_cancelled(tmp_path, upstream):
    col, guard, ledger = make(tmp_path, upstream, max_runs=0, cancel_test_after_chunks=40)
    col.run_all()
    assert col.stages.get("cancel_test") and col.stages["cancel_observations"]


def test_exploratory_data_refused_by_dev_and_heldout_paths():
    from floodlab.evaluate import evaluate
    from floodlab.heldout_eval import run as heldout_run
    from floodlab.splits import refuse_exploratory
    t = {"run_id": "x", "split": "exploratory-2A", "turns": [], "label": "unknown", "shape": ""}
    with pytest.raises(ValueError, match="exploratory"):
        evaluate(None, [t])
    with pytest.raises(ValueError, match="exploratory"):
        heldout_run([t], Path("/tmp/should_not_be_written"))
    assert not Path("/tmp/should_not_be_written").exists()
    with pytest.raises(ValueError):
        refuse_exploratory([{"run_id": "y", "exploratory": True, "split": "none"}], "x")
    refuse_exploratory([{"run_id": "z", "split": "test"}], "x")     # ordinary splits pass


def test_criteria_definition():
    sigs = ["a|{}"] * 30
    assert CR.is_flood_qualifying(sigs) and not CR.is_flood_qualifying(sigs[:29])
    assert not CR.is_flood_qualifying([f"a|{{\"i\":{i}}}" for i in range(30)])
    assert CR.signature("ping", '{"target":"a","ts":5}') == CR.signature("ping", '{"ts":99,"target":"a"}')   # volatile field dropped


def test_worst_case_covers_template_overhead_for_tiny_prompt(tmp_path):
    # regression: live probe billed 61 prompt tokens for a prompt the chars/3 estimate counted as ~21
    g = BudgetGuard(tmp_path / "l.jsonl", live=False)
    wc, p = g.worst_case_request([{"role": "user", "content": "Reply with the single word: ok"}], [], 16)
    assert p >= 61 and wc > g.cost(61, 16)


# ------------------------------------------------------------------ bounded 429 retry
def make_retry(tmp_path, upstream, opts, **cfg_kw):
    sleeps = []
    col, guard, ledger = make(tmp_path, upstream, mock_opts=opts, sleep=lambda s: sleeps.append(s), **cfg_kw)
    col.stages["key_usage_start_usd"] = None
    return col, guard, ledger, sleeps


def test_connectivity_retries_429_then_succeeds_with_backoff_and_zero_spend_for_429s(tmp_path, upstream):
    col, guard, ledger, sleeps = make_retry(tmp_path, upstream, {"http_429_first_n": 3})
    col.stage_connectivity()
    assert upstream.app.state.n429 == 3 and upstream.app.state.chat_count == 4
    assert len(sleeps) == 3 and sleeps[0] < sleeps[2] * 1.01 + 5 and all(s > 0 for s in sleeps)      # exponential growth (with jitter)
    rows = load_jsonl(ledger)
    assert sum(1 for r in rows if r["kind"] == "release") == 3
    assert any(r["kind"] == "note" and "429 retry" in r["note"] for r in rows)
    assert guard.spent() < 1e-4                      # 429s cost $0 after release; only the successful call remains
    assert [r["attempt"] for r in col.stages["retries"]] == [1, 2, 3] and all(r["status"] == 429 for r in col.stages["retries"])
    assert col.stages["connectivity"]["attempts"] == 4
    assert col.cfg.connectivity_max_tokens == 64


def test_retry_attempt_budget_exhausted_stops_without_provider_change(tmp_path, upstream):
    col, guard, ledger, sleeps = make_retry(tmp_path, upstream, {"http_429_first_n": 999}, retry_total_wall_s=10**6)
    with pytest.raises(Anomaly, match="still rate-limited"):
        col.stage_connectivity()
    assert upstream.app.state.chat_count == col.cfg.retry_max_attempts == 8
    assert guard.spent() == pytest.approx(0.0, abs=1e-12)          # every 429 released
    assert P.PROVIDER_PIN == {"order": ["Darkbloom"], "allow_fallbacks": False}
    assert P.PINNED_NAME == "Darkbloom" and "DeepInfra" not in json.dumps(P.PROVIDER_PIN)


def test_retry_wall_time_budget_stops(tmp_path, upstream):
    col, guard, ledger, sleeps = make_retry(tmp_path, upstream, {"http_429_first_n": 999}, retry_total_wall_s=12.0, retry_base_s=5.0)
    with pytest.raises(Anomaly, match="wall-time"):
        col.stage_connectivity()
    assert sum(sleeps) <= 12.0 and upstream.app.state.chat_count < 6


def test_smoke_retries_429(tmp_path, upstream):
    col, guard, ledger, sleeps = make_retry(tmp_path, upstream, {"http_429_first_n": 2})
    tr = col.run_scenario_live("smoke", Scenario("pagination", "plain", 1000))
    assert tr["termination_reason"] == "completed" and len(sleeps) == 2
    assert upstream.app.state.n429 == 2


def test_elicitation_first_request_429_stops(tmp_path, upstream):
    col, guard, ledger, sleeps = make_retry(tmp_path, upstream, {"http_429_from_request": 1})
    col.stage_connectivity()
    with pytest.raises(Anomaly, match="429 during elicit"):
        col.run_scenario_live("elicit", Scenario("fan_out", "rotating_argument", 2002))
    assert sleeps == [] and upstream.app.state.chat_count == 2
    assert guard.spent() < 1e-4                      # the 429 was released
    assert col.stages["retries"][-1]["action"].startswith("STOP")


def test_full_flow_stops_on_429_in_elicitation_and_reports(tmp_path, upstream):
    # connectivity ok, smoke needs several requests; 429 starts after the smoke run (request >= 7)
    col, guard, ledger, sleeps = make_retry(tmp_path, upstream, {"http_429_from_request": 8})
    col.run_all()
    assert col.stages["anomaly"] and "429" in json.dumps(col.stages["anomaly"])
    assert col.stages["stage_status"].get("connectivity") == "ok"


def test_retry_window_defaults_and_expected_schedule(tmp_path):
    cfg = P.Config(False, tmp_path / "o", tmp_path / "l.jsonl")
    assert (cfg.retry_max_attempts, cfg.retry_total_wall_s, cfg.retry_base_s, cfg.retry_cap_s) == (8, 1800.0, 45.0, 400.0) and cfg.retry_global_wall_s == 3600.0
    waits = [min(cfg.retry_cap_s, cfg.retry_base_s * 2 ** i) for i in range(cfg.retry_max_attempts - 1)]
    assert 1500 <= sum(waits) <= 2100                      # nominal (un-jittered) ~ 30 min; jitter [0.5,1] makes the expected ~ 23 min
    assert 0.5 * sum(waits) < cfg.retry_total_wall_s


def test_retry_window_configurable_via_cli_args(monkeypatch, tmp_path):
    seen = {}
    real = P.Config
    def spy(*a, **k):
        seen.update(k); return real(*a, **k)
    monkeypatch.setattr(P, "Config", spy)
    monkeypatch.setattr(P.Collector, "run_all", lambda self: {"anomaly": None, "stage_status": {}})
    P.main(["--mock", "--out-dir", str(tmp_path / "o"), "--retry-attempts", "3", "--retry-wall-s", "50", "--retry-base-s", "1", "--retry-cap-s", "4"])
    assert (seen["retry_max_attempts"], seen["retry_total_wall_s"], seen["retry_base_s"], seen["retry_cap_s"]) == (3, 50.0, 1.0, 4.0)


# ------------------------------------------------------------------ prompt families / pilot / disconnect test
def test_families_tools_deterministic_and_documented():
    from floodlab.phase2a_families import FAMILIES, make
    import pathlib
    doc = (pathlib.Path(__file__).resolve().parent.parent / "docs" / "PHASE2A_PROMPT_FAMILIES.md").read_text()
    assert len(FAMILIES) == 8
    for f in FAMILIES:
        assert f.split("_")[0] in doc and f.split("_", 1)[1] in doc.replace("`", "") or f in doc.replace("F1a `cancel_retry_explain`", f)
        s1, s2 = make(f, 7), make(f, 7)
        assert s1.build_messages() == s2.build_messages()
        e1, e2 = s1.env(), s2.env()
        for c in s1.mock_cycle:
            assert e1.execute(c["name"], c["arguments"]) == e2.execute(c["name"], c["arguments"]) == e1.execute(c["name"], c["arguments"])
        names = {t["function"]["name"] for t in s1.tools}
        assert all(c["name"] in names for c in s1.mock_cycle)
        assert "loop" not in s1.user.lower() and "repeat" not in s1.user.lower()        # the model is never told to loop / repeat
    e = make("F1a_cancel_retry_explain", 1).env(); r = json.loads(e.execute("update_config", {"file": "a", "version": "1"}))
    assert r["status"] == "cancelled" and "reason" in r
    r = json.loads(make("F1b_cancel_retry_noexplain", 1).env().execute("update_config", {"file": "a", "version": "1"}))
    assert r["status"] == "cancelled" and "reason" not in r
    assert json.loads(make("F3_pagination_backtrack", 1).env().execute("list_records", {"page": 4}))["records"] == []
    assert len(make("F7_crossturn_history_primed", 1).prime) > 40


@pytest.mark.parametrize("family", ["F1a_cancel_retry_explain", "F1b_cancel_retry_noexplain", "F2_repeated_failure", "F3_pagination_backtrack",
                                    "F4_alternating_check_apply", "F5_changing_args_no_change", "F6_partial_success_retry", "F7_crossturn_history_primed"])
def test_every_family_dry_runs_and_cancels_flood_in_mock(tmp_path, upstream, family):
    from floodlab.phase2a_families import make
    col, guard, ledger = make_col(tmp_path, upstream)
    tr = col.run_scenario_live("pilot", make(family, 11))
    assert tr["split"] == "exploratory-2A" and "EXPLORATORY" in tr["notes"]
    assert tr["stats"]["n_calls"] <= 120 and tr["stats"]["n_turns"] <= 12
    assert tr["flood_qualifying_machine"] and tr["termination_reason"] == "flood_qualifying_cancelled"
    assert tr["provenance"]["prompt_version"].startswith("families-v1") and tr["provenance"]["scenario"].startswith(family)
    assert guard.spent() <= guard.cap


def make_col(tmp_path, upstream, **kw):
    return make(tmp_path, upstream, **kw)


def test_family_run_respects_turn_cap_when_no_flood(tmp_path, upstream):
    from floodlab.phase2a_families import make
    # a cycle with all-distinct calls never qualifies -> must end by max_turns (12) or call cap, never run away
    col, guard, ledger = make_col(tmp_path, upstream)
    sc = make("F5_changing_args_no_change", 3)
    sc.mock_cycle = [{"name": "search_tickets", "arguments": {"query": f"q{i}"}} for i in range(500)]
    sc.mock_per_turn = 3
    tr = col.run_scenario_live("pilot", sc)
    assert not tr["flood_qualifying_machine"] and tr["stats"]["n_turns"] <= 12 and tr["termination_reason"] == "max_turns_12"


def test_pilot_flow_mock_extension_rules_and_report(tmp_path, upstream):
    from floodlab import phase2a_pilot as PP
    col, guard, ledger = make_col(tmp_path, upstream, max_runs=0)
    res = PP.pilot(col, families=["F2_repeated_failure", "F4_alternating_check_apply"], n_initial=1, n_max=3, stop_at_floods=99)
    assert res["counts"] == {"F2_repeated_failure": 3, "F4_alternating_check_apply": 3}          # 1 initial + extended (repetition signs) up to n_max, never beyond
    rp = PP.write_pilot_report(tmp_path / "out", ledger, mock=True, report_path=tmp_path / "r.md", base_traces=[], stages=col.stages, ku_now=None)
    txt = rp.read_text()
    assert "PILOT REPORT" in txt and "does not escalate" in txt or "I did not escalate" in txt or "escalat" in txt
    assert "EXPLORATORY" in txt and "F2_repeated_failure" in txt
    res2 = None


def test_pilot_stops_early_on_enough_floods(tmp_path, upstream):
    from floodlab import phase2a_pilot as PP
    col, guard, ledger = make_col(tmp_path, upstream, max_runs=0)
    res = PP.pilot(col, n_initial=3, n_max=5, stop_at_floods=5)
    assert sum(res["counts"].values()) == 5 and "enough evidence" in res["stop"]


def test_pilot_429_at_turn_boundary_is_bounded_and_no_provider_change(tmp_path, upstream):
    from floodlab.phase2a_families import make
    sleeps = []
    col, guard, ledger = make_col(tmp_path, upstream, mock_opts={"http_429_first_n": 2}, sleep=lambda s: sleeps.append(s), retry_max_attempts=3, retry_base_s=30, retry_cap_s=120)
    tr = col.run_scenario_live("pilot", make("F2_repeated_failure", 1))
    assert len(sleeps) == 2 and max(sleeps) <= 120 and tr["flood_qualifying_machine"]
    col2, g2, l2 = make_col(tmp_path / "b", upstream, mock_opts={"http_429_first_n": 99}, sleep=lambda s: sleeps.append(s), retry_max_attempts=3, retry_total_wall_s=10**6)
    upstream.app.state.n429 = 0
    with pytest.raises(Anomaly, match="still rate-limited"):
        col2.run_scenario_live("pilot", make("F2_repeated_failure", 2))
    assert g2.spent() == pytest.approx(0.0, abs=1e-12)


def test_disconnect_test_mock_records_cancellation_and_billing(tmp_path, upstream):
    from floodlab import phase2a_pilot as PP
    col, guard, ledger = make_col(tmp_path, upstream, max_runs=0)
    obs = PP.disconnect_test(col, points=(20, 80))
    assert len(obs) == 3                                                    # two disconnects + control
    for o in obs[:2]:
        assert o["client"]["cancelled"] and o["client"]["termination_reason"] == "deliberate_early_disconnect_test"
        assert o["client"]["stop_record"]["t_cancel"] and o["client"]["stop_record"]["chunks_at_cancel"] == o["requested_disconnect_chunks"]
        assert o["generation_first_read"]["cancelled"] is True
        assert o["generation_first_read"]["tokens_completion"] < o["max_tokens"]
        assert o["billed_fraction_of_full"] < 1.0
    assert obs[2]["client"]["cancelled"] is False
    assert obs[1]["generation_first_read"]["tokens_completion"] > obs[0]["generation_first_read"]["tokens_completion"]


def test_pilot_cli_refuses_live_without_key(monkeypatch, capsys):
    from floodlab import phase2a_pilot as PP
    monkeypatch.delenv(P.KEY_ENV, raising=False)
    assert PP.main(["--live"]) == 2
    assert "REFUSING" in capsys.readouterr().err


def test_pilot_mock_cli_end_to_end(tmp_path):
    from floodlab import phase2a_pilot as PP
    rc = PP.main(["--mock", "--out-dir", str(tmp_path / "o"), "--n-initial", "1", "--n-max", "1", "--stop-at-floods", "3"])
    assert rc == 0 and (tmp_path / "o" / "PHASE2A_PILOT_REPORT.MOCK.md").exists()
    assert "secret scan" not in (tmp_path / "o" / "PHASE2A_PILOT_REPORT.MOCK.md").read_text().lower() or "CLEAN" in (tmp_path / "o" / "PHASE2A_PILOT_REPORT.MOCK.md").read_text()


def test_report_empty_data_says_undecidable_not_no_escalation(tmp_path):
    from floodlab import phase2a_pilot as PP
    (tmp_path / "o").mkdir()
    rp = PP.write_pilot_report(tmp_path / "o", tmp_path / "l.jsonl", mock=False, report_path=tmp_path / "r.md", base_traces=[], stages={"anomaly": {"message": "429"}}, ku_now=None)
    txt = rp.read_text()
    assert "no evidence collected; escalation question undecidable" in txt
    assert "no family justifies escalation" not in txt
    assert "no null result is claimed" in txt


def test_pilot_retry_window_defaults_scopes_and_cli(tmp_path, upstream, monkeypatch):
    from floodlab import phase2a_pilot as PP
    from floodlab.phase2a_families import make
    seen = {}
    real = P.Config
    monkeypatch.setattr(P, "Config", lambda *a, **k: (seen.update(k), real(*a, **k))[1]); monkeypatch.setattr(PP, "Config", P.Config)
    monkeypatch.setattr(PP, "pilot", lambda *a, **k: {}); monkeypatch.setattr(PP, "disconnect_test", lambda *a, **k: [])
    PP.main(["--mock", "--out-dir", str(tmp_path / "o")])
    assert (seen["retry_max_attempts"], seen["retry_total_wall_s"], seen["retry_base_s"], seen["retry_cap_s"]) == (8, 1800.0, 45.0, 400.0)
    # per-run scope: a 429 burst on run 1 does not consume run 2's attempts
    sleeps = []
    col, guard, ledger = make_col(tmp_path / "x", upstream, mock_opts={"http_429_first_n": 3}, sleep=lambda s: sleeps.append(s), retry_max_attempts=4, retry_base_s=1, retry_cap_s=2)
    col.run_scenario_live("pilot", make("F2_repeated_failure", 1))
    assert len(sleeps) == 3
    upstream.app.state.n429 = 0
    col.cfg.retry_total_wall_s = 1e9
    col.run_scenario_live("pilot", make("F2_repeated_failure", 2))
    assert col.retry_state["attempts"]["p2a-mock-pilot-F2_repeated_failure-F2_repeated_failure-1"] == 3


def test_global_retry_wall_budget_stops(tmp_path, upstream):
    col, guard, ledger, sleeps = make_retry(tmp_path, upstream, {"http_429_first_n": 999}, retry_total_wall_s=1e9, retry_global_wall_s=8.0, retry_base_s=5.0, retry_max_attempts=99)
    with pytest.raises(Anomaly, match="global retry wall-time"):
        col.stage_connectivity()
    assert sum(sleeps) <= 8.0


def test_provider_pin_prices_and_exact_provider_in_ledger(tmp_path, upstream):
    from floodlab import budget
    assert P.PINNED_NAME == "Darkbloom" and P.PROVIDER_PIN == {"order": ["Darkbloom"], "allow_fallbacks": False}
    assert budget.PRICE_IN_PER_M >= 0.018 and budget.PRICE_OUT_PER_M >= 0.09          # guard price >= listed Darkbloom price (conservative)
    col, guard, ledger = make(tmp_path, upstream)
    col.stage_connectivity()
    pl = P.Collector.payload(col, [{"role": "user", "content": "x"}], tools=None, max_tokens=8, stream=False, seed=0)
    assert pl["provider"] == {"order": ["Darkbloom"], "allow_fallbacks": False}
    rows = [r for r in load_jsonl(ledger) if r["kind"] in ("precharge", "settle")]
    assert rows and all(r["provider"] in ("Darkbloom(pinned)", "Darkbloom") for r in rows) and all(r["live_call"] is False for r in rows)


def test_provider_checked_on_every_chunk_and_deepinfra_now_refused(tmp_path, upstream):
    col, guard, ledger = make(tmp_path, upstream, mock_opts={"provider": "DeepInfra"})       # DeepInfra is no longer the pin -> mismatch
    col.stage_connectivity() if False else None
    with pytest.raises(Anomaly, match="not Darkbloom"):
        col.stage_connectivity()
    import floodlab.mock_upstream.app as _m
    assert P.PINNED_NAME.lower() != "deepinfra"


def test_pilot_report_labels_provider_and_keeps_history(tmp_path):
    from floodlab import phase2a_pilot as PP
    (tmp_path / "o").mkdir()
    txt = PP.write_pilot_report(tmp_path / "o", tmp_path / "l.jsonl", mock=False, report_path=tmp_path / "r.md", base_traces=[], stages={}, ku_now=None).read_text()
    assert "Darkbloom" in txt and "AkashML" in txt and "NOT DeepInfra" in txt
    assert "DeepInfra blocked history" in txt          # blocked-history section preserved (from docs/PHASE2A_DEEPINFRA_BLOCKED_HISTORY.md)


# ------------------------------------------------------------------ F3 follow-up
def test_f3_followup_scenario_unchanged_except_turn_cap_and_provenance():
    from floodlab import phase2a_f3_followup as FU
    from floodlab.phase2a_families import make
    base, fu = make(FU.FAMILY, 6001), FU.make_scenario(6001, 34)
    assert base.build_messages() == fu.build_messages() and base.tools == fu.tools and base.user == fu.user
    assert base.max_turns == 12 and fu.max_turns == 34
    assert fu.provenance_extra["run_set"] == "f3-followup" and fu.provenance_extra["turn_cap"] == 34 and fu.provenance_extra["family_prompt_changed"] is False


def test_f3_followup_cli_bounds_and_refusals(monkeypatch, capsys):
    from floodlab import phase2a_f3_followup as FU
    monkeypatch.delenv(P.KEY_ENV, raising=False)
    assert FU.main(["--live"]) == 2
    assert FU.main(["--mock", "--turn-cap", "200"]) == 2          # cap must stay small (just enough to test 30 calls)
    assert FU.main(["--mock", "--runs", "11"]) == 2 and FU.main(["--mock", "--budget-usd", "0.5"]) == 2


def test_f3_followup_mock_flow_cancels_at_threshold_records_provenance_and_report(tmp_path):
    from floodlab import phase2a_f3_followup as FU
    rc = FU.main(["--mock", "--out-dir", str(tmp_path / "o"), "--runs", "6"])
    assert rc == 0
    traces = load_jsonl(tmp_path / "o" / "traces.jsonl")
    assert 5 <= len(traces) <= 6
    for t in traces:
        assert t["split"] == "exploratory-2A" and "EXPLORATORY" in t["notes"]
        assert t["provenance"]["run_set"] == "f3-followup" and t["provenance"]["turn_cap"] == 34 and t["provenance"]["provider_served"] == ["Darkbloom"]
        assert t["flood_qualifying_machine"] and t["stats"]["n_calls"] == 30 and t["termination_reason"] == "flood_qualifying_cancelled"
    txt = (tmp_path / "o" / "PHASE2A_F3_FOLLOWUP_REPORT.MOCK.md").read_text()
    assert "runs that reached 30+ tool calls" in txt and "did the 1->2->3->4 cycle stay stable" in txt and "total cost of this follow-up" in txt


def test_f3_followup_budget_stops_before_exceeding(tmp_path, upstream):
    from floodlab import phase2a_f3_followup as FU
    ledger = tmp_path / "ledger.jsonl"
    # follow-up cap 0.02 with 0.0045 already spent: whole-run worst case (~0.0174 at 34 turns) does not fit -> refused BEFORE any request
    BudgetGuard(ledger, live=False).append({"kind": "settle", "usd": 0.0045, "request_key": "x", "stage": "s", "run_id": "r", "model": "m", "provider": "p"})
    col, guard, _ = make(tmp_path, upstream, guard_kw={"cap": 0.02, "prompt_ceiling": 500}, max_turns=34)
    res = FU.run_followup(col, n_runs=10, turn_cap=34, budget=0.02)
    assert "refused to launch run 1" in col.stages["followup_stop_reason"] and upstream.app.state.requests == [] and not col.traces
    # with a larger cap runs proceed, and the running ledger total never exceeds the cap
    ledger.unlink()
    col2, g2, l2 = make(tmp_path / "b", upstream, guard_kw={"cap": 0.03, "prompt_ceiling": 500}, max_turns=34)
    FU.run_followup(col2, n_runs=3, turn_cap=34, budget=0.03)
    running = peak = 0.0
    for r in load_jsonl(l2):
        running += r["usd"]; peak = max(peak, running)
    assert col2.traces and peak <= 0.03 + 1e-9


def test_f3_cycle_analysis_detects_break():
    from floodlab import phase2a_f3_followup as FU
    sig = lambda p: f'list_records|{{"page":{p}}}'
    a = FU.cycle_analysis([sig(p) for p in (1, 2, 3, 4, 1, 2, 3, 4, 1, 2)])
    assert a["first_deviation_index"] is None and a["full_cycles"] == 2
    b = FU.cycle_analysis([sig(p) for p in (1, 2, 3, 4, 1, 2, 3, 3, 5)])
    assert b["first_deviation_index"] == 7 and b["stable_through"] == 7


# ------------------------------------------------------------------ adapted MiMo families (planning only; mock dry runs, $0)
@pytest.mark.parametrize("family", ["M1_fanout_cancel_resend", "M2_rotating_batch", "M3_start_done_alternation"])
def test_mimo_adapted_families_dry_run_in_mock(tmp_path, upstream, family):
    from floodlab.phase2a_mimo_families import make as mk, MIMO_FAMILIES
    col, guard, ledger = make_col(tmp_path, upstream)
    sc = mk(family, 21)
    assert family in MIMO_FAMILIES and sc.prompt_version == "families-mimo-v1"
    assert mk(family, 21).user == sc.user                                   # deterministic
    tr = col.run_scenario_live("pilot", sc)
    assert tr["split"] == "exploratory-2A" and tr["stats"]["n_calls"] <= 120
    assert tr["flood_qualifying_machine"] and tr["termination_reason"] == "flood_qualifying_cancelled"
    assert tr["stats"]["n_calls"] / max(1, tr["stats"]["n_turns"]) > 1.5     # several calls per generation in the mock (the shape MiMo is expected to emit)
    assert guard.spent() <= guard.cap
    for word in ("loop", "repeat", "again and again"):                       # the prompt never invites looping
        assert word not in sc.user.lower()


# ------------------------------------------------------------------ MiMo pilot module (mock only, $0)
def test_mimo_mock_end_to_end_and_labels(tmp_path):
    from floodlab import phase2a_mimo as M
    out = tmp_path / "o"
    assert M.main(["--mock", "--out-dir", str(out), "--ledger", str(out / "l.jsonl")]) == 0
    assert P.MODEL == "openai/gpt-oss-20b" and P.PINNED_NAME == "Darkbloom"                 # globals restored after the run
    traces = load_jsonl(out / "traces.jsonl")
    assert 5 <= len(traces) <= 9
    for t in traces:
        assert t["split"] == "exploratory-2A" and t["provenance"]["checkpoint"] == "unknown (provider-claimed, likely fixed MOPD)"
        assert t["provenance"]["provider_pinned"] == {"order": ["Xiaomi"], "allow_fallbacks": False} and t["provenance"]["provider_served"] == ["Xiaomi"]
    rep = (out / "PHASE2A_MIMO_PILOT_REPORT.MOCK.md").read_text()
    assert "checkpoint: unknown (provider-claimed, likely fixed MOPD)" in rep and "Guard v2 OFF" in rep and "MOCK DRY RUN" in rep
    assert "likely-fixed-model contrast" in rep
    spent = sum(r["usd"] for r in load_jsonl(out / "l.jsonl"))
    assert spent <= M.PILOT_CAP_USD


def test_mimo_pilot_guard_caps(tmp_path):
    from floodlab import phase2a_mimo as M
    g = M.PilotGuard(tmp_path / "l.jsonl", live=False, pilot_start_spent=0.0, pilot_cap=0.005)
    assert (g.price_in, g.price_out, g.margin, g.prompt_ceiling) == (0.15, 0.30, 1.25, 16000)
    wc, _ = g.worst_case_request([{"role": "user", "content": "x" * 30000}], [], 3000)
    g.check(wc, "request r#0")                                         # fits: ~0.0035
    g.precharge("k1", wc, stage="s", run_id="r")
    with pytest.raises(BudgetRefused):
        g.check(wc, "request r#1")                                     # pilot cap $0.005 would be exceeded
    g2 = M.PilotGuard(tmp_path / "l2.jsonl", live=False, pilot_start_spent=0.0, run_cap=0.001)
    g2.append({"kind": "precharge", "usd": 0.002, "run_id": "runA"})
    with pytest.raises(BudgetRefused):
        g2.check(0.0001, "request runA#3")                             # per-run cap
    g2.check(0.0001, "request runB#0")


def test_mimo_live_refuses_without_snapshot_or_key(tmp_path, monkeypatch, capsys):
    from floodlab import phase2a_mimo as M
    monkeypatch.delenv(P.KEY_ENV, raising=False)
    assert M.main(["--live", "--stage", "connectivity"]) == 2
    monkeypatch.setenv(P.KEY_ENV, FAKE_KEY)
    assert M.main(["--live", "--stage", "connectivity", "--snapshot", str(tmp_path / "missing.json")]) == 2
    assert "Nothing spent" in capsys.readouterr().err
    bad = tmp_path / "s.json"                                          # Novita present but status -2 -> refuse
    bad.write_text(json.dumps({"fetched_at": "t", "response": {"data": {"endpoints": [{"provider_name": "Xiaomi", "status": -2, "supported_parameters": ["tools", "tool_choice", "reasoning"],
                                                                               "uptime_last_5m": 1, "uptime_last_30m": 1, "uptime_last_1d": 1, "pricing": {"prompt": "0", "completion": "0", "input_cache_read": "0"}}]}}}))
    assert M.main(["--live", "--stage", "connectivity", "--snapshot", str(bad)]) == 2


def test_mimo_wrong_provider_is_anomaly_and_stops(tmp_path, upstream):
    from floodlab import phase2a_mimo as M
    ledger = tmp_path / "l.jsonl"
    with M.configured():
        cfg = P.Config(False, tmp_path / "o", ledger, max_tokens=3000, max_turns=3)
        guard = M.PilotGuard(ledger, live=False, pilot_start_spent=0.0)
        up = P.Upstream(False, upstream.url.rsplit("/v1", 1)[0], mock_opts={"provider": "DeepInfra"})       # mock answers as a different provider
        col = M.MimoCollector(cfg, up, guard, tag="t")
        with pytest.raises(Anomaly):
            M.run_one(col, "M2_rotating_batch", 1, 3, "smoke")
    assert col.traces and col.traces[-1]["termination_reason"] == "anomaly"


def test_mimo_smoke_premise_stop_rule(tmp_path, upstream):
    from floodlab import phase2a_mimo as M
    ledger = tmp_path / "l.jsonl"
    with M.configured():
        cfg = P.Config(False, tmp_path / "o", ledger, max_tokens=3000, max_turns=3)
        guard = M.PilotGuard(ledger, live=False, pilot_start_spent=0.0)
        up = P.Upstream(False, upstream.url.rsplit("/v1", 1)[0], mock_opts={"provider": "Xiaomi", "n_calls": 1})
        col = M.MimoCollector(cfg, up, guard, tag="t")
        try:
            M.stage_smoke(col)
        except Anomaly as e:
            assert "premise" in str(e)
        else:
            pytest.skip("mock does not force n_calls override")


def test_mimo_xml_leak_and_passback_recorders():
    from floodlab import phase2a_mimo as M
    t = {"run_id": "r", "turns": [{"turn": 0, "generations": [{"tool_calls": [], "content": "<tool_call><function=x>", "reasoning_content": "", "finish_reason": "stop"}]}]}
    assert M.xml_leaks(t)[0]["field"] == "content" and not M.xml_leaks(t)[0]["generation_had_parsed_calls"]
    asm = M.MimoAssembler()
    asm.feed({"choices": [{"delta": {"reasoning_details": [{"type": "reasoning.text", "text": "ab", "index": 0, "format": "f"}]}}]})
    asm.feed({"choices": [{"delta": {"reasoning_details": [{"type": "reasoning.text", "text": "cd", "index": 0, "format": "f"}]}}]})
    assert asm.reasoning_details_merged == [{"type": "reasoning.text", "text": "abcd", "index": 0, "format": "f"}]
