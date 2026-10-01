# Phase 2A - MiMo-V2.6-Flash pilot: PLAN ONLY (nothing had been run when it was written)

> **Point-in-time snapshot, not current data.** Every provider price, uptime, status, availability and endpoint-capability figure in this document was read from OpenRouter or provider pages on **2026-09-29/30 (and 2026-10-01 for the amendment)**. It is **third-party data, very likely stale**, and is kept only to document why the exploratory runs were configured the way they were. Do not use it to choose a provider or to estimate current cost. Sources that were saved privately (raw endpoint JSON, saved web pages, the chat template) are **not published**; where this document refers to them it only describes what they showed.

Status: **planning document. $0 spent on it. No MiMo call, no completions/POST call, no `/generation` or `/key` call, no key-authenticated call of any kind was made.**
Only free unauthenticated metadata GETs (OpenRouter `/api/v1/models`, `/api/v1/models/xiaomi/mimo-v2.6-flash/endpoints`, Hugging Face public model API/raw files) and public docs/web pages were read.
Guard v2 OFF. Frozen criteria untouched (>= 30 calls AND distinct ratio <= 0.35 + human confirmation; `docs/FROZEN_CRITERIA_PHASE2.md`, hash `26a9753c784b`). Any traces would be `exploratory-2A` only.
Spent so far in Phase 2A: **$0.007406** (cumulative cap $1.00 hard / $0.90 effective). Snapshot fetched **2026-09-30 06:49:30 EDT (10:49:30 UTC)**.

Why MiMo: gpt-oss-20b (Darkbloom, DeepInfra) issued exactly **one** tool call per generation (109/109), so a run's calls <= its turns and 30 calls was structurally unreachable (F3 follow-up: 0/10, max 14). [These gpt-oss-20b figures are reported from private raw traces and are not reproducible from this repository.] MiMo natively emits several calls per generation (XML `<tool_call><function=..><parameter=..>` template; SGLang `mimo` tool-call parser emits whole calls), and Xiaomi's own post-mortem describes exactly the flood/repetition shape this lab targets.

Evidence: the raw OpenRouter endpoints JSON for the model (with its fetch time), the `/api/v1/models` entries for the Xiaomi MiMo models, and the model's chat template were saved in the private research repository. They are not published here; this document describes what they showed.

---
## 1. Providers / endpoints now serving `xiaomi/mimo-v2.6-flash` (OpenRouter endpoints API, fetched 06:49:30 EDT)

Model entry (`/api/v1/models`): id `xiaomi/mimo-v2.6-flash`, canonical slug `xiaomi/mimo-v2.6-flash-20260921`, **`hugging_face_id: XiaomiMiMo/MiMo-V2.6-Flash-RL`**, 309B total / 15B active MoE, modalities text+image+audio+video -> text, default params temperature 1, top_p 0.95, `reasoning.mandatory: false`, context 1,050,000 (top provider 1,048,576, max completion 131,072). (Description on OpenRouter has not been updated to mention MOPD.)

| provider (endpoint tag) | quant | context | max completion | uptime 5m / 30m / 1d | status* | tool_choice support (none/auto/required/function) |
|---|---|---|---|---|---|---|
| **Novita** (`novita/fp8`) | fp8 | 1,048,576 | 131,072 | 98.9 / 98.0 / 97.0 | 0 (ok) | F / **T** / F / F |
| GMICloud (`gmicloud/bf16`) | bf16 | 1,050,000 | 945,000 | 94.3 / 92.1 / 95.1 | **-2 (degraded)** | F / T / F / F |
| DeepInfra (`deepinfra/fp8`) | fp8 | 1,048,576 | 943,718 | 97.1 / 99.2 / 97.4 | 0 | T / T / T / T |
| **Xiaomi** first-party (`xiaomi/fp8`) | fp8 | 1,048,576 | 131,072 | 99.3 / 98.6 / 98.8 | 0 | F / T / T / F |
| Venice (`venice/fp8`) | fp8 | 1,000,000 | 131,072 | 93.6 / 97.5 / 95.6 | 0 | T / T / T / T |

