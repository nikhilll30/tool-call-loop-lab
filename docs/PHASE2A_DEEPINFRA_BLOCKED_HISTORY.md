## 8. DeepInfra blocked history (kept; DeepInfra data is NOT part of the Darkbloom results below/above)

### 8a. Attempt 1 (bounded 3 attempts, 2026-09-29 ~19:0x ET)
Disconnect test request rate-limited (HTTP 429, "openai/gpt-oss-20b is temporarily rate-limited upstream") on all 3 attempts (waits 21.65, 50.35, 63.79 s); pre-charges released, $0 spent; stopped by rule.

### 8b. Attempt 2 (8 attempts over ~23.5 min, 2026-09-29 19:18:59-19:42:27 ET)

- Run window: 2026-09-29 19:18:59 - 19:42:27 EDT (ET). The disconnect test's first request was rate-limited (HTTP 429, "openai/gpt-oss-20b is temporarily rate-limited upstream") on **all 8 attempts** over ~23.5 minutes (backoff waits 33, 62, 161, 284, 271, 350, 240 s before the stop; total waiting 1689 s incl. the last computed wait not slept). Every 429's pre-charge was released ($0). The runner then stopped by rule ("still rate-limited after 8 attempts"); the pilot (Step 3) never started.
- Provider stayed pinned to DeepInfra (`allow_fallbacks:false`); no BYOK, no model/provider change; no request other than the 8 rate-limited ones was sent.
- Real spend this run: **$0.000000**. Cumulative: **$0.001419** (ledger) = key usage counter **$0.00141902** (re-read after the stop): reconciled. Hard cap $1.00 / effective $0.90 untouched. No anomalies other than the sustained 429 (no auth error, provider mismatch, cost or billing issue).
- Therefore: no disconnect-test numbers, no pilot runs, no per-family results, no flood-qualifying runs, no /generation reconciliation for this continuation. Sections 2-4 are empty for that reason. The "escalation" line in section 5 now correctly says "no evidence collected; escalation question undecidable".
- Cumulative history of this rate limiting for this key/model: 429 at first connectivity retry (~10 min window) -> cleared once (Phase 2A first live run, 7 requests + 30 more succeeded, then 429 mid-elicitation) -> 429 for ~2.3 min (attempt 1 of this continuation) -> 429 for ~23.5 min (this attempt). The limit is upstream/provider-side (message suggests "add your own key to accumulate your rate limits", which is BYOK and is NOT permitted under the approved terms).

### 8c. Consequence
The maintainer approved a DIFFERENT provider for the same model (see docs/PHASE2A_PROVIDER_CHOICE.md). Cumulative spend before the Darkbloom continuation: $0.001419 (all DeepInfra, first collection in the Phase 2A consolidated report (not published)).
