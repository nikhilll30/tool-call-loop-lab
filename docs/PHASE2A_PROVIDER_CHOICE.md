# Phase 2A provider choice (DeepInfra excluded: persistent HTTP 429)

> **Point-in-time snapshot, not current data.** Every provider price, uptime, status, availability and endpoint-capability figure in this document was read from OpenRouter or provider pages on **2026-09-29/30 (and 2026-10-01 for the amendment)**. It is **third-party data, very likely stale**, and is kept only to document why the exploratory runs were configured the way they were. Do not use it to choose a provider or to estimate current cost. Sources that were saved privately (raw endpoint JSON, saved web pages, the chat template) are **not published**; where this document refers to them it only describes what they showed.

Snapshot: the OpenRouter endpoints listing for `openai/gpt-oss-20b` (`GET https://openrouter.ai/api/v1/models/openai/gpt-oss-20b/endpoints`, a free unauthenticated metadata call), taken 2026-09-29 ~20:30 ET. The raw JSON is not published.
Filters: excludes DeepInfra; needs `tools` AND `tool_choice` in supported_parameters (streaming is universal on OpenRouter); status 0 (OK); uptime.

| provider (tag) | quant | max completion | in $/M | out $/M | uptime 30m / 1d | tools + tool_choice | note |
|---|---|---|---|---|---|---|---|
| **Darkbloom** (darkbloom/fp8) | fp8 | 32768 | **0.018** | **0.09** | 99.5 / 99.85 | yes / yes | **cheapest suitable -> CHOSEN** |
| AkashML (akashml/fp4) | fp4 | 117964 | 0.020 | 0.10 | 99.4 / 99.4 | yes / yes | **runner-up (report only, NOT used automatically)** |
| DekaLLM (dekallm/bf16) | bf16 | 117964 | 0.029 | 0.14 | 98.3 / 98.8 | yes / yes | |
| CoreWeave (coreweave/fp4) | fp4 | 117964 | 0.030 | 0.13 | 100 / 99.996 | yes / yes | best uptime; listed for information |
| Parasail (parasail/fp4) | fp4 | 117964 | 0.030 | 0.15 | 99.9 / 99.9 | yes / yes | |
| Novita, SiliconFlow, Google | | | | | | **no tools** | excluded |
| Amazon Bedrock, Groq | | | 0.07-0.075 | 0.15-0.30 | | yes | dearer; Bedrock and Groq are on OpenRouter's "stream cancel not supported" list |

Decision: **Darkbloom** - cheapest endpoint (0.018/0.09 $/M) that supports tools + tool_choice, status OK, uptime 99.5% (30 m) / 99.85% (1 d), which is not poor, 131k context, 32768 max completion tokens (our per-request cap is 4000, so no conflict), fp8 quantization (differs from DeepInfra bf16 - results are provider- and quantization-specific).
Caveats noted honestly: Darkbloom is not on OpenRouter's documented "stream-cancel supported" list (neither are most small providers; the list is short and out of date - DeepInfra is on it). Whether cancel stops billing is exactly what the early-disconnect test measures, and it will be reported as Darkbloom's behavior. Its parallel-tool-call behaviour is unverified (`parallel_tool_calls` is not in its supported_parameters list, same for the others).
Runner-up for the report only: **AkashML**. No automatic failover: the request pins `{"order":["Darkbloom"],"allow_fallbacks":false}`; any response/chunk/`/generation` naming another provider STOPS the run. Any further provider change would have needed the maintainer's decision.

Guard prices: pre-charge uses in $0.02/M, out $0.10/M (rounded UP from 0.018/0.09) with the existing 1.25x margin and 300-token template allowance; max_tokens fully priced as output (reasoning included). The 3x-cost anomaly check uses these prices.
