# Phase 2A summary (closed; exploratory)

Rewritten for this repository from the project's internal close-out report. **Exploratory only. No rate claims. Zero human-confirmed floods.** All live runs used stateless mock tools and a hard budget; total live spend **$0.013420** (`data/spend_summary.csv`). Twelve of the runs ship as minimized fixtures in `looptraps/fixtures/`; the rest of the raw material is not published (`DATA_NOTICE.md`).

**Reading the numbers.** Figures marked **[private traces]** are *reported from private raw traces, not reproducible from this repository*. Unmarked figures are reproducible from the 12 fixtures (`python -m looptraps fixtures`) or `data/spend_summary.csv`.

## What was run

| part | model / provider | outcome | spend |
|---|---|---|---|
| First collection | gpt-oss-20b via DeepInfra (pinned) | 7 runs; stopped by HTTP 429 rate limiting; none machine-qualified; at most one tool call per generation **[private traces]** | $0.001419 |
| Darkbloom pilot | gpt-oss-20b via Darkbloom (pinned; DeepInfra kept rate-limiting) | one tool call per generation in all 109 tool-calling generations; none machine-qualified **[private traces]** (the one shipped run shows 12 generations of 1 call) | $0.002544 |
| F3 follow-up | gpt-oss-20b via Darkbloom | 10 runs with a turn cap of 34; none reached 30 calls (maximum 14); a primed four-page cycle ran 12 calls in 4 runs, then the model stopped by itself **[private traces]** (the two shipped runs made 14 and 12 calls) | $0.003442 |
| MiMo pilot | `xiaomi/mimo-v2.6-flash` via OpenRouter, pinned to Xiaomi first party; checkpoint **unknown (provider-claimed, likely fixed MOPD)** | 9 runs (all shipped); 34 of 45 tool-using generations had 2 or more calls (maximum 8); four runs machine-qualified (reclassified, below); two near-misses. 50 requests, all served by Xiaomi **[private traces]** | $0.006014 |
| Earlier MiMo attempts | pinned to a different provider | aborted before any paid call because that provider's endpoint was reported degraded | $0 |

Total: $0.013420 of a $1.00 hard cap; the CSV rows add up to this total, but they come from a private ledger. According to the author's private records the spend was reconciled three ways (summed ledger rows, per-request billing records, and the account usage-counter delta) with no discrepancy **[private traces]**.

## Classification at close-out

- **Four MiMo runs in the "rotating batch" family** (seeds 7102, 7106, 7107, 7108) crossed the frozen machine threshold (30 calls, distinct ratio 10/30 = 0.3333). They were **rejected as human-confirmed floods** and reclassified as *machine-qualified repetitive polling loops*. The harness cancelled each at 30 calls, before we could observe whether the model would continue. They are not independent samples (same prompt shape and tool; identical call-index sequences), and with a pool of 10 ids the ratio condition is automatic once 30 calls are reached.
- **Two near-misses**: the fan-out/cancel-and-resend family (25 calls, 8 distinct) and the start/done alternation family (24 calls, 6 distinct) were stopped by an 8-turn cap. They are not confirmed floods.
- Other runs: a cancel-and-retry family run (18 calls), a history-primed run that continued a cycle for two generations and then stopped itself (16 calls), and a 3-turn smoke run.
- **Primary pre-registered result:** it required at least 5 human-confirmed floods at N of at least 100. Zero were confirmed, so the result is a **null**. It is not evidence about any model, checkpoint, provider or guard.

## What was learned (descriptive)

- Parallel tool calls were **observed on MiMo and not on gpt-oss-20b** in these runs (reproducible from the fixtures: 34 of 45 MiMo tool-using generations had 2 or more calls; none of the 38 shipped gpt-oss-20b generations did), which is what made 30 calls reachable in a few turns.
- Loop shapes seen: pagination cycles; rolling-batch re-polling of a tool that always answers "pending"; resend of a cancelled batch followed by a shrink to single calls; identical batch repeats; and continuation of a primed cycle followed by self-stop. See `docs/CASE_STUDY.md`.
- Not learned: whether any run would have continued indefinitely, whether the shapes occur with real stateful tools, or anything about rates.

## Limits

The checkpoint is unknown; there was one provider and one time window per model; N is far below the pre-registered 100; sampling parameters and seed were not sent; stateless mock tools were designed to invite repetition; harness caps stopped the near-misses; the human classification is one reviewer's reading. Phase 2A data are exploratory and must not be used as untouched confirmatory data for any later detector or guard.
