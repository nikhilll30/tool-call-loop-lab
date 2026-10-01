"""Small hand-written legitimate set (literal traces, no generators). `hard` cases are legitimate work that
is genuinely hard to tell from a flood WITHOUT ground-truth of state; they are included on purpose."""
from __future__ import annotations
import json
from .common import build


def _r(**kw):
    return json.dumps(kw, sort_keys=True)


def handwritten_legit() -> list[dict]:
    T = []
    # 1. paginate a repo listing, 6 pages, one call per turn
    T.append(build("hw-legit-paginate", shape="hw_pagination", label="legitimate", seed=-1,
                   gens=[[("list_items", {"cursor": c}, _r(page=i))] for i, c in enumerate([None, "5", "10", "15", "20", "25"])],
                   note="HAND-WRITTEN"))
    # 2. fan out reads of 25 distinct files then a summary write
    T.append(build("hw-legit-fanout25", shape="hw_fanout", label="legitimate", seed=-1,
                   gens=[[("read_file", {"path": f"docs/ch{i:02d}.md"}, _r(text=f"chapter {i}")) for i in range(25)],
                         [("edit_file", {"path": "docs/summary.md", "content": "summary"}, _r(ok=True))]], note="HAND-WRITTEN"))
    # 3. retry with backoff arguments
    T.append(build("hw-legit-backoff", shape="hw_retry", label="legitimate", seed=-1,
                   gens=[[("fetch", {"source": "primary", "attempt": i, "wait_s": 2 ** i}, _r(err=503 if i < 3 else 200))] for i in range(4)],
                   note="HAND-WRITTEN"))
    # 4. HARD: poll a job; result text identical 'running' for 8 polls then 'done' (only final poll differs)
    T.append(build("hw-legit-hard-poll-plateau", shape="hw_hard_poll_plateau", label="legitimate", seed=-1,
                   gens=[[("get_job_status", {"job": "index"}, _r(status="running" if i < 8 else "done"))] for i in range(9)],
                   note="HAND-WRITTEN HARD: legit polling whose observable state does not change until the last poll"))
    # 5. read-edit-test cycle over 3 files, results differ each time
    g = []
    for i in range(9):
        g.append([("read_file", {"path": f"src/mod_0{i % 3}.py"}, _r(v=i)), ("edit_file", {"path": f"src/mod_0{i % 3}.py", "content": f"v{i}"}, _r(ok=True)),
                  ("run_tests", {}, _r(failing=9 - i))])
    T.append(build("hw-legit-rwt-cycle", shape="hw_read_edit_test", label="legitimate", seed=-1, gens=g, note="HAND-WRITTEN"))
    # 6. HARD: same search repeated 3 times across turns with different results (index updating)
    T.append(build("hw-legit-repeat-search", shape="hw_repeat_search", label="legitimate", seed=-1,
                   gens=[[("search", {"query": "status"}, _r(hits=i))] for i in range(3)], note="HAND-WRITTEN"))
    return T
