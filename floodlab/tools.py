"""Deterministic mock tools with simulated external state.

MockEnv(scenario, seed) owns all state. execute(name, args) -> str (JSON text).
Same (scenario, seed, call sequence) -> same results. No network, no clock, no randomness
outside random.Random(seed).
"""
from __future__ import annotations
import json, random
from .canon import canonical_json

TOOL_SCHEMA_VERSION = "tools-v1"

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": n, "description": d, "parameters": {"type": "object", "properties": p, "required": list(p)}}}
    for n, d, p in [
        ("list_items", "List items, paginated.", {"cursor": {"type": ["string", "null"]}}),
        ("fetch", "Fetch a resource from a source (primary or mirror).", {"source": {"type": "string"}}),
        ("list_dir", "List a directory.", {"path": {"type": "string"}}),
        ("read_file", "Read a file.", {"path": {"type": "string"}}),
        ("edit_file", "Replace the content of a file.", {"path": {"type": "string"}, "content": {"type": "string"}}),
        ("run_tests", "Run the test-suite.", {}),
        ("search", "Search documents.", {"query": {"type": "string"}}),
        ("get_doc", "Get a document by id.", {"id": {"type": "string"}}),
        ("get_author", "Get author info.", {"name": {"type": "string"}}),
        ("start_job", "Start a background job.", {"job": {"type": "string"}}),
        ("get_job_status", "Poll a job.", {"job": {"type": "string"}}),
        ("ping", "Health check with a client timestamp.", {"target": {"type": "string"}, "ts": {"type": "number"}}),
    ]
]


class MockEnv:
    def __init__(self, scenario: str, seed: int):
        self.scenario, self.seed = scenario, seed
        self.rng = random.Random(f"{scenario}:{seed}")
        r = self.rng
        # pagination
        self.n_items = r.randint(23, 47)
        self.page = 5
        # fan-out / files
        self.n_files = r.randint(20, 40)
        self.files = {f"src/mod_{i:02d}.py": f"# module {i}\nvalue = {r.randint(0, 999)}\n" for i in range(self.n_files)}
        # fix-loop: k buggy files, each fixed by writing its 'fixed' content
        self.k_bugs = r.randint(2, 4)
        self.bugs = {f"src/mod_{i:02d}.py" for i in range(self.k_bugs)}
        # error-fallback
        self.primary_failures = 10**9   # primary always fails (503)
        # missing path
        self.true_path = f"docs/guide_{r.randint(10, 99)}.md"
        self.files[self.true_path] = "the guide"
        # multi-hop
        self.docs = {f"d{i}": {"title": f"Doc {i}", "author": f"author_{i % 5}"} for i in range(12)}
        self.authors = {f"author_{i}": {"email": f"a{i}@example.org"} for i in range(5)}
        self.target_doc = f"d{r.randint(0, 11)}"
        # polling
        self.jobs: dict[str, int] = {}          # job -> polls so far
        self.job_ready_after = r.randint(4, 9)
        self.edits = 0

    # each tool returns a JSON string
    def execute(self, name: str, args: dict) -> str:
        fn = getattr(self, "t_" + name, None)
        if fn is None:
            return canonical_json({"error": f"unknown tool {name}"})
        try:
            return canonical_json(fn(**args))
        except TypeError as e:
            return canonical_json({"error": f"bad arguments: {e}"})

    def t_list_items(self, cursor=None):
        start = int(cursor) if cursor else 0
        end = min(start + self.page, self.n_items)
        return {"items": [f"item_{i}" for i in range(start, end)], "next_cursor": str(end) if end < self.n_items else None}

    def t_fetch(self, source):
        if source == "primary":
            return {"error": "503 service unavailable"}
        return {"data": "payload from " + source}

    def t_list_dir(self, path):
        if path in ("src", "src/"):
            return {"entries": sorted(p for p in self.files if p.startswith("src/"))}
        if path in ("docs", "docs/"):
            return {"entries": [self.true_path]}
        return {"error": "not found"}

    def t_read_file(self, path):
        if path not in self.files:
            return {"error": "file not found: " + path}
        return {"content": self.files[path]}

    def t_edit_file(self, path, content):
        if path not in self.files:
            return {"error": "file not found: " + path}
        self.files[path] = content
        self.bugs.discard(path)
        self.edits += 1
        return {"ok": True}

    def t_run_tests(self):
        failing = sorted(self.bugs)
        return {"passed": not failing, "failing": failing[:1]}   # reports first failure only

    def t_search(self, query):
        return {"hits": [self.target_doc]}

    def t_get_doc(self, id):
        d = self.docs.get(id)
        return d if d else {"error": "no such doc"}

    def t_get_author(self, name):
        return self.authors.get(name, {"error": "no such author"})

    def t_start_job(self, job):
        self.jobs.setdefault(job, 0)
        return {"started": job}

    def t_get_job_status(self, job):
        self.jobs[job] = self.jobs.get(job, 0) + 1
        n = self.jobs[job]
        return {"job": job, "status": "done" if n >= self.job_ready_after else "running",
                "progress": min(100, n * 100 // self.job_ready_after)}

    def t_ping(self, target, ts):
        return {"target": target, "alive": True}   # state-free: result independent of ts