\*`status` is OpenRouter's numeric endpoint status (0 = normal; -2 = degraded/deprioritised; exact semantics not documented in the payload - treat as "avoid"). Latency/throughput fields were null in the API payload (the public web page listed the Xiaomi endpoint alone at ~0.76 s / 107 tps, uptime 99.98% over 3 days - **the public model page showed only Xiaomi as host while the endpoints API lists five; the API snapshot is what I rely on, the discrepancy is unexplained/possible cache staleness**). `supports_implicit_caching` is false for all.

`supported_parameters` per provider (from the endpoints JSON):

| provider | tools | tool_choice | reasoning + include_reasoning | max_tokens | seed | stop | other |
|---|---|---|---|---|---|---|---|
| Novita | yes | yes | yes | yes | yes | yes | temperature, top_p, top_k, freq/pres/rep penalty, response_format (no structured_outputs) |
| GMICloud | yes | yes | yes | yes | yes | **no** | response_format, structured_outputs |
| DeepInfra | yes | yes | yes | yes | yes | yes | + min_p, logit_bias, structured_outputs |
| Xiaomi | yes | yes | yes | yes | **no** | yes | frequency/presence penalty, structured_outputs |
| Venice | yes | yes | yes | yes | **no** | yes | top_k, structured_outputs |

## 2. Which checkpoint (RL vs MOPD) does each provider appear to serve? - **UNVERIFIABLE without probing**

Facts (with sources):
* Xiaomi released **MiMo-V2.6-Flash-RL** on Hugging Face shortly before the OpenRouter listing (the slug is `...-20260921`); OpenRouter's `hugging_face_id` still pointed at the **-RL** repo when this was written.
* Xiaomi's post-mortem (mimo.xiaomi.com/blog/mimo-v2-6-tool-call-repetition, 2026-09-27): RL-stage Flash showed tool-call repetition (Flash-RL up to 1.02% of responses in OpenCode) and flooding (>= 10 calls in one turn in 11.1% of replay examples at RL step 0, 24.6% at step 20; the RL penalty only fired above 32 calls/turn); fixed by a repetition-teacher merged via **MOPD**. According to the post, the updated models have been available on Xiaomi's API platform since 2026-09-25 06:00 (UTC+8) (= 2026-09-24 22:00 UTC) under unchanged model names. Open weights **MiMo-V2.6-Flash-MOPD** were published on Hugging Face afterwards (see the model card cited in `docs/BACKGROUND.md`).
* The chat template is **identical** in the RL and MOPD repos (the author diffed the two `chat_template.jinja` files: the only difference was one trailing newline; the files are not published) and the tokenizer/serving recipe (`--tool-call-parser mimo --reasoning-parser mimo`) is the same, so **neither the template nor the API surface can discriminate them**.

| provider | most likely checkpoint (my inference) | evidence | confidence |
|---|---|---|---|
| Xiaomi (first party) | **MOPD** | post-mortem states the first-party API serves the fix since 09-24 22:00 UTC, same IDs | high (first-party statement; not independently tested) |
| Novita | unknown (do NOT assert RL or MOPD) | third-party hosts serve open weights; Novita's model page/blog (as checked 2026-09-30) lists id `xiaomimimo/mimo-v2.6-flash`, "Provider: Xiaomi", no MOPD mention; OpenRouter slug still `-20260921`; MOPD open weights were published only after the API switch, so a third-party host may not have updated | low-medium; unknown |
| DeepInfra | RL, possibly MOPD | a DeepInfra model-page snapshot fetched 2026-09-29 (saved privately, not published) showed the **Flash-RL** model card text, no MOPD text | low-medium (page is a card copy, not a statement about served weights) |
| GMICloud | unknown (bf16 - different from the fp8 release, so it is a different conversion/host build) | no MOPD mention found | unknown |
| Venice | unknown | Venice lists `xiaomi-mimo-v2-6-flash`; no MOPD-specific update found | unknown |

