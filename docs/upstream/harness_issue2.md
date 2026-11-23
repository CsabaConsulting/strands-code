# Filed URL

https://github.com/strands-agents/harness-sdk/issues/4857

---

## Human Overview

> HUMAN: replace this paragraph with ~50 words in your own words (repo policy:
> AI-drafted issues require a human overview; see team/AI_USAGE_POLICY.md).
> Suggested gist: Several Amazon Bedrock models (Mistral Large 24.02/24.07,
> Pixtral Large 25.02, Writer Palmyra X4/X5, and Meta Llama 3/4) reject tool use
> over the streaming ConverseStream API but accept it over non-streaming
> Converse, so every tool-carrying streamed turn fails; the SDK should fall back.

## Checks

- [x] I have updated to the lastest minor and patch version of Strands
- [x] I have checked the documentation and this is not expected behavior
- [x] I have searched [./issues](./issues?q=) and there are no duplicates of my issue

## SDK Language

Python

## Strands Version

strands-harness 0.4.0 (with strands-agents 1.65.0)

## Language Runtime Version

Python 3.14

## Operating System

Linux

## Installation Method

uv (pip-compatible)

## Steps to Reproduce

1. Build any agent with tools on a unary-only Bedrock model, e.g.
   `BedrockModel(model_id="mistral.mistral-large-2402-v1:0")` (active on-demand;
   also reproduces on `mistral.mistral-large-2407-v1:0` and
   `us.mistral.pixtral-large-2502-v1:0`, plus `LEGACY`-gated
   `us.writer.palmyra-x4-v1:0`, `us.writer.palmyra-x5-v1:0`, and Meta Llama 3/4).
2. Run a turn (the agent streams by default with `toolConfig` attached).
3. The turn fails with `ValidationException: ... This model doesn't
   support tool use in streaming mode.`
4. Contrast: plain boto3 `bedrock-runtime.converse` (non-streaming) with
   the same `toolConfig` on the same model id succeeds and can return
   `toolUse` blocks.

## Expected Behavior

When streaming Converse rejects `toolConfig` with the
doesn't-support-tool-use-in-streaming-mode `ValidationException`, the
model layer retries that turn over non-streaming Converse instead of
failing it — streaming stays the default, the fallback covers models
whose Bedrock config restricts tool use to the unary API.

## Actual Behavior

The `ValidationException` propagates and the turn fails. Every turn on
an affected model fails identically (tools are always attached), so the
models are unusable through the SDK despite supporting tool use.

## Possible Solution

In the Bedrock streaming path, catch the specific `ValidationException`
(tool-use-in-streaming-mode) and re-issue the request via unary
`converse`, adapting the response into the stream event shape the agent
loop consumes. Alternatively a model-scoped streaming-policy table could
route known-affected Bedrock ids (`mistral-large-2402`,
`mistral-large-2407`, `pixtral-large-2502`, `palmyra-x4`, `palmyra-x5`,
Meta Llama 3/4) to `streaming=False` up front — note that vendor-wide
rules are unsafe because newer Mistral models (`mistral-large-3-675b-instruct`,
`devstral-2-123b`, `ministral-3-8b-instruct`, `magistral-small-2509`) do
support streaming tool use.

## Additional Context

Downstream reporter: `CsabaConsulting/strands-code` (model switching
across the Bedrock catalog; affected unary-only turns fail unless
`streaming=False` is configured, while Anthropic / Nemotron / Nova /
GPT-OSS / Mistral Large 3 turns on identical tool sets stream cleanly).

<details>
<summary>Live evidence (us-west-2, 2026-09-27 &amp; 2026-11-21)</summary>

- **Active unary-only models (2026-11-21):**
  `mistral.mistral-large-2402-v1:0`, `mistral.mistral-large-2407-v1:0`, and
  `us.mistral.pixtral-large-2502-v1:0`: `ConverseStream` + `toolConfig`
  → `ValidationException` (`This model doesn't support tool use in streaming mode.`);
  unary `converse` + identical `toolConfig` → `stopReason=tool_use`.
- **Active streaming-capable contrast (2026-11-21):**
  `mistral.mistral-large-3-675b-instruct`, `mistral.devstral-2-123b`,
  `mistral.ministral-3-8b-instruct`, `mistral.magistral-small-2509`:
  `ConverseStream` + `toolConfig` → succeeds.
- **Legacy-gated unary-only models (2026-09-27 &amp; 2026-11-21):**
  `us.meta.llama4-scout-17b-instruct-v1:0`, `us.meta.llama3-3-70b-instruct-v1:0`,
  `us.writer.palmyra-x4-v1:0`, `us.writer.palmyra-x5-v1:0`: `ConverseStream`
  + `toolConfig` → `ValidationException` (`This model doesn't support tool use in streaming mode.`);
  unary `converse` accepted Llama on 2026-09-27 before Meta Llama and
  Writer Palmyra entered Bedrock's 30-day `LEGACY` gate.

</details>
