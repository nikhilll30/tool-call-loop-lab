# Background and citations

**Verification status.** On **2026-10-01** the maintainer re-opened each source below live (link fetched, content read) and wrote the summaries from what it said at that time. **No claim made by any source was reproduced or independently verified**; the sources are vendor-reported (Xiaomi post, model card) or user-reported (GitHub issues), and nothing in this repository's data confirms or refutes them. The build separately checked each link for an HTTP 200 response only. Each claim is phrased as "according to" its source and paraphrased, not quoted.

## Xiaomi MiMo Team post-mortem (2026-09-27)

<https://mimo.xiaomi.com/blog/mimo-v2-6-tool-call-repetition>

According to this post:

- After the release of MiMo-V2.6, tool-call repetition became a prominent problem in agentic settings (MiMo Desktop, MiMo Code, OpenCode and others); Xiaomi's internal evaluations put the response-level repetition rate above 0.05%.
- The post distinguishes normal parallel tool calls, tool-call *flooding* (many more calls than the task needs) and tool-call *repetition* (repeated actions with no justification), and uses a narrow metric, exact within-turn repetition, as a lower bound.
- Xiaomi attributes the flooding to its RL training: a penalty that triggered only above 32 calls per turn was too permissive.
- Its fix was a specialized repetition teacher merged by multi-teacher on-policy distillation (MOPD).
- Xiaomi states that updated models with unchanged names (`mimo-v2.6-pro`, `mimo-v2.6-flash`) have been available on its API platform since 2026-09-25 06:00 (UTC+8), and that MOPD checkpoints were open-sourced on Hugging Face.

## MiMo Code issue #2482

<https://github.com/XiaomiMiMo/MiMo-Code/issues/2482>

A user report which, according to its text, describes a single generation of 4,120 tool calls that rotated over 35 distinct inputs.

## MiMo Code issue #2509

<https://github.com/XiaomiMiMo/MiMo-Code/issues/2509>

A user report which, according to its text, describes a byte-identical batch of 17 tool calls that was re-emitted ten times after the MiMo Code host raised its tool-call flooding error. As described there, the host's guard cancels all but one call of an oversized batch and releases one call per round (so it is not simply a cap of 16 calls per batch).

## Hugging Face model card, MiMo-V2.6-Flash-MOPD

<https://huggingface.co/XiaomiMiMo/MiMo-V2.6-Flash-MOPD>

According to the card, this checkpoint is the MOPD upgrade of the MiMo-V2.6-Flash-RL checkpoint and mitigates the tool-call repetition problem described in the post above.

## Consequence for this repository

The only MiMo endpoint used was Xiaomi's first-party API through OpenRouter, which per Xiaomi's post has served the fixed checkpoint since 2026-09-25. The checkpoint actually served in our pilot is therefore recorded as **unknown (provider-claimed, likely fixed MOPD)**, and this repository does not claim to reproduce the failure described in these sources.
