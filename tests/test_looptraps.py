"""Tests for looptraps (no network, no key; fixtures are read-only copies of exploratory-2A traces)."""
import json
import hashlib
from pathlib import Path
import pytest
from floodlab import criteria as CR
from floodlab.canon import sha
import looptraps as lt

ROOT = Path(__file__).resolve().parents[1]


def test_registry_covers_all_families():
    from floodlab.phase2a_families import FAMILIES
    from floodlab.phase2a_mimo_families import MIMO_FAMILIES
    assert set(lt.ENV_NAMES) == set(FAMILIES) | set(MIMO_FAMILIES)
    assert {"M1_fanout_cancel_resend", "M2_rotating_batch", "M3_start_done_alternation", "F1a_cancel_retry_explain", "F3_pagination_backtrack",
            "F7_crossturn_history_primed"} <= set(lt.ENV_NAMES)


@pytest.mark.parametrize("name", lt.ENV_NAMES)
def test_env_deterministic_and_stateless(name):
    a, b = lt.make_env(name, 3), lt.make_env(name, 3)
    assert a.initial_messages() == b.initial_messages() and a.tools == b.tools
    c = a.scenario.mock_cycle[0]
    r1 = a.execute(c["name"], c["arguments"])
    r2 = a.execute(c["name"], json.dumps(c["arguments"]))     # dict or JSON string
    r3 = b.execute(c["name"], c["arguments"])
    for _ in range(5):
        assert a.execute(c["name"], c["arguments"]) == r1     # same result however often it is called
    assert r1 == r2 == r3
    assert "error" not in json.loads(r1) or name in ("F2_repeated_failure",)    # F2's result is itself an upstream-503 error by design


def test_bad_inputs():
    with pytest.raises(KeyError):
        lt.make_env("nope")
    e = lt.make_env("M2_rotating_batch", 1)
    assert "error" in json.loads(e.execute("lookup_order", "{not json"))
    assert "error" in json.loads(e.execute("no_such_tool", {}))


def test_runner_reports_with_frozen_criteria_only():
    res = lt.run_agent(lt.RepeatBatchAgent("M2_rotating_batch", 1), "M2_rotating_batch", 1, max_turns=12)
    assert res.n_calls == 84 and res.n_distinct == 10 and res.termination == "max_turns_12"
    assert res.machine_qualified is True and res.distinct_ratio == round(10 / 84, 4)
    assert "not a flood verdict" in res.labels
    assert CR.CRITERIA_HASH == "26a9753c784b"                   # frozen criteria untouched


def test_guard_and_finishing_agent():
    g = lt.run_agent(lt.RepeatBatchAgent("M2_rotating_batch", 1), "M2_rotating_batch", 1, max_turns=12, guard=lt.max_calls_guard(20))
    assert g.termination == "guard:max_calls_20" and g.n_calls == 14 and not g.machine_qualified
    f = lt.run_agent(lt.GiveUpAfterAgent(lt.RepeatBatchAgent("M3_start_done_alternation", 1), 2), "M3_start_done_alternation", 1)
    assert f.termination == "agent_finished" and f.n_calls == 12 and "Giving up" in f.final_content


def test_call_cap_and_shrink_agent():
    r = lt.run_agent(lt.RepeatBatchAgent("F4_alternating_check_apply", 1), "F4_alternating_check_apply", 1, max_turns=100, call_cap=10)
    assert r.n_calls == 10 and r.termination == "call_cap"
    s = lt.run_agent(lt.ShrinkAfterFailureAgent("M1_fanout_cancel_resend", 1, 2), "M1_fanout_cancel_resend", 1)
    assert s.calls_per_generation[:3] == [12, 12, 1] and s.termination == "max_turns_8"


def test_suite_guard_plumbing_runs_without_claims():
    r = lt.run_agent(lt.RepeatBatchAgent("F3_pagination_backtrack", 1), "F3_pagination_backtrack", 1, max_turns=30, guard=lt.suite_guard("S0"))
    assert r.n_calls >= 1 and (r.termination.startswith("guard:S0") or r.termination.startswith("max_turns"))   # outcome not asserted (draft config)


