## Human Overview

> HUMAN: replace this paragraph with ~50 words in your own words (repo policy:
> AI-drafted issues require a human overview; see team/AI_USAGE_POLICY.md).
> Suggested gist: `strands_harness.models._gemini()` unconditionally passes
> `thinking_config={"thinking_level": effort}` whenever `effort` is not `None`,
> which Gemini 3 accepts but Gemini 2.5 models (`gemini-2.5-pro`,
> `gemini-2.5-flash`) reject because they require integer `thinking_budget`.

## Checks

- [x] I have updated to the lastest minor and patch version of Strands
- [x] I have checked the documentation and this is not expected behavior
- [x] I have searched [./issues](./issues?q=) and there are no duplicates of my issue

## SDK Language

Python

## Strands Version

strands-harness 0.4.0 (with strands-agents 1.65.0)

## Language Runtime Version

Python 3.12 / 3.14

## Operating System

Linux

## Installation Method

uv (`strands-harness>=0.4.0`, `strands-agents[gemini]`)

## Steps to Reproduce

1. Install the Gemini extra (`strands-agents[gemini]`).
2. Call `resolve_model` on any Gemini 2.5 model with an explicit `effort`:

   ```python
   from strands_harness.models import resolve_model

   model = resolve_model("google/gemini-2.5-pro", "google/gemini-2.5-flash", effort="high")
   print(model.get_config()["params"])
   # {'thinking_config': {'thinking_level': 'high'}}
   ```

3. Use the resulting `GeminiModel` in a request against the Google GenAI API.

## Expected Behavior

For `gemini-2.5-*` models, `effort` should map to `thinking_config={"thinking_budget": ...}` (for example `0` for off/none, or an integer/dynamic token budget `-1` / positive count), reserving `"thinking_level"` for Gemini 3+ models that accept string thinking levels.

## Actual Behavior

In `strands_harness/models.py`, `_gemini()` unconditionally sets:

```python
if effort is not None:
    extra["params"] = {"thinking_config": {"thinking_level": effort}}
```

Because `supports_thinking("google/gemini-2.5-pro")` returns `True`, routed/effort-aware callers pass `effort="high"` / `"medium"` / `"low"` on Gemini 2.5 and emit `"thinking_level"` for a model family that expects `"thinking_budget"`.

(Additionally, when `web_search=True` is enabled on Gemini 2.5, `_gemini()` injects `gemini_tools=[Tool(google_search=GoogleSearch())]`; paired with custom function declarations on `models/gemini-2.5-flash`, the Gemini Developer API returns `400 INVALID_ARGUMENT: Tool call context circulation is not enabled for models/gemini-2.5-flash`. Gemini 3.8+ and Gemini 4 accept both together.)

## Possible Solution

Guard `_gemini()` by model family: emit `"thinking_budget"` for `gemini-2.5*` model ids (e.g. `0` when effort is `"off"`/`"none"`, `-1` dynamic thinking when enabled), reserve `"thinking_level"` for `gemini-3*`+ models, and omit built-in `GoogleSearch()` `gemini_tools` on `gemini-2.5*` when custom function declarations are attached. Downstream in `CsabaConsulting/strands-code`, `configure_gemini_for_model()` rewrites `params["thinking_config"]` and clears `gemini_tools=[]` on `gemini-2.5*` as a defensive workaround until fixed upstream.
