# Data notice

## 1. Licence scope (exhaustive, per path)

Code is licensed under **Apache-2.0** (`LICENSE`, copyright 2026 nikhilll30). Documentation, fixtures, data and generated results are licensed under **CC BY 4.0** (`LICENSE-CC-BY-4.0.txt`; attribution: "nikhilll30, tool-call-loop-lab (2026)"). The two licence texts themselves are reproduced as published by their originators (the Apache Software Foundation and Creative Commons) and carry no additional licence (`none`).

Every tracked file of this repository is matched by **exactly one** row below, and every row matches at least one file. A build gate and the test `tests/test_data_notice_scope.py` enforce this. Pattern forms: an exact path; `dir/**` (everything below `dir`); `dir/*.ext` (one directory level only).

<!-- scope:start -->
| paths | licence | what it is |
|---|---|---|
| `floodlab/**` | Apache-2.0 | harness, mock upstream, detectors, evaluation, guard skeleton, live-collection runner (Python code) |
| `looptraps/*.py` | Apache-2.0 | loop-trap environments, runner, scripted agents, replay (Python code) |
| `tests/**` | Apache-2.0 | the offline test suite |
| `scripts/**` | Apache-2.0 | helper scripts (demo outputs, DATA_NOTICE scope checker) |
| `.github/**` | Apache-2.0 | CI workflow (tests only) |
| `configs/**` | Apache-2.0 | draft (never frozen) detector/guard configuration files |
| `Makefile` | Apache-2.0 | build/test shortcuts |
| `pytest.ini` | Apache-2.0 | pytest configuration |
| `requirements.txt` | Apache-2.0 | pinned Python dependencies (list of third-party package versions; the packages keep their own licences) |
| `.gitignore` | Apache-2.0 | git ignore rules |
| `README.md` | CC BY 4.0 | top-level documentation |
| `DATA_NOTICE.md` | CC BY 4.0 | this notice |
| `PHASE1_REPORT.md` | CC BY 4.0 | report of the synthetic offline Phase 1 |
| `PHASE1_5_REPORT.md` | CC BY 4.0 | report of the synthetic held-out Phase 1.5 |
| `docs/**` | CC BY 4.0 | case study, Phase 2A summary, background and citations, design documents, trace schema |
| `looptraps/README.md` | CC BY 4.0 | documentation of the loop-trap package |
| `looptraps/fixtures/*.jsonl` | CC BY 4.0 | the 12 minimized replay fixtures (call sequences, result hashes, classification; no model text) |
| `looptraps/fixtures/MANIFEST.json` | CC BY 4.0 | fixture manifest with file hashes and provenance anchors (see section 3) |
| `data/spend_summary.csv` | CC BY 4.0 | aggregate live spend (five rows) |
| `results/README.md` | CC BY 4.0 | description of the files under `results/` |
| `results/baseline_vs_new.png` | CC BY 4.0 | plot generated from synthetic traces |
| `results/demo_output.txt` | CC BY 4.0 | output of the offline demo (synthetic traces, loopback only) |
| `results/eval_report.md` | CC BY 4.0 | detector evaluation table on synthetic traces |
| `results/example_outputs.txt` | CC BY 4.0 | example detector outputs on synthetic traces |
| `results/per_trace.csv` | CC BY 4.0 | per-trace detector results on synthetic traces |
| `results/pytest_verbose.txt` | CC BY 4.0 | historical pytest output of Phase 1 (labelled as such) |
| `results/smoke_traces.jsonl` | CC BY 4.0 | scripted output of the loopback mock upstream (model name "mock"; not real model output) |
| `results/summary.json` | CC BY 4.0 | summary of the synthetic evaluation |
| `results/phase1_5/**` | CC BY 4.0 | outputs of the synthetic held-out Phase 1.5 evaluation |
| `MANIFEST.sha256` | CC BY 4.0 | sha256 of every file in the repository (except itself) |
| `LICENSE` | none | Apache License 2.0 text, as published by the Apache Software Foundation |
| `LICENSE-CC-BY-4.0.txt` | none | CC BY 4.0 legal code, as published by Creative Commons |
<!-- scope:end -->

Not tracked, but relevant: `data/heldout/heldout_v1.jsonl` (about 3 MB) is **not shipped**. It is deterministic generated data (`python -m floodlab.heldout`); the tests regenerate it when missing and check it against the SHA-256 pre-registered in `docs/SELECTION_PROCEDURE.md`. Once you generate it, treat it as CC BY 4.0.

## 2. Minimization of the fixtures

Each fixture keeps only: run id, split, model name, scenario, seed, prompt and tool-schema version labels, the per-turn, per-generation tool calls (index, tool name, arguments, hash of the tool result), the finish reason (first token only), the termination reason, a close-out `classification`, and a `derived` note. Everything else in the stored runs was removed: model text, reasoning text, provider and generation identifiers, which provider served a request, token usage, costs, latencies, timestamps and the message history.

The MiMo fixtures carry the checkpoint label "unknown (provider-claimed, likely fixed MOPD)". These runs are exploratory, were produced against stateless mock tools, and must not be read as rates or as a reproduction of any vendor-reported failure. They are minimized derivations of private raw traces, not the raw traces themselves.

## 3. What can and cannot be verified

- **Verifiable from this repository:** every fixture file against `looptraps/fixtures/MANIFEST.json` (field `fixture_file_sha256`, checked by a test); every file against `MANIFEST.sha256`; the statistics tagged as derivable in `docs/CASE_STUDY.md` (checked by a test); the sum of the spend rows against the stated total.
- **NOT publicly verifiable:** the manifest field `source_line_sha256` and the `derived_from_canonical_commit` value. They are **provenance anchors against the author's private canonical record**: they let the author show later that a fixture was derived from a given private trace line, but nobody else can recompute them because the source traces are not published. Likewise the spend figures come from a private ledger, and figures tagged "reported from private raw traces" in the docs cannot be reproduced from this repository.

## 4. What is not shipped

Raw traces and raw streaming logs; the spend ledger; saved vendor web pages, API catalog snapshots and pricing notes (third-party material); verbatim copies of model output; the original (verbatim) fixtures; the held-out dataset file (see above).

## 5. Attribution and names

Attribution for CC BY 4.0 material: "nikhilll30, tool-call-loop-lab (2026)". Third-party names (Xiaomi, MiMo, DeepInfra, Darkbloom, OpenRouter, gpt-oss) are used only as factual labels of what was called and remain the property of their owners.