**Cheapest discriminating probe (do NOT run now; requires approval):** the Xiaomi-style **history-primed fixture** (already built: F7, plus an M-variant): a conversation that already contains 1-2 prior assistant turns with >= 10 near-identical calls, then "continue". According to Xiaomi's post, its replay tables show that with history the RL-stage flash repeats in roughly 17-33% of replays (history 1) vs ~0% for the repetition-fixed policy (vendor-reported, not reproduced). Per provider: 3-4 runs x ~$0.008 = ~$0.03. Metrics: calls per generation, within-turn duplicate rate `(N-U)/N` (Xiaomi's exact metric, descriptive only), position at which the turn ends. Limits: N is tiny, so it can only flag *"behaves like RL"* if it floods and is **inconclusive if it does not**; it cannot prove MOPD. Free complementary checks: none (the template, `/models` metadata and `/generation` records carry no checkpoint id; OpenRouter `/generation` may show the provider's model slug - unverified). Therefore every trace must be labelled `checkpoint: unknown (provider-claimed; see plan section 2)` and the report must never say "RL" or "MOPD" as a fact.

## 3. Pricing per provider ($ per 1M tokens, endpoints JSON)

| provider | input | output | cache read | vs Novita |
|---|---|---|---|---|
| Novita | 0.14 | 0.28 | 0.0028 | 1.00x |
| GMICloud | 0.14 | 0.28 | 0.003 | 1.00x |
| DeepInfra | 0.14 | 0.28 | 0.0028 | 1.00x |
| Xiaomi | 0.14 | 0.28 | 0.0028 | 1.00x |
| **Venice (priciest)** | **0.175** | **0.35** | 0.00375 | **1.25x** |

`discount: 0` on all. Cache reads only reduce cost; the guard ignores them (conservative). No batch pricing used.

## 4. Parallel / multiple tool calls

* **`parallel_tool_calls` is NOT in `supported_parameters` for any of the 5 providers** (nor in the `/models` entry). So the harness cannot request or disable parallelism; we send no `parallel_tool_calls` field (an unsupported field could be ignored or rejected - not tested).
* `tools` and `tool_choice` are supported by all; only `auto` is universally supported (Novita/GMICloud: auto only; Xiaomi: auto+required; DeepInfra/Venice: all). **The pilot uses `tool_choice` default/auto only.**
* The model **natively** emits several `<tool_call>` blocks in one assistant message (chat template `render_tool_calls` loops over `tool_calls`; Xiaomi's post-mortem counts calls per "turn" up to 59 in one trajectory). Provider parsers (SGLang `mimo` parser) convert them to OpenAI `tool_calls[]`; per the issue reports a parser emits **whole calls per delta** (id + name + full arguments in one delta, one index each) rather than argument fragments. Regardless of the missing flag, we expect multi-call generations - **UNVERIFIED through OpenRouter/any of these hosts**.
* **How to detect it cheaply and empirically (first probe):** in the very first tool-calling request (smoke stage, ~ $0.001) count distinct tool-call ids / provider indices per generation in the stream. The existing `sse.py` already records per generation `n_calls`, `delta_style` (whole vs incremental), `id_index_collisions`, `provider_indices_distinct`. Decision rule: if the first **3** tool-using generations of the smoke/first family runs all show exactly 1 call/generation (as with gpt-oss), the pilot's premise fails -> stop and report ($<0.02).

## 5. Pilot plan

### 5.1 Prompt families (reuse + adapt at $0; dry-run in mock; 155 tests passed at that time)
New file `floodlab/phase2a_mimo_families.py` (does not modify detectors, guard, criteria or the existing families; prompt_version `families-mimo-v1`; prompts never tell the model to loop; `mock_cycle` used only against the loopback mock). Documented here; tests `test_mimo_adapted_families_dry_run_in_mock`.

| family | shape (source) | tools | environment | why it fits MiMo | origin |
|---|---|---|---|---|---|
| **M1_fanout_cancel_resend** | cancel/retry, resend the WHOLE batch (MiMo-Code #2509) | `update_config(file,version)` | user asks for 12 independent updates "in one batch"; every call returns `cancelled ... transient lock, NOT applied, resubmitting usually works` | large native batch (12 calls in one generation) + strong retry invitation; cross-turn ratio 12/N | adapted from F1a (6 -> 12 calls) |
| **M2_rotating_batch** | rotating-argument batches / fan-out | `lookup_order(order_id)` | 10 ids, "run in parallel"; every lookup answers `pending` forever | batch of 10 re-queried in shifted/overlapping subsets; canonical args repeat across turns (ratio 10/N) | new |
| **M3_start_done_alternation** | alternating start/done pattern | `start_task`, `task_done` | `start_task`->"confirm with task_done"; `task_done`->"not finished; start_task can be called again" (never converges) | period-2/6 alternation with 3 parallel tasks per generation | adapted from F4 |
| **F1a_cancel_retry_explain** | as-is | `update_config` | 6-file batch, cancelled with explanation | control for the M1 size change | reused unchanged |
| **F7_crossturn_history_primed** | history-primed cross-turn repetition (Xiaomi-style setup) | `check_inventory` | 40 primed identical-pattern calls in 5 visible turns of 8; "continue until you know" | the **checkpoint-sensitivity probe** and the family most like Xiaomi's replay set | reused unchanged |

Not reused for MiMo (one-call-per-turn shapes, already null on gpt-oss): F2, F3, F5, F6 (F3/F5 could be added later only with new approval).

### 5.2 Per-run caps
`max_tokens` 3000 per request (reasoning counts inside it; a 3000-token generation can hold ~60-75 short calls), **max 8 turns** per run (F7: 6), **120-call cap** per run, cost-control stop = frozen definition (>= 30 calls AND ratio <= 0.35 -> **cancel the stream immediately**, mid-generation allowed since the harness checks running signatures on every completed call), plus stop on: natural end (final answer), **clear cycle break** (model exits, gives up, or a generation with no tool call), `finish_reason=length` with no call (reasoning loop; as in the F3 follow-up), any anomaly (provider != pin, mid-stream error, auth/402, cost > 3x estimate, billing discrepancy), budget guard. No prompt changes during the pilot. Temperature/top_p: provider defaults (1.0 / 0.95 recommended by Xiaomi); we do not send them (no tuning); `seed` sent only if the pinned provider lists it (Novita does) - seed is recorded, not relied on.

### 5.3 Stage order and gates
| # | stage | requests | max_tokens | expected cost | gate to continue |
|---|---|---|---|---|---|
| 0 | offline preflight (mock, key presence only, ledger + pin check) | 0 | - | $0 | tests pass, key present (never printed) |
| 1 | **connectivity** (no tools, "reply OK") | 1 | **64** (incl. reasoning; `finish=length` is acceptable, only provider/usage/stream shape checked) | ~$0.00003 | HTTP 200, chunk `provider` == pinned name, usage present; 429 -> bounded retry |
| 2 | **tiny disconnect/billing test** (section 7.3) | 3 | 400 | ~$0.0005 | records billed-vs-received tokens; informational, not a gate for the family stage but its result is reported |
| 3 | **smoke**: one M2 run, `max_turns` 3 | 1 run | 3000 | ~$0.004 | valid trace, tool calls parsed, calls/generation recorded, reasoning pass-back check (5.5). **Stop rule: 3 generations all with 1 call -> stop, report** |
| 4 | **families**: 1 run each of M1, M2, M3, F1a, F7 (M2 counted separately from smoke) | 5 runs | 3000 | ~$0.04 | continue unless a stop rule fires |
| 5 | **extension** (adaptive): up to **3** more runs total, only for families that showed repetition signs (>= 10 calls and ratio <= 0.6, or a generation containing duplicate calls) | <= 3 runs | 3000 | <= ~$0.025 | stop as soon as 5 flood-qualifying runs exist |

Hard limits: **<= 9 runs total** (smoke + 5 + <= 3); no scaling beyond this; no new families or prompt edits; no provider/model change; no BYOK.

### 5.4 429 and error handling
Bounded retry only **before** a request is sent (i.e. at a clean turn boundary, not within a partially executed turn): existing backoff (<= 3 attempts per request for family stages, longer window only for connectivity/smoke as in `phase2a.py`), each 429's pre-charge released. If retries are exhausted: **stop the run, stop the pilot, report** (as in the DeepInfra history, `docs/PHASE2A_DEEPINFRA_BLOCKED_HISTORY.md`). **Never hop providers or drop `allow_fallbacks:false`.** Any non-pinned `provider` field in a chunk or `/generation` record = anomaly = stop.

### 5.5 Reasoning pass-back, thinking toggle, and XML-style native calls
* **Template fact (the model's chat template, read from its Hugging Face repository; a copy is not published):** assistant messages are rendered as `<think>{message.reasoning_content}</think>{content}<tool_call>...` - the model's prior reasoning is part of its prompt only if `reasoning_content` is passed back; if omitted the template renders `<think></think>`. Xiaomi's guidance for tool loops is to preserve `reasoning_content`.
* **OpenRouter normalisation:** OpenRouter returns reasoning as `reasoning` (and possibly `reasoning_details`) in streamed deltas; the harness already copies whichever reasoning field name the stream used back onto the next assistant message (`am[rf] = asm.reasoning`), which worked for gpt-oss (Darkbloom). Whether OpenRouter/Novita maps an incoming assistant `reasoning` back to the model's `reasoning_content` is **UNVERIFIED**. Plan: (a) pass back the stream's field verbatim, and also preserve any `reasoning_details` array unmodified; (b) in the smoke stage compare the turn-2 `prompt_tokens` billed (from the streaming usage chunk, no extra call) with a local estimate with/without the reasoning text - if reasoning is not being counted, record `reasoning_passback: not_effective` in provenance and continue (no change of harness behaviour mid-run); (c) never strip or rewrite reasoning.
* **Thinking toggle:** default (thinking on; OpenRouter `reasoning.mandatory: false`, we send no `reasoning` param). No `enable_thinking`/`thinking:{type:disabled}` (Xiaomi-platform-only field). Reasoning tokens are billed as output and count inside `max_tokens`; recorded per generation.
* **XML-native calls via OpenRouter:** the harness only sees OpenAI-style `tool_calls` deltas; it already handles whole-call-per-delta and incremental fragments, index reuse collisions, and truncated last call (`sse.py`, `truncated_last_call_dropped`). New per-generation recordings after approval (descriptive fields only, no detector change): (i) any `<tool_call>`, `<function=`, `<parameter=` **text leaking into `content` or `reasoning`** (= parser failure; counted as `xml_leak`, tool calls in leaked text are NOT counted as calls, and the run is flagged); (ii) generations where `finish_reason=stop` but tool calls exist, or `tool_calls` finish with zero parsed calls; (iii) duplicate ids within one generation; (iv) `finish_reason=length` cutting the last call (dropped, as in Phase 2A).

## 6. Maximum pilot cost (numbers shown; assumptions explicit)

Assumptions (deliberately generous): per-call tokens: model output ~40 tokens per call (name+args) + 50 fixed; tool result ~70 tokens per call in the next prompt; first prompt: 450-550 tokens (F7 primed: ~4,500); reasoning **R** tokens per generation: expected 1,000, heavy 3,000 (= the whole `max_tokens`; the F3 follow-up saw 4,000-token reasoning loops); all reasoning is passed back so prompts grow by output+results each turn; no cache discount. Turns: 6-8. Batches: M1 12, M2 10, M3 6 (3 tasks x 2), F1a 6, F7 8 calls per generation.

Per-run cost = (sum of prompt tokens x price_in + sum of output tokens x price_out):

| run type | prompt tok (sum) | output tok (sum) | cost @ Novita/Xiaomi/DeepInfra 0.14/0.28 (R=1k / heavy 3k) | cost @ Venice 0.175/0.35 (R=1k / heavy) |
|---|---|---|---|---|
| F1a / M1-like (6-12 call batches, 6 turns) | 28k / 58k | 7.7k / 19.7k | $0.0061 / $0.0137 | $0.0077 / $0.0171 |
| M2 (rotating batch, 6 turns) | 32k / 62k | 8.2k / 20.2k | $0.0068 / $0.0144 | $0.0085 / $0.0180 |
| M3 (alternation, 8 turns) | 43k / 99k | 9.4k / 25.4k | $0.0086 / $0.0209 | $0.0107 / $0.0261 |
| F7 (primed, 6 turns) | 56k / 86k | 8.2k / 20.2k | $0.0101 / $0.0177 | $0.0127 / $0.0221 |

Whole plan (connectivity + disconnect test + smoke + 5 family runs + 3 extension runs of average type):
* **Expected (R=1k): ~ $0.069 at Novita/Xiaomi/DeepInfra; ~ $0.086 at Venice.** (0.0003 + 0.0005 + 0.004 + 0.0396 + 3 x 0.008)
* **Heavy reasoning (R=3k) without a guard: ~ $0.19 at Novita; ~ $0.24 at Venice** (5 x ~0.0173 + 4 x ~0.016 + probes) - this is above the target, which is exactly why the pilot-specific guard binds first.
* **Guaranteed maximum = the pilot-specific guard cap, $0.10** (below). The unguarded arithmetic bound above is what the cap protects against; if heavy reasoning shows up early, the pilot simply runs fewer of the 9 runs (about 5-6), and the report says so.

### 6.1 Budget guard (reuse `floodlab/budget.py` unchanged in logic; pilot-specific parameters only)
* **Pilot cap `PILOT_CAP = $0.10`** on spend since pilot start, **in addition to** the cumulative $0.90 effective / $1.00 hard caps (spent so far $0.007406 -> even a full $0.10 leaves $0.89 hard-cap headroom). Every request is refused unless `pilot_spent + worst_case_request <= $0.10` **and** `ledger_spent + worst_case <= 0.90`. A run only launches if the whole-run worst case also fits (as before).
* **Worst-case pre-charge per request, written to the ledger BEFORE the request:** `est_prompt_tokens = ceil(len(messages json)/3) + ceil(len(tools json)/3) + 300`; `worst = (est_prompt*price_in_guard + max_tokens*price_out_guard)/1e6 * 1.25`.
* **Guard prices (rounded UP with margin):** Novita/Xiaomi/DeepInfra `0.15 / 0.30` $/M (listed 0.14/0.28, +7%); if Venice were chosen `0.20 / 0.40` (listed 0.175/0.35, +14%). Plus the 1.25x margin.

| request | est prompt | max_tokens | pre-charge @0.15/0.30 | pre-charge @0.20/0.40 |
|---|---|---|---|---|
| connectivity | 1,000 | 64 | $0.00021 | $0.00028 |
| disconnect test each | 1,000 | 400 | $0.00034 | $0.00044 |
| family turn (typical) | 6,000 | 3,000 | $0.00225 | $0.00300 |
| family turn (late/F7) | 12,000 | 3,000 | $0.00338 | $0.00450 |
| family turn (ceiling, 16k prompt) | 16,000 | 3,000 | $0.00413 | $0.00550 |

  Whole-run launch check (8 turns at 12k/3k) = 8 x $0.00338 = **$0.027** at guard prices ($0.036 Venice); F7 ceiling 16k -> $0.033. So runs stop launching once pilot spend passes ~$0.07; this by itself limits the plan to ~7-9 runs of typical cost.
* **Per-run guard:** a run is stopped if its own settled cost exceeds **$0.02** (about 2.5x the expected run cost; heavy F7 is $0.018) or if any single request settles at > 3x its estimate (anomaly).
* **Prompt ceiling** for the pilot: 16,000 tokens (down from the 24,000 used for gpt-oss); a request whose estimate exceeds it is refused.
* **Reconciliation after approval:** (1) `usage.cost` from the streaming final usage chunk (`usage:{include:true}`) replaces the pre-charge (settle row); (2) `GET /api/v1/generation?id=...` `total_cost` and native token counts per generation (cancelled requests keep the pre-charge until reconciled, as before); (3) `GET /api/v1/key` `usage` counter delta before/after (read twice until stable - it lags about one test, seen with Darkbloom). Pass criteria as in P2-A: ledger within 20% of provider-reported (observed 0.0% for gpt-oss); any larger discrepancy = anomaly = stop and report. All three are compared in the final report. (`/generation` and `/key` are **not** used in this planning step.)

## 7. Provider recommendation

### 7.1 Recommended: **Novita** (`provider: {"order":["Novita"],"allow_fallbacks":false}`)
Reasons: (1) **stream-cancel is on OpenRouter's documented "Supported" list** (Novita and DeepInfra are listed; Xiaomi, GMICloud and Venice are **not listed at all** on https://openrouter.ai/docs/api-reference/streaming, which was fetched 2026-09-30 - the list is old/incomplete for new hosts, so absence means "undocumented", not "unsupported"); (2) identical lowest price ($0.14/$0.28), so the cost bound in section 6 holds; (3) healthy endpoint (status 0; uptime 98.9/98.0/97.0%); (4) `tools`+`tool_choice(auto)`+`reasoning`+`seed`+`stop` supported; (5) **checkpoint: unknown (provider-claimed)** - Novita's served weights (pre-fix RL vs MOPD) are unverified and must not be asserted in traces or reports; (6) avoids DeepInfra, which rate-limited this key for ~25 min on gpt-oss (429 history) and GMICloud (status -2), Venice (lowest 5-min uptime 93.6%, 1.25x price).
Caveats: 97% 1-day uptime means a small chance of transient 5xx/429 (handled by 5.4); `tool_choice` only `auto` (fine); Novita's own docs list "Anthropic API/Responses" but we use chat completions.

**Cancel/billing behavior for Novita is UNVERIFIED for this model** (the documented list is generic; gpt-oss on Darkbloom billed tokens received plus a small tail: 30 chunks -> 31 tokens, 400 -> 446, with `cancelled=False` in `/generation`). Cheapest measurement, part of stage 2 (3 requests, ~ $0.0005): no-tool prompt that would run long; abort after ~30 chunks and ~120 chunks, plus a control to `max_tokens` 400; compare `/generation` native completion tokens and `total_cost` with the tokens received, and the `/key` counter delta. Verdict rules: billed <= received x 1.2 + 60 tokens = "cancel stops billing"; billed ~ max_tokens = "provider runs to completion; any later stream cancels do NOT save money" (then the worst-case per-request pre-charge is treated as the real cost of every cancelled request - already the guard's default).

### 7.2 Runner-up (information only, not requested): **Xiaomi first-party**
Highest uptime (99.3/98.6/98.8%), same price, `tool_choice` auto+required, and it is the endpoint Xiaomi states has served the **MOPD** fix since 09-24 22:00 UTC - so it is the natural *contrast* endpoint if a later approval wants an RL-vs-fixed comparison. Downsides: not on the documented cancel list, no `seed`, `structured_outputs` only. (Others: DeepInfra - full tool_choice, documented cancel, but rate-limit history; Venice - 1.25x price; GMICloud - degraded status.)

### 7.3 Adaptive stopping summary
Stop the whole pilot when any of: 5 flood-qualifying runs (then human confirmation list for the maintainer, P2-B counted with N far below 100 - no rate claims); 9 runs done; pilot spend would exceed $0.10 (guard refusal); 3 consecutive generations with 1 call/generation (premise fails); any anomaly; exhausted 429 retries. Human confirmation of floods stays the maintainer's job.

## 8. Explicit unknowns and risks
1. Served checkpoint per provider (RL vs MOPD) - unknown, may change mid-pilot if the host redeploys; mitigation: provenance stamps + `/generation` provider/model per request; label "unknown".
2. If Novita/OpenRouter serves MOPD, floods may be rarer (Xiaomi reports repetition ~0.1-1% of responses; flooding >=10 calls in single turn ~11-25% of *pre-selected replay* examples on RL) - a null result is likely at N <= 9 and is **not** evidence about either checkpoint or about the guard.
3. Multi-call generations are expected but unverified through this host; the parallel-shape probe (section 4) is the first thing measured, with a stop rule.
4. Reasoning pass-back may not be honoured by the host; could change behavior versus Xiaomi's harnesses (measured via prompt-token accounting; flagged).
5. Hidden reasoning tokens can make requests 5-10x costlier than the "expected" case (F3 follow-up: 4,000-token reasoning loops); guard binds at $0.10 which may cut the plan to ~5-6 runs.
6. Parser/XML leakage or truncated calls; flood mid-generation (one 3,000-token generation can already hold 60+ calls, so a single generation can cross the 30-call threshold - harness cancels at qualification but the billed tokens up to abort are unavoidable).
7. Cancel/billing behavior unverified for Novita (7.1); OpenRouter's cancel list is stale.
8. The OpenRouter public page and endpoints API disagree on which providers host the model (page: Xiaomi only; API: five). Endpoint set may change after this snapshot; re-fetch (free) before any run and abort if the pinned provider is absent.
9. Frozen definition counts calls per run; MiMo's batched floods can qualify inside one or two generations - the cross-turn, rotating-arg (M2) case can also fail the ratio criterion by design (ratio counts distinct args). That is reported as-is; no criteria change.
10. Distinct-call ratio for M2/M3 can be > 0.35 even when behavior is repetitive; expected and documented.

## 9. Checklist for AFTER approval (nothing below has been done)
- [ ] Re-fetch `/api/v1/models/xiaomi/mimo-v2.6-flash/endpoints` (free); confirm Novita present, status 0; save the snapshot with time.
- [ ] Add MiMo run config in a new module (model `xiaomi/mimo-v2.6-flash`, pin `{"order":["Novita"],"allow_fallbacks":false}`, guard prices 0.15/0.30, pilot cap $0.10, prompt ceiling 16k, per-run cap $0.02, max_tokens 3000, max_turns 8/6, run set id `mimo-pilot-1`, `checkpoint: unknown` provenance); reuse existing collector/budget code; **no detector/guard/criteria edits**.
- [ ] Add descriptive-only recorders: `xml_leak`, calls-per-generation, reasoning pass-back check, provider/model per chunk. Extend tests; run full suite (all must pass); mock dry run of every stage ($0).
- [ ] Preflight: key present (never printed), ledger consistent ($0.007406), secret scan clean.
- [ ] Stage 1 connectivity (64 tokens) -> Stage 2 disconnect/billing test -> Stage 3 smoke (M2, 3 turns; stop rule on 1 call/generation) -> Stage 4 five families -> Stage 5 <= 3 extension runs. Reconcile after each run (usage.cost, `/generation`, `/key`).
- [ ] Stop and report on any anomaly, exhausted 429 retries, guard refusal, or 5 flood-qualifying runs. Never hop providers.
- [ ] Write the pilot report (not published; its figures are summarised in `docs/PHASE2A_SUMMARY.md`): per-run calls, calls/generation, distinct ratio, cycles, leaks, cancel/billing measurement, cost reconciliation, secret scan; human-confirmation list for the maintainer; explicit statement: exploratory-2A, checkpoint unknown, null result if < 5 qualifiers, no rate claims, **no Guard v2**.
- [ ] Secret scan (raw SSE `.gz`, data, ledger, reports), full pytest, commit (no push).


---
## 10. AMENDMENT (2026-10-01, attempt 3): pin changed from Novita to **Xiaomi first party** (the maintainer's "option B")

* Attempts 1-2 (Novita pin) aborted at $0 because Novita's OpenRouter status was -2 (degraded) at the pre-spend gate and for the whole 25-minute retry window. The pilot report (not published) keeps that history.
* New pin: `provider: {"order":["Xiaomi"],"allow_fallbacks":false}`, model `xiaomi/mimo-v2.6-flash`. Verified by chunk `provider` == Xiaomi (every chunk that names one) and `/generation` `provider_name` == Xiaomi; any other provider or a model mismatch = anomaly = stop. No other provider is allowed.
* Listed price on this endpoint: $0.14 in / $0.28 out / $0.0028 cache read per M (same as Novita). **Guard prices stay 0.15 / 0.30** (rounded up) with the 1.25x margin; pilot cap $0.10, per-run cap $0.02, prompt ceiling 16k; a new pilot-start ledger baseline ($0.007406; attempts 1-2 spent $0).
* Endpoint facts used (free GET 2026-10-01 06:17:49 ET): Xiaomi status 0, uptime 99.5 / 99.4 / 98.8 (5m/30m/1d), tools + tool_choice (auto, required) + reasoning supported, no `seed`, no `parallel_tool_calls`, max completion 131,072.
* **Interpretation:** this is a **likely-fixed-model CONTRAST**, not an attempt to reproduce the historical pre-fix RL failure. Xiaomi's post-mortem states its API has served the MOPD-fixed weights since 2026-09-25 06:00 (UTC+8) under unchanged model names; that is a provider claim and is not verified here. **Every trace and report is labelled `checkpoint: unknown (provider-claimed, likely fixed MOPD)`**; the served weights are never called "the historical RL checkpoint" and MOPD is never asserted as fact. A result of "no flood behavior" is therefore not evidence about the pre-fix model either.
* **Cancel/billing:** Xiaomi is NOT on OpenRouter's documented stream-cancel list; the stage-2 tiny disconnect test (3 requests, max_tokens 400) measures it; until measured, every cancelled request is treated at its worst-case pre-charge.
* **Premise check (stage 3, smoke, M2 run, 3 turns):** if three tool-calling generations in a row each contain exactly one tool call, the pilot stops and reports that the parallel-call premise was not observed. XML leaks / parser issues are recorded in all stages.
* Stop immediately at: 5 qualifying floods, provider != Xiaomi or model mismatch, the budget cap, repeated API failures, or any anomaly of section 5.4/6. If the pilot shows no meaningful flood behavior, live model hunting for this project stops (a project rule); no other provider or model is tried.
