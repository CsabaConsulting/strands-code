# Upstream Bug Report: `strands_harness.models._openai()` Emits `reasoning.effort` Unconditionally on Non-Reasoning and Effort-Subset OpenAI Models

> **HOLD BEFORE PUBLISHING:** Complete `## Human Overview` in your own words per `team/AI_USAGE_POLICY.md`. Downstream `strands-code` carries a temporary fail-soft guard (`configure_openai_for_model()` in `strands_code_cli/model/model_switch.py`) until upstream Harness validates effort capabilities per OpenAI model family.

- **Target repo:** `strands-agents/harness-sdk` (`main` / tag `python/v1.65.0`, `strands-harness 0.4.0`)
- **Downstream reference:** `CsabaConsulting/strands-code#17`

---

## 1. Issue Title

```text
[BUG] strands_harness.models._openai() emits reasoning.effort on non-reasoning models and unsupported effort levels on effort-subset OpenAI models
```

## 2. Issue Body

```markdown
## Human Overview

[TODO: Replace with a brief 2-3 sentence summary in your own words before publishing — e.g.: When resolving native OpenAI models through `strands_harness.models.resolve_model("openai/...")`, `_openai()` attaches `params={"reasoning": {"effort": "high"}}` even on non-reasoning models (`gpt-4o`, `gpt-4.1*`, `gpt-4-turbo`, `chat-latest`) and forwards Harness effort levels (`minimal`, `xhigh`, `max`, `off`) verbatim to effort-subset families (`o1`/`o3`/`o4-mini`, `gpt-5`..`gpt-5.2`, `gpt-6-astra`/`gpt-6.1-sol`). This triggers HTTP 400 rejections from the OpenAI Responses API on non-reasoning models and mismatched effort levels.]

## Bug Description

In `strands-harness 0.4.0` (`harness-py/src/strands_harness/models.py`), resolving native `openai/<model>` strings via `resolve_model()` builds an `OpenAIResponsesModel` with:

- Default `effort=None`: attaches `params={"reasoning": {"effort": "high"}}` unconditionally, even for non-reasoning OpenAI models (`gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4-turbo`, `chatgpt-4o-latest`, `gpt-3.5-turbo`).
- Routed `effort` values (`"off"`, `"minimal"`, `"xhigh"`, `"max"`): passed through without model-family clamping for families that only accept subsets:
  - `o1` / `o3` / `o4-mini`: accept only `low | medium | high` (reject `"minimal"`, `"xhigh"`, `"max"`, `"off"`).
  - `gpt-5`..`gpt-5.2`: accept `minimal | low | medium | high` (reject `"xhigh"`, `"max"`, `"off"`).
  - `gpt-6-astra` / `gpt-6.1-sol`: accept `low | medium | high | xhigh` (reject `"minimal"`, `"off"`).

## Reproduction (Verified on `strands-harness 0.4.0`)

```python
from strands_harness.models import resolve_model

for model_id, effort in [
    ("openai/gpt-4o", None),
    ("openai/gpt-4.1-mini", None),
    ("openai/o3", "minimal"),
    ("openai/o3", "xhigh"),
    ("openai/gpt-5", "xhigh"),
    ("openai/gpt-6.1-sol", "minimal"),
]:
    kw = {"effort": effort} if effort else {}
    resolved = resolve_model(model_id, model_id, **kw)
    print(model_id, effort, type(resolved).__name__, resolved.get_config().get("params"))
```

Observed output on `strands-harness 0.4.0`:

```text
openai/gpt-4o None -> OpenAIResponsesModel {'reasoning': {'effort': 'high'}}
openai/gpt-4.1-mini None -> OpenAIResponsesModel {'reasoning': {'effort': 'high'}}
openai/o3 minimal -> OpenAIResponsesModel {'reasoning': {'effort': 'minimal'}}
openai/o3 xhigh -> OpenAIResponsesModel {'reasoning': {'effort': 'xhigh'}}
openai/gpt-5 xhigh -> OpenAIResponsesModel {'reasoning': {'effort': 'xhigh'}}
openai/gpt-6.1-sol minimal -> OpenAIResponsesModel {'reasoning': {'effort': 'minimal'}}
```

## Expected Behavior

1. Non-reasoning OpenAI models (`gpt-4o*`, `gpt-4.1*`, `gpt-4-turbo*`, `*chat-latest*`, `gpt-4`, `gpt-3.5*`) should omit `"reasoning"` from `params`.
2. Effort-subset OpenAI models should clamp/omit unsupported `effort` strings rather than sending invalid Responses API parameters (`"off"`/`"none"` should omit `"reasoning"`; `o1`/`o3`/`o4-mini` should clamp `"minimal"` -> `"low"` and `"xhigh"`/`"max"` -> `"high"`; `gpt-5`..`5.2` should clamp `"xhigh"`/`"max"` -> `"high"`; `gpt-6-astra`/`gpt-6.1-sol` should map `"minimal"` -> `"low"`).

## Suggested Fix & Downstream Workaround

- Update `supports_thinking()` / `_openai()` in `strands_harness/models.py` (alongside `shared/model-info.json` capabilities) so non-reasoning OpenAI models do not receive `reasoning` params and effort levels clamp per model family.
- Reference workaround implemented downstream in `CsabaConsulting/strands-code`: `configure_openai_for_model()` in `strands_code_cli/model/model_switch.py`.
```

---

## 3. Held Publish Command (Run Only After Human Review)

```bash
# Edit ## Human Overview in your own words first, then copy ONLY the fenced markdown block from Section 2 (excluding the top HOLD notice and Section 3) to /tmp/openai_reasoning_guard_issue.md
gh issue create \
  --repo strands-agents/harness-sdk \
  --title "[BUG] strands_harness.models._openai() emits reasoning.effort on non-reasoning models and unsupported effort levels on effort-subset OpenAI models" \
  --body-file /tmp/openai_reasoning_guard_issue.md
```
