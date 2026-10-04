## Human Overview

> HUMAN: replace this paragraph with ~50 words in your own words (repo policy:
> AI-drafted issues require a human overview; see team/AI_USAGE_POLICY.md).
> Suggested gist: Llama models on Bedrock reject tool use over the
> streaming Converse API but accept it over non-streaming Converse, so
> every tool-carrying streamed turn fails; the SDK should fall back.

## Checks

- [x] I have updated to the lastest minor and patch version of Strands
- [x] I have checked the documentation and this is not expected behavior
- [x] I have searched [./issues](./issues?q=) and there are no duplicates of my issue

## SDK Language

Python

## Strands Version

strands-harness 0.1.2 (with strands-agents 1.57.0)

## Language Runtime Version

Python 3.14

## Operating System

Linux

## Installation Method

uv (pip-compatible)

## Steps to Reproduce

1. Build any agent with tools on a Bedrock Llama model, e.g.
   `BedrockModel(model_id="us.meta.llama4-scout-17b-instruct-v1:0")`.
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
loop consumes. Alternatively a per-model streaming-policy table could
route known-affected ids (Bedrock Llama 3/4 families, verified) to unary
up front.

## Additional Context

Downstream reporter: `CsabaConsulting/strands-code` (model switching
across the Bedrock catalog; Llama turns fail while Anthropic / Nemotron
/ GPT-OSS turns on identical tool sets succeed).

<details>
<summary>Live evidence (us-west-2, 2026-09-27)</summary>

- `us.meta.llama4-scout-17b-instruct-v1:0` and
  `us.meta.llama3-3-70b-instruct-v1:0`: `ConverseStream` + `toolConfig`
  → `ValidationException` (doesn't support tool use in streaming mode).
- Same ids, unary `converse` + identical `toolConfig` → accepted;
  response contained `toolUse` blocks. Minimal boto3 repro available on
  request.

</details>

## Related Issues

https://github.com/strands-agents/harness-sdk/issues/4857
