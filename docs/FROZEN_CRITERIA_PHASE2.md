# Phase 2 success / failure criteria - pre-registered (Phase 1.5). Not to be edited after Phase 2 data arrives.

Phase 2 = small live trace collection with `openai/gpt-oss-20b` pinned to DeepInfra (Stage 1), offline analysis of those traces with the FROZEN
detector/guard config (Stage 2 re-check, no retuning), and, only if separately approved, the Stage-4 A/B. Requires explicit user approval and
an OpenRouter key placed by the user; every experiment expected to exceed $1 needs approval; hard budget target <= $10, max $15.
Nothing in Phase 1 / 1.5 made any live call.

## Definitions (detector-independent, fixed now)
* **Flood-qualifying run**: an unguarded run (guard off, only the cost-control run cap of 120 tool calls and the harness turn/token caps) that
  contains >= 30 tool calls AND a distinct-signature ratio <= 0.35 over its calls (signature = tool name + canonical args after dropping
  the frozen volatile-field list), AND is confirmed by a human reading of the trace excerpt (agent repeated without new information).
  The definition does not use the frozen detectors' flags.
* **Legitimate run**: any run that reaches a natural end (final answer) and is not flood-qualifying.
* **Interruption**: the frozen policy would (offline replay) or did (online) cancel a run before it completed. Uses the same definitions
  as `docs/PRIMARY_METRICS.md`.

## Criteria
| id | criterion | pass | fail |
|---|---|---|---|
| P2-A plumbing | >= 95% of runs produce valid traces with full provenance; harness spend ledger within 20% of provider-reported cost; the real streamed delta shape (whole vs fragments, usage chunk placement) recorded and `sse.py` handles it without code changes to detector logic | all hold | any fails -> fix plumbing only, report; no detector changes |
| P2-B elicitation | in N >= 100 unguarded runs (>= 3 scenarios, >= 3 modes incl. history-primed), >= 5 flood-qualifying runs | >= 5 | < 5 = **NULL RESULT** (below) |
| P2-C legit safety (the pre-frozen FP threshold) | on real legitimate runs (need >= 60), frozen policy legit interruption UB (Clopper-Pearson 95%) <= 5.0% | UB <= 5% | UB > 5% = guard FAILS its FP threshold on real data; reported as a failure |
| P2-D detection on real floods (only interpretable if P2-B passes) | frozen policy intervenes on >= 80% of flood-qualifying runs (report count and CI; with 5-10 floods the CI is wide and no rate claim is made) and median calls-after-loop-start <= 40 | both | reported as-is; failure is a result |
| P2-E A/B (only if separately approved and P2-B passed) | paired by scenario/seed: guard-on tool calls executed after loop start reduced >= 50% vs guard-off, with no increase in legit-run failure rate | both | reported as-is |

## What a null result means
If gpt-oss-20b (or any pinned model) never produces flood-qualifying runs within the pre-registered budget/N, the outcome is **"no flood was elicited
under these conditions"** (report model, provider, scenarios, modes, N, caps). It is NOT evidence that the model cannot flood, that floods are rare in
the world, or that the guard works. The guard A/B is then **not interpretable for flood reduction**; P2-C (FP / interruption on legitimate runs), latency
overhead of the proxy, and plumbing findings (P2-A) are still reportable. No real-world rate claims are made in any case, and no new model
is tried beyond the budget without a new approval. A permitted fallback, only with approval: history-primed MiMo probe, or replay of recorded/mock floods
(which validates mechanics, not ecological validity).

## No optimization against Phase 2
The detector/guard configuration frozen in `configs/frozen/` (hash recorded in PHASE1_5_REPORT.md and MANIFEST.json) will **NOT** be modified,
tuned or re-selected after Phase 2 results arrive. Phase 2 results are reported against that config even if poor. Any improvement is a new
version with a NEW pre-registration and a NEW held-out split, and cannot be presented as validating the frozen version.
If no policy qualifies in Phase 1.5, nothing is frozen and Phase 2 (guard parts) does not proceed without a new user decision; Phase 2 trace
collection (Stage 1, unguarded, with cost-control stop) may still be proposed separately.
