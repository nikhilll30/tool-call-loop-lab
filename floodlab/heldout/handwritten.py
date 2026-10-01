"""Hand-written HELD-OUT cases (6 floods, 12 legitimate). Literal structures, different from dev/handwritten.py."""
from __future__ import annotations
from .common import mk, R, one_per_turn


def heldout_handwritten() -> list[dict]:
    T = []
    # ---------------- floods ----------------
    cyc = [("read_file", {"path": "a.txt"}), ("search", {"query": "x"}), ("get_doc", {"id": "d1"})]
    calls = [(n, a, R(same=1)) for _ in range(14) for n, a in cyc]
    T.append(mk("ho-hw-F-lcm3tool", "hw_flood_3tool_cycle", "flood", -1, one_per_turn(calls), 3, "literal A,B,C cycle spread one call per turn, 14 laps"))
    T.append(mk("ho-hw-F-oscillate", "hw_flood_oscillating_edit", "flood", -1,
                [[("edit_file", {"path": "m.py", "content": "AB"[i % 2]}, R(ok=1)), ("run_tests", {"cmd": "pytest"}, R(failing=3))] for i in range(30)], 5,
                "oscillating edit, identical failing tests"))
    T.append(mk("ho-hw-F-querycreep", "hw_flood_query_creep", "flood", -1,
                one_per_turn([("search", {"query": "python async bug" + " please" * i}, R(hits=[])) for i in range(40)]), 1,
                "query grows by one word each call; always empty"))
    T.append(mk("ho-hw-F-poll-reread", "hw_flood_poll_then_reread", "flood", -1,
                one_per_turn([c for _ in range(20) for c in [("get_job_status", {"job": "x"}, R(s="running")), ("read_file", {"path": "out.log"}, R(c=""))]]), 2,
                "poll job + reread empty log forever; period 2 with different tools"))
    T.append(mk("ho-hw-F-sameerror", "hw_flood_same_error_retry", "flood", -1,
                one_per_turn([("run_query", {"sql": "SELECT * FROM t WHERE id = 1"}, R(err="syntax error near WHERE"))] * 25), 1,
                "byte-identical failing query retried 25 times"))
    ids = ["u1", "u2", "u3"]
    T.append(mk("ho-hw-F-startdone3", "hw_flood_startdone_3ids", "flood", -1,
                [[c for i in range(30) for c in [("start_job", {"job": ids[i % 3]}, R(ok=1)), ("get_job_status", {"job": ids[(i + 1) % 3]}, R(s="running"))]]], 6,
                "3-id start/done alternation, 60 calls, one generation"))
    # ---------------- legitimate ----------------
    T.append(mk("ho-hw-L-poll60", "hw_legit_poll_plateau60", "legitimate", -1,
                one_per_turn([("get_job_status", {"job": "train"}, R(s="running", p=0)) for _ in range(60)] + [("get_job_status", {"job": "train"}, R(s="done", p=100))]), None,
                "60-poll unchanged plateau then done (bounded wait) - longer than any dev case"))
    T.append(mk("ho-hw-L-backoff-capped", "hw_legit_backoff_capped_plateau", "legitimate", -1,
                one_per_turn([("fetch", {"url": "u", "wait_s": min(30, 2 ** i)}, R(err=503) if i < 9 else R(ok=1)) for i in range(10)]), None, "backoff capped at 30s; changing wait param"))
    T.append(mk("ho-hw-L-tokenrefresh", "hw_legit_token_refresh_retry", "legitimate", -1,
                one_per_turn([("api_call", {"endpoint": "/me", "token": f"t{i}"}, R(err=401) if i < 2 else R(ok=1)) for i in range(3)]
                             + [("api_call", {"endpoint": "/orders", "token": "t2"}, R(orders=[1, 2]))]), None, "401 -> refreshed token -> success"))
    T.append(mk("ho-hw-L-dup-page", "hw_legit_pagination_duplicate_page", "legitimate", -1,
                one_per_turn([("list_items", {"cursor": c}, R(page=p)) for c, p in [(None, 0), ("a", 1), ("b", 2), ("b", 3), ("c", 4), ("d", 5)]]), None,
                "server returns different page for the same cursor after retry (cursor quirk)"))
    T.append(mk("ho-hw-L-resample45", "hw_legit_repeated_subcalls_fanout", "legitimate", -1,
                [[("query_metric", {"name": f"m{i % 3}"}, R(v=i * 0.37)) for i in range(45)]], None, "45 calls over 3 metrics in one generation; every sample differs"))
    T.append(mk("ho-hw-L-write-read", "hw_legit_write_read_verify", "legitimate", -1,
                [[("edit_file", {"path": "c.yaml", "content": "v1"}, R(ok=1))], [("read_file", {"path": "c.yaml"}, R(c="v1"))],
                 [("edit_file", {"path": "c.yaml", "content": "v2"}, R(ok=1))], [("read_file", {"path": "c.yaml"}, R(c="v2"))]], None, "write then verify read, twice"))
    T.append(mk("ho-hw-L-testrerun", "hw_legit_test_rerun_stagnation", "legitimate", -1,
                [g for i in range(6) for g in ([("run_tests", {"cmd": "pytest"}, R(failing=4))], [("edit_file", {"path": f"f{i}.py", "content": f"x{i}"}, R(ok=1))])], None,
                "tests rerun after each of 6 distinct edits with failing count stuck at 4 (stagnation, but real edits)"))
    T.append(mk("ho-hw-L-noisypoll", "hw_legit_noisy_poll", "legitimate", -1,
                one_per_turn([("get_status", {"svc": "db"}, R(state="starting", t=i * 1.7, rid=f"r{i}")) for i in range(15)] + [("get_status", {"svc": "db"}, R(state="up", t=99.9, rid="rZ"))]), None,
                "15 polls with unchanged state and fresh noise fields, then up"))
    T.append(mk("ho-hw-L-fanout70", "hw_legit_fanout70_distinct", "legitimate", -1,
                [[("read_file", {"path": f"logs/{i:03d}.log"}, R(n=i)) for i in range(70)]], None, "70 distinct reads in one generation (exceeds a 64-call cap)"))
    T.append(mk("ho-hw-L-oneretry", "hw_legit_single_retry", "legitimate", -1,
                one_per_turn([("run_query", {"sql": "SELECT 1"}, R(err="timeout")), ("run_query", {"sql": "SELECT 1"}, R(rows=[[1]]))]), None, "one identical retry after a timeout"))
    T.append(mk("ho-hw-L-search-doc", "hw_legit_alternating_search_doc", "legitimate", -1,
                one_per_turn([c for i in range(12) for c in [("search", {"query": f"q{i}"}, R(hit=i)), ("get_doc", {"id": f"d{i}"}, R(t=i))]]), None, "distinct search/get_doc alternation"))
    T.append(mk("ho-hw-L-monitor4", "hw_legit_monitor_4_services", "legitimate", -1,
                [[("get_status", {"svc": s}, R(state="starting" if t < 4 and s == "db" else "up", t=t)) for s in ("web", "db", "cache", "queue")] for t in range(7)], None,
                "same 4-service batch each turn; only db changes state; others identical 'up'"))
    return T
