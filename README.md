# tool-call-loop-lab

Offline replay harness, detectors and deterministic loop-trap environments for studying repetitive LLM tool calls. Exploratory; no rate claims.

> **EXPLORATORY. No rate claims. We did not reproduce Xiaomi's historical failure. The MiMo checkpoint served in our pilot is unknown (provider-claimed, likely fixed MOPD). Zero human-confirmed floods.**

Author: [nikhilll30](https://github.com/nikhilll30). This repository was extracted from a longer private research effort; it contains the reusable offline code, the synthetic evaluation material and a small set of minimized replay fixtures. Total live spend across the whole effort: **$0.013420** (see [`data/spend_summary.csv`](data/spend_summary.csv); the figures come from a private ledger and cannot be audited from this repository).

**How to read the numbers in this repository.** A figure is either (a) *reproducible here* (from the 12 fixtures via `python -m looptraps fixtures`, from the shipped `results/`, or from the spend CSV), or (b) tagged **"reported from private raw traces, not reproducible from this repository"**, meaning it is the author's unaudited statement about raw data that is not published. Untagged figures in this README are of kind (a) unless stated otherwise.

## What this is, and is not

**This is** a small, offline toolkit: a streaming trace harness with a loopback mock upstream, a set of detectors for repetitive tool-call patterns (evaluated on *synthetic* traces), a "loop-trap" package of deterministic mock-tool environments in which repetition can never make progress, and twelve minimized replay fixtures derived from private records of real model runs (call sequences only; the raw runs are not published, see [`DATA_NOTICE.md`](DATA_NOTICE.md)). Everything in the test suite runs offline at $0; a socket guard fails any non-loopback connection.

**This is not** a benchmark, a validated guard, or evidence about how often any model loops. It does not reproduce the failure described by Xiaomi or in the MiMo Code issues cited below. No detector or guard was frozen. The live part of the effort was a handful of runs on mock tools, with a total of $0.013420 spent.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt     # Python 3.11+; tested on 3.13.5
.venv/bin/python -m pytest -q                                          # expect: 188 passed, 1 skipped (offline)
.venv/bin/python -m looptraps list                                     # the 11 loop-trap environments
.venv/bin/python -m looptraps demo --env M2_rotating_batch             # scripted stand-in agent, not a model
.venv/bin/python -m looptraps fixtures                                 # summaries of the 12 replay fixtures
.venv/bin/python -m floodlab.run_offline_demo                          # synthetic traces, detector evaluation, plots
```

The held-out synthetic dataset (`data/heldout/heldout_v1.jsonl`, about 3 MB) is **not shipped**; it is deterministic generated data. The test suite regenerates it automatically if it is missing and checks the result against its pre-registered SHA-256. To regenerate by hand: `python -m floodlab.heldout`. The regenerated file is byte-identical to the original.

## What's inside

| path | purpose |
|---|---|
| `floodlab/` | trace harness, SSE parsing, loopback mock upstream, detectors, evaluation, draft guard proxy, live-collection runner with budget controls (not run by CI) |
| `looptraps/` | no-spend loop-trap environments, scripted agents, guard hook, replay of fixtures (`looptraps/README.md`) |
| `looptraps/fixtures/` | 12 minimized replay fixtures plus a manifest (file hashes are checkable; source-line hashes are private provenance anchors, see `DATA_NOTICE.md`) |
| `tests/` | the offline test suite |
| `results/` | outputs of the synthetic Phase 1 / 1.5 evaluations (properties of generated traces, not real-world rates); two pytest outputs there are historical (`results/README.md`) |
| `docs/` | case study, Phase 2A summary, background and citations, frozen reporting criteria, evaluation stages, trace schema |
| `data/spend_summary.csv` | aggregate live spend, five rows |
| `PHASE1_REPORT.md`, `PHASE1_5_REPORT.md` | reports of the synthetic offline phases |

## Findings in brief (exploratory)

- **gpt-oss-20b (DeepInfra, Darkbloom): nulls.** Reproducible here: the 3 shipped gpt-oss-20b fixtures make exactly one tool call per generation (38 tool-calling generations) and reach 12, 12 and 14 calls. Reported from private raw traces, not reproducible from this repository: one call per generation in all 109 tool-calling generations of the Darkbloom pilot, and none of 10 follow-up runs with a pagination trap reaching 30 calls (maximum 14).
- **Xiaomi MiMo-V2.6-Flash (first-party endpoint), 9 runs, all shipped as fixtures: multi-call generations occurred.** Reproducible here: 34 of the 45 tool-using generations had two or more calls, maximum 8. Four runs in one mock "pending" polling family crossed the machine threshold (at least 30 calls and a distinct-signature ratio of at most 0.35); the harness cancelled each at 30 calls, so we do not know whether they would have continued. They were **rejected as human-confirmed floods** and reclassified as machine-qualified repetitive polling loops (the close-out classification is stored in each fixture and is a single reviewer's judgement, not reproducible). Two other runs were near-misses (25 and 24 calls, stopped by an 8-turn cap).
- **Zero human-confirmed floods overall.** The pre-registered primary result needed at least 5 at N of at least 100, so it is a null result and says nothing about any model, checkpoint, provider or guard. (The human classification is the author's; the fixtures show the call sequences it was based on.)
- **Checkpoint: unknown** (provider-claimed, likely fixed MOPD). Nothing in our data verifies which weights were served.

Read the [case study](docs/CASE_STUDY.md) (loop shapes, caveats, limitations) and the [Phase 2A summary](docs/PHASE2A_SUMMARY.md).

## Loop-trap suite

`looptraps/` offers 11 deterministic, stateless mock-tool environments (for example a batch of writes that always answers "cancelled", a lookup that always answers "pending", a pagination trap that sends the agent back to page 1) plus a runner that accepts any callable agent, a guard hook (`guard(gens) -> reason | None`), scripted stand-in agents and `ReplayAgent`, which replays the call sequence of a stored run. It makes no network calls and reads no environment variables (a test enforces this). If you plug in an agent that calls a paid model, that spend is yours. See [`looptraps/README.md`](looptraps/README.md).

**Fixtures.** The 12 replay fixtures are *minimized derivations* of stored runs: tool name, arguments, result hashes, finish reason and a close-out `classification`. They contain no model text, reasoning, provider payloads, ids, timings or costs. `looptraps.human_label()` returns the classification; the manifest records a hash of every fixture file (checkable) and, per run, the hash of the private source line it was derived from. **The source-line hashes are provenance anchors against the author's private canonical record and are not publicly verifiable**, because the source traces are not published. See [`DATA_NOTICE.md`](DATA_NOTICE.md).

## Method and caveats

- The environments are **stateless**: results depend only on arguments, never on call count, so repetition is never rewarded. A model that keeps polling a tool that can never succeed is not clearly "wrong" without knowing what a real tool would do.
- The distinct-ratio criterion is **nearly automatic with a small argument pool**: with 10 ids, any run of 30 or more calls has a ratio of at most 0.333.
- The four machine-qualified runs are **not independent** (same prompt and tool, different id strings; identical call-index sequences).
- **Small N** (9 MiMo runs; a few dozen gpt-oss-20b runs, reported from private raw traces), one provider and one time window per model, sampling parameters and seed not sent, so runs are not reproducible at the model level (the environments are deterministic; the model is not).
- The "frozen criteria" ([`docs/FROZEN_CRITERIA_PHASE2.md`](docs/FROZEN_CRITERIA_PHASE2.md)) are a **reporting threshold**, not a detector; a human must confirm a run before it counts as a flood, and the human labels are a single reviewer's reading.
- The Phase 1 / 1.5 detectors are **drafts**; nothing was frozen because no policy met the pre-registered bounds. The held-out synthetic set was examined in detail, so it cannot serve as clean confirmation of future changes. Known gaps: cross-generation repetition, near-duplicates with a changing field, cancel-and-retry loops, slow drift, noisy-result repeats.

## What is NOT claimed

- No reproduction of Xiaomi's historical failure, or of any flood described in the issues cited below.
- No rate at which any model "floods", and no claim that any model is safe because few or no confirmed floods were seen.
- No claim that the four polling runs were runaway floods; they were rejected as human-confirmed floods.
- No claim about which checkpoint (RL or MOPD) was served, or whether the vendor's fix works.
- No claim that any detector or guard works, fails or is ready.
- No claim that the loop shapes are a complete taxonomy or would arise with real, stateful tools.

## Citations

How these were checked: on **2026-10-01** the maintainer re-opened each source below live and read its content; the statements attributed to them in this repository are paraphrases of what they said at that time. **This is not independent reproduction: none of their claims was reproduced or independently verified**, and the sources are vendor-reported or user-reported. The links were additionally checked by the build for an HTTP 200 response only (a liveness check, not a content check).

- Xiaomi MiMo Team, "Diagnosing and Mitigating Tool-Call Repetition in MiMo-V2.6", 2026-09-27 (vendor post): <https://mimo.xiaomi.com/blog/mimo-v2-6-tool-call-repetition>
- MiMo Code issue #2482 (user report), according to which one generation contained 4,120 tool calls over 35 distinct inputs: <https://github.com/XiaomiMiMo/MiMo-Code/issues/2482>
- MiMo Code issue #2509 (user report), according to which a byte-identical 17-call batch was re-emitted ten times after the host's flooding guard cancelled most of it: <https://github.com/XiaomiMiMo/MiMo-Code/issues/2509>
- Model card, MiMo-V2.6-Flash-MOPD (vendor): <https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-MOPD>

What each source says is summarized in [`docs/BACKGROUND.md`](docs/BACKGROUND.md). Other external links in the documentation (an OpenRouter endpoints API URL, an OpenRouter docs page, the author's GitHub profile) were checked for HTTP 200 only.

## Data and provenance

Raw per-run traces, raw SSE logs, the spend ledger, saved vendor web pages and API catalog snapshots, and the original (verbatim) fixtures are **not published**: they contain model text and provider payloads and third-party material. What ships instead is derived: minimized fixtures, aggregate spend, and rewritten summaries. Provider and model names (Xiaomi, DeepInfra, Darkbloom, OpenRouter, gpt-oss-20b, MiMo) appear as plain factual labels of what was called. Absolute paths and personal names were redacted. No API key is needed or used by anything here, and CI never has access to secrets.

## Licence

- **Code:** Apache License 2.0 ([`LICENSE`](LICENSE)), copyright 2026 nikhilll30.
- **Documentation, fixtures and data:** Creative Commons Attribution 4.0 International ([`LICENSE-CC-BY-4.0.txt`](LICENSE-CC-BY-4.0.txt)).
- The exact licence of every file is listed in [`DATA_NOTICE.md`](DATA_NOTICE.md) (each file falls under exactly one entry; a test checks this). The two licence texts are unlicensed copies as published by their originators.

## Contributing and security

Issues and pull requests are welcome if they keep the test suite offline. Please do not add API keys or live-call code to CI. If you find a credential-shaped string anywhere in this repository, open an issue without pasting it.

## Citing

> nikhilll30. *tool-call-loop-lab: offline replay harness, detectors and loop-trap environments for repetitive LLM tool calls* (exploratory, 2026).