def test_agent_receives_openai_style_history():
    seen = []

    def spy(messages, tools):
        seen.append(messages)
        return {"tool_calls": [{"name": "lookup_order", "arguments": {"order_id": "ORD-1"}}]} if len(seen) < 3 else {"tool_calls": []}
    lt.run_agent(spy, "M2_rotating_batch", 1)
    assert seen[0][0]["role"] == "system" and seen[0][1]["role"] == "user"
    last = seen[2]
    assert last[-2]["role"] == "assistant" and last[-2]["tool_calls"][0]["id"] == last[-1]["tool_call_id"] and last[-1]["role"] == "tool"


def test_fixtures_match_manifest_and_provenance():
    """Two fixture forms exist. Private/canonical tree: verbatim copies of the stored exploratory traces (MANIFEST is a list; each line is
    checked byte-for-byte against data/exploratory_2A). Public tree: minimized derivations (MANIFEST is {"entries": [...]}); checked by file hash
    and for the absence of model text / provider ids."""
    raw = json.loads((lt.replay.FIXDIR / "MANIFEST.json").read_text())
    fx = lt.load_fixtures()
    assert all(t["split"] == "exploratory-2A" for t in fx.values())
    if isinstance(raw, list):
        assert len(raw) == len(fx) == 12
        for m in raw:
            src = [l for l in (ROOT / m["source"]).read_text().splitlines() if json.loads(l)["run_id"] == m["run_id"]]
            assert len(src) == 1
            assert hashlib.sha256(src[0].encode()).hexdigest() == m["sha256_line"]            # identical to the stored trace
            assert (lt.replay.FIXDIR / m["fixture"]).read_text().splitlines().count(src[0]) == 1
    else:
        man = raw["entries"]
        assert len(man) == len(fx) == 12
        for m in man:
            assert hashlib.sha256((lt.replay.FIXDIR / m["fixture"]).read_bytes()).hexdigest() == m["fixture_file_sha256"]
        blob = "".join(p.read_text() for p in lt.replay.FIXDIR.glob("*.jsonl"))
        assert "reasoning_content" not in blob and "gen-" not in blob and "provider_served" not in blob
        assert all(t["derived"].startswith("minimized") and t["classification"] for t in fx.values())


def test_human_label_prefers_explicit_classification_and_falls_back_to_closeout_table():
    t = lt.get_fixture("M2_rotating_batch-7102")
    derived = lt.human_label({k: v for k, v in t.items() if k != "classification"})
    assert "rejected as human-confirmed flood" in derived
    assert lt.human_label({**t, "classification": derived}) == derived                       # explicit field agrees with the table
    assert lt.human_label({**t, "classification": "custom label"}) == "custom label"          # explicit field wins
    assert lt.human_label({"run_id": "x-M1_fanout_cancel_resend-1"}).startswith("near-miss")
    assert lt.human_label({"run_id": "x-M3_start_done_alternation-1"}).startswith("near-miss")
    assert lt.human_label({"run_id": "x-other-1"}) == "not machine-qualified"
    # whichever fixture form is installed, every shipped run gets the same label as the close-out table
    for rid, tr in lt.load_fixtures().items():
        assert lt.human_label(tr) == lt.human_label({"run_id": rid})


def test_fixture_summaries_match_reports():
    s = {k.split("-")[-1]: lt.summarize_trace(t) for k, t in lt.load_fixtures().items()}
    for seed in ("7102", "7106", "7107", "7108"):
        assert (s[seed]["calls"], s[seed]["distinct"], s[seed]["machine_qualified"]) == (30, 10, True)
        assert "rejected as human-confirmed flood" in s[seed]["human_label"]
    assert (s["7101"]["calls"], s["7101"]["distinct"], s["7101"]["machine_qualified"]) == (25, 8, False)
    assert (s["7103"]["calls"], s["7103"]["distinct"], s["7103"]["machine_qualified"]) == (24, 6, False)
    assert "near-miss" in s["7101"]["human_label"] and "near-miss" in s["7103"]["human_label"]
    assert s["7105"]["calls_per_generation"] == [8, 8, 0]
    assert all("no rate claims" in v["notice"] for v in s.values())


