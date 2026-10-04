## Human Overview

> HUMAN: replace this paragraph with ~50 words in your own words (repo policy:
> AI-drafted issues require a human overview; see team/AI_USAGE_POLICY.md).
> Suggested gist: Bedrock model-family coverage in harness-py `models.py`
> lags the current Bedrock catalog in two places — the web_fetch
> summarizer map and Nova 2 thinking support.

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

Part A — web_fetch summarizer family map:

1. `from strands_harness.models import resolve_web_fetch_model`
2. `resolve_web_fetch_model("google.gemma-3-27b-it", None)`
3. Observe the warning; the main model is reused as its own summarizer.

Part B — Nova 2 thinking never enabled:

1. `from strands_harness.models import resolve_model`
2. `resolve_model("global.amazon.nova-2-lite-v1:0", "global.amazon.nova-2-lite-v1:0")`
3. Inspect the built `BedrockModel`: no `reasoningConfig` in
   `additional_request_fields`, so the turn runs thinking-off even though
   Nova 2 documents `reasoningConfig` (`type` + `maxReasoningEffort`).

## Expected Behavior

Part A: non-Anthropic/OpenAI Bedrock families resolve a small same-provider
summarizer (or the reuse-the-main-model fallback stays silent when intended).
Part B: Nova 2 ids get the documented `reasoningConfig` treatment so effort
levels apply like the other thinking families.

## Actual Behavior

Part A: `_bedrock_web_fetch_model` only recognizes `anthropic.*` and
`openai.*`; every other Bedrock family (google, meta, mistral, qwen,
amazon, xai, …) logs `could not identify the Bedrock model family for the
web_fetch summarizer` and reuses the main model. Part B: `_bedrock_levels` /
`_bedrock_thinking` have no Nova branch, so Nova 2 turns silently run
thinking-off.

## Possible Solution

Part A: extend the family map with small-model picks per Bedrock family, or
add an explicit opt-out/silence knob for intentional main-model reuse.
Part B: add a Nova branch mapping effort levels to
`{"reasoningConfig": {"type": "enabled", "maxReasoningEffort": ...}}` per the
Nova 2 user guide. Happy to split this into two issues if preferred.

## Additional Context

Downstream reporter: `CsabaConsulting/strands-code` (Phase 5 model switching;
`harness-py` consumed via `resolve_model` / `create_harness`).

<details>
<summary>Live evidence (us-west-2, 2026-09-27)</summary>

- Part A reproduces for any Bedrock id outside the two mapped families;
  e.g. `google.gemma-3-27b-it` warns twice per agent build (main model +
  summarizer resolution paths).
- Part B: `ListFoundationModels` shows `amazon.nova-2-lite-v1:0` (TEXT+IMAGE+
  VIDEO in); direct `Converse` with
  `additionalModelRequestFields={"reasoningConfig": {"type": "enabled",
  "maxReasoningEffort": "low"}}` returns native `reasoningContent`, and a
  thinking-off replay of those blocks is accepted (no `ValidationException`).
  Docs: `https://docs.aws.amazon.com/nova/latest/nova2-userguide/extended-thinking.html`
  and `https://aws.amazon.com/blogs/aws/introducing-amazon-nova-2-lite-a-fast-cost-effective-reasoning-model`.

</details>

## Related Issues

https://github.com/strands-agents/harness-sdk/issues/4852
