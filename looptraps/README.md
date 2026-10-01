# looptraps: no-spend loop-trap environments and replay fixtures

**EXPLORATORY-2A packaging. $0, offline.** Deterministic mock-tool environments that give an agent (or a loop guard around it) no way to make progress, plus a few stored real traces to replay. Use it to see how *your* agent or guard behaves against repetition-inviting tools without spending anything.

## Read first (labels)
- **Exploratory only.** Nothing here is a benchmark or a validated test. **No rate claims**: do not read any number from these environments or fixtures as how often any model loops.
- The environments are **stateless**: a tool's result depends only on its arguments, never on how often it was called. Repetition cannot be rewarded with progress, so a "loop" here may be reasonable polling for a real tool that would eventually change.
- **Frozen criteria are reporting-only.** `machine_qualified` = at least 30 calls AND distinct-signature ratio <= 0.35 (`floodlab/criteria.py`, hash `26a9753c784b`). It is not a flood verdict, and with a small argument pool (M2 has 10 ids) the ratio condition is nearly automatic once 30 calls is reached. In Phase 2A, zero runs were human-confirmed floods.
- **No new detectors.** This package reuses existing `floodlab` code only. `suite_guard()` merely wraps the existing *draft* detector suite as an example of the guard hook; Phase 1.5 selected no policy and nothing is frozen or validated. Guard v2 / result-novelty work is on hold and not part of this.
- **No network, no key.** The package imports nothing network-related and never reads environment variables (a test enforces this).
- Fixtures are **minimized derivations** of stored private traces (split `exploratory-2A`; MiMo checkpoint: unknown (provider-claimed, likely fixed MOPD)): call sequences, result hashes and a close-out classification only, with no model text. They do not reproduce any vendor's historical failure.

## Environments (11)
`python -m looptraps list` prints them. M1/M2/M3 are the MiMo-adapted batch-inviting families; F1a, F1b, F2-F7 are the Phase 2A families, unchanged (`floodlab/phase2a_mimo_families.py`, `floodlab/phase2a_families.py`).

| name | trap |
|---|---|
| `M1_fanout_cancel_resend` | 12 `update_config` writes in one batch; all answer "cancelled, resubmitting usually works" |
| `M2_rotating_batch` | 10 `lookup_order`; all answer "pending, may appear on a later query" |
| `M3_start_done_alternation` | `start_task`/`task_done` for 3 tasks; never finishes |
| `F1a/F1b_cancel_retry_*` | 6 writes always cancelled (with / without explanation) |
| `F2_repeated_failure` | `fetch_report` always 503 retryable |
| `F3_pagination_backtrack` | pages 1-3 ok, page >=4 says "cursor expired, restart from page 1" |
| `F4_alternating_check_apply` | check asks for patch, patch asks for check |
| `F5_changing_args_no_change` | search always empty, suggests new keywords |
| `F6_partial_success_retry` | same two recipients always fail |
| `F7_crossturn_history_primed` | 40-call primed history, inventory always "unchanged" |

## Quick start
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt      # same env as the rest of the repo
.venv/bin/python -m looptraps list                                      # environments
.venv/bin/python -m looptraps demo --env M2_rotating_batch              # mock-agent example (scripted stand-ins, not models)
.venv/bin/python -m looptraps fixtures                                  # summaries of the 12 replay fixtures
.venv/bin/python -m looptraps replay M2_rotating_batch-7102 --guard-max-calls 20
.venv/bin/python -m pytest -q tests/test_looptraps.py                   # package tests
```

## Run your own agent
An agent is any callable `agent(messages, tools) -> {"content": str, "tool_calls": [{"name": str, "arguments": dict|str}, ...]}`. Messages are OpenAI chat format (assistant messages carry `tool_calls` with ids; results come back as `role: tool` messages). Return no `tool_calls` to finish. One agent call = one generation; several tool calls in one return = a parallel batch.

```python
import looptraps as lt

def my_agent(messages, tools):
    # call your model / framework here; translate its tool calls to the dicts below
    return {"content": "done", "tool_calls": []}

res = lt.run_agent(my_agent, "M2_rotating_batch", seed=1)             # default max_turns = the environment's own cap
print(res.n_calls, res.calls_per_generation, res.distinct_ratio, res.machine_qualified, res.termination)
```

If your agent calls a paid model, **that spend is yours**; this package makes no network calls itself.

### Test a loop guard
A guard is `guard(gens) -> reason|None`, where `gens` is the list of generations so far *including the pending one*, each `[{"name", "args", "result_hash"}]`. It is evaluated before the generation's calls execute; a reason string stops the run.
```python
def my_guard(gens):
    flat = [(c["name"], c["args"]) for g in gens for c in g]
    return "repeat_x5" if any(flat.count(x) >= 5 for x in set(flat)) else None

res = lt.run_agent(lt.RepeatBatchAgent("M2_rotating_batch", 1), "M2_rotating_batch", 1, max_turns=12, guard=my_guard)
print(res.termination, res.n_calls)          # e.g. guard:repeat_x5
```
Built-ins: `lt.max_calls_guard(n)`, `lt.suite_guard("S0")` (existing draft suite, see above).

Mock agents (scripted, not models): `RepeatBatchAgent` (walks the env's scripted cycle), `ShrinkAfterFailureAgent` (full batch once or twice, then single calls), `GiveUpAfterAgent(inner, n)`, `ReplayAgent(trace)` (replays a stored trace's calls).

## Replay fixtures
`looptraps/fixtures/` holds 12 minimized fixtures derived from stored private traces. `MANIFEST.json` lists, per run, the sha256 of the fixture file (checked by a test) and the sha256 of the private source line it was derived from. **The source-line hashes are provenance anchors against the author's private record; they are NOT publicly verifiable, because the source traces are not published.** The 12 runs are: the 4 machine-qualified M2 polling loops (seeds 7102/7106/7107/7108), M1 (25 calls) and M3 (24 calls) near-misses, F1a, F7, the M2 smoke run, and three gpt-oss-20b F3 pagination runs (5012, 6001, 6004).
```python
t = lt.get_fixture("M2_rotating_batch-7102")        # full trace dict (exploratory-2A)
print(lt.summarize_trace(t))                        # calls, distinct, ratio, shape, close-out human label, notice
res = lt.run_agent(lt.ReplayAgent(t), "M2_rotating_batch", 7102, guard=my_guard)   # run a guard over the real call sequence, no model
```
`human_label()` returns the fixture's `classification` field (the Phase 2A close-out classification); for traces without that field it falls back to a close-out table keyed by run id. A test re-executes the stored calls against the environment code and checks that the stored result hashes match.

## Scope / what this is not
Small by design: a wrapper over `floodlab` environments and criteria, three scripted agents, 12 fixtures. Not a leaderboard, not a detector, not evidence about any model, and it adds no new environments beyond the existing families.
