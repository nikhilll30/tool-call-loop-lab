# Trace schema `floodlab.trace/1`

One JSON object per line (JSONL). Canonical JSON (sorted keys, no spaces). Builders/validator: `floodlab/trace.py`.

Terminology: **generation** = one model response (one streamed completion). **turn** = one assistant response in the
agent loop plus the tool results that follow. In Phase 1 every turn has exactly one generation; the schema keeps a
`generations` list so retries/regenerations within a turn can be represented without a schema change.

```jsonc
{
  "schema_version": "floodlab.trace/1",
  "run_id": "flood-rot35-1g-100",
  "synthetic": true,                 // true for generated traces AND for mock-upstream runs
  "label": "flood" | "legitimate" | "unknown",   // ground truth (synthetic sets) / unknown for harness runs
  "shape": "rotating35_one_gen",     // generator family ("" for harness runs)
  "split": "dev" | "test" | "none",  // dev seeds 0-9, test seeds 100-109, none = hand-written / harness
  "provenance": {                    // REQUIRED on every record
    "model": "...", "endpoint": "...", "scenario": "fan_out/rotating_argument", "seed": 3,
    "detector_config": {"id": "draft-0.1", "hash": "b1baa129b8d2"},   // or {id:null, hash:null}
    "guard_config": "off" | {"id": "...", "hash": "..."},
    "prompt_version": "prompts-v1", "tool_schema_version": "tools-v1"
  },
  "turns": [
    {
      "turn": 0,
      "messages": [                  // per-turn messages (assistant summary + tool result hashes)
        {"role": "assistant", "content": "", "reasoning_content": "...", "n_tool_calls": 12},
        {"role": "tool", "tool_call_id": "call_..", "result_hash": "16hex"}
      ],
      "generations": [
        {
          "gen": 0, "t_start": 0.0, "t_end": 0.0,        // seconds (epoch for live/mock runs, simulated clock for generators)
          "finish_reason": "tool_calls|stop|length|cancelled|cancelled_by_stop_hook|...",
          "cancelled": false, "content": "", "reasoning_content": "",
          "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
          "stop": {"reason": "...", "detector": "...", "evidence": {}},   // present iff a stop hook cancelled the stream
          "floodlab_guard": {"stopped": true, "reason": "...", ...},     // present iff the guard proxy stopped it
          "tool_calls": [
            {"index": 0, "name": "read_file",
             "arguments": "{\"path\":\"a.py\"}",       // CANONICAL JSON string (sorted keys); raw string if unparseable
             "timestamp": 1700000000.0,                // emission (stream-complete) time of this call
             "result_hash": "16hex"}                   // sha256[:16] of the tool result; absent if not executed
          ]
        }
      ]
    }
  ],
  "latency_s": 12.3,
  "cost_usd": 0.0,                   // 0.0 in Phase 1; live runs fill from usage x price (or provider-reported cost)
  "termination_reason": "completed|max_turns|call_cap|token_cap|budget_guard|http_<code>|stopped_by_hook:<r>|guard_stop:<r>|synthetic",
  "notes": "free text; synthetic traces always say SYNTHETIC"
}
```

Cross-turn structure is preserved: detectors read `generations()` (list of generations, each a list of `Call`) and the
flattened emission order with a global call index (`gidx`) which is the index reported as "first index at which a detector fires".

`result_hash` is the ground for the state-aware detector: a repeated call whose result hash changes is evidence
that external state legitimately changed.