def test_stored_result_hashes_match_environment_code():
    """Re-execute the stored calls against the deterministic envs: the environment code reproduces the stored result hashes (non-cancelled generations)."""
    checked = 0
    for t in lt.load_fixtures().values():
        name = t["provenance"]["scenario"].split("/")[0]
        if name not in lt.ENV_NAMES:
            continue
        env = lt.make_env(name, t["provenance"]["seed"])
        for turn in t["turns"]:
            for g in turn["generations"]:
                for c in g["tool_calls"]:
                    if c.get("result_hash"):
                        assert sha(env.execute(c["name"], c["arguments"])) == c["result_hash"], (t["run_id"], c)
                        checked += 1
    assert checked > 100


def test_replay_agent_reproduces_stored_sequence_and_guard():
    t = lt.get_fixture("M2_rotating_batch-7102")
    res = lt.run_agent(lt.ReplayAgent(t), "M2_rotating_batch", 7102, max_turns=10)
    assert res.n_calls == 30 and res.calls_per_generation == [8, 8, 8, 6] and res.machine_qualified
    assert res.termination == "agent_finished"
    g = lt.run_agent(lt.ReplayAgent(t), "M2_rotating_batch", 7102, max_turns=10, guard=lt.max_calls_guard(20))
    assert g.n_calls == 16 and g.termination == "guard:max_calls_20"


def test_no_network_imports_or_keys():
    for f in (ROOT / "looptraps").glob("*.py"):
        src = f.read_text()
        for bad in ("requests", "httpx", "urllib.request", "socket", "OPENROUTER", "os.environ", "getenv"):
            assert bad not in src, (f.name, bad)


def test_cli_smoke(capsys):
    from looptraps.__main__ import main
    main(["list"]); main(["demo", "--env", "M3_start_done_alternation"]); main(["fixtures"])
    out = capsys.readouterr().out
    assert "M1_fanout_cancel_resend" in out and "scripted stand-ins" in out and "7107" in out


def test_statistics_reported_in_docs_are_derivable_from_the_fixtures():
    """Figures the public docs state without a 'private raw traces' qualifier must be reproducible from the 12 shipped fixtures."""
    fx = lt.load_fixtures()
    gens = lambda t: [len(g["tool_calls"]) for tu in t["turns"] for g in tu["generations"]]
    mimo = {k: t for k, t in fx.items() if "mimo" in str(t["provenance"]["model"])}
    gpt = {k: t for k, t in fx.items() if k not in mimo}
    assert len(fx) == 12 and len(mimo) == 9 and len(gpt) == 3
    mg = [n for t in mimo.values() for n in gens(t)]
    using = [n for n in mg if n > 0]
    assert (len(using), sum(1 for n in using if n >= 2), max(mg)) == (45, 34, 8)                 # "34 of 45 tool-using generations had 2+ calls, max 8"
    assert all(n <= 1 for t in gpt.values() for n in gens(t))                                    # the shipped gpt-oss runs are single-call per generation
    assert sum(1 for t in gpt.values() for n in gens(t) if n == 1) == 38
    s = {k.split("-")[-1]: lt.summarize_trace(t) for k, t in fx.items()}
    assert sorted(k for k, v in s.items() if v["machine_qualified"]) == ["7102", "7106", "7107", "7108"]
    assert (s["7101"]["calls"], s["7101"]["distinct"], s["7103"]["calls"], s["7103"]["distinct"]) == (25, 8, 24, 6)
    assert (s["7104"]["calls"], s["7105"]["calls"], s["7001"]["calls"]) == (18, 16, 18)
    assert (s["6001"]["calls"], s["6004"]["calls"], s["5012"]["calls"]) == (14, 12, 12)
