# Filed URL

https://github.com/strands-agents/harness-sdk/issues/6521

Updated: 2026-11-24 (title and body updated in place with empirical verification from live api.meta.ai/v1 testing).

---

# Title

`[FEATURE] Add first-class Meta Model API (meta/ / Muse) provider in Harness and shared/model-info.json`

---

# Body

```markdown
*(Disclosure: empirical update drafted with AI assistance and reviewed/edited by me; see `team/AI_USAGE_POLICY.md`.)*

## Human Overview

`LlamaAPIModel` targets Meta's retired legacy Llama API and is slated for removal in v2.0, leaving no built-in Harness provider or `model_info.json` metadata for Meta's current Meta Model API (`https://api.meta.ai/v1`, serving Muse Wonder, Muse Spark, and Muse Ember). Since Meta recommends `/v1/responses` natively for agentic loops, adding a `meta/<model>` provider built on `OpenAIResponsesModel` (matching `bedrock-mantle`'s pattern) plus Muse `model_info` entries — updated here with empirical protocol verification from live `api.meta.ai/v1` testing — would support Meta's models cleanly without LiteLLM indirection or manual `client_args` plumbing.

## SDK Language

Python (with `shared/model-info.json` parity for TypeScript)

## Problem Statement

Today in `strands-agents/harness-sdk`:

1. `strands.models.llamaapi.LlamaAPIModel` is explicitly `@deprecated` (targets Meta's retired legacy Llama API via `llama_api_client`, slated for removal in `strands-agents v2.0.0`).
2. Meta's current developer platform — the **Meta Model API** (`https://api.meta.ai/v1`, serving `muse-wonder-1.0`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, and `muse-ember-1.0`) — has **no** provider entry in `strands_harness/models.py` (`_PROVIDERS`) and **zero** `muse-*` entries in `shared/model-info.json`.
3. Callers cannot cleanly work around this via `ANTHROPIC_BASE_URL` alone: Meta's `/v1/messages` endpoint is a secondary stateless wire translator (accepting both `x-api-key` and `Authorization: Bearer` in live testing, while stripping Anthropic-only beta headers and colliding with Anthropic env configuration), whereas Meta's recommended native agentic protocol is **`POST /v1/responses`** (OpenAI Responses API compatible, supporting multi-step tool loops, native web search, automatic prefix caching, multimodal image inputs, and encrypted reasoning replay).

## Proposed Solution

1. **Add a `"meta"` provider in `strands-harness` (`meta/<model>`):**
   - Route `meta/<model>` (e.g., `meta/muse-spark-1.3`, `meta/muse-spark-1.3-contributor`, `meta/muse-wonder-1.0`, `meta/muse-ember-1.0`) through `strands.models.openai_responses.OpenAIResponsesModel` pointed at `https://api.meta.ai/v1` (overridable via `META_BASE_URL`) and authenticated with `MODEL_API_KEY` (with optional `META_API_KEY` fallback) — reusing the existing `openai` SDK with zero new third-party dependencies (matching `bedrock-mantle`'s pattern in `harness-py/src/strands_harness/models.py`).
   - Map `effort` (`minimal | low | medium | high | xhigh | max`) onto `reasoning={"effort": ...}`, and **omit `params["reasoning"]` on `"none"` / `"off"`** (live `api.meta.ai/v1` rejects `"none"` with HTTP 400).
   - Enable native `web_search` (`tools=[{"type": "web_search"}]`) and select `_WEB_FETCH_MODELS["meta"] = "muse-ember-1.0"`.
   - Instantiate `CacheConfig()` **without** `strategy="auto"` (avoiding `warn_on_cache_config_not_supported` when `promptCaching="auto"` — Meta uses automatic server-side prefix caching with `prompt_cache_key` and rejects `prompt_cache_options` with HTTP 400).

2. **Add Muse models to `shared/model-info.json`:**
   - Add `muse-wonder-1.0`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-spark-1.2`, `muse-spark-1.2-contributor`, `muse-spark-1.1`, and `muse-ember-1.0` (`contextWindow: 1048576`, `promptCaching: "auto"` — never `"cache_points"`/`"cachePoints"`).

3. **Note critical synergy with `#3389` (encrypted reasoning replay on `OpenAIResponsesModel`):**
   - Meta's `/v1/responses` supports stateless encrypted reasoning replay (`store=False`, `include=["reasoning.encrypted_content"]`); omitting encrypted reasoning items across turns degrades chain-of-thought continuity and invalidates prefix caches (especially impactful given Meta's 50× cached input pricing on contributor tiers). Resolving `#3389` directly unlocks first-class multi-turn performance for Meta Model API as well.

## Empirical Verification (`https://api.meta.ai/v1`, verified 2026-11-24)

Tested live using `MODEL_API_KEY`, `openai.OpenAI`, and `strands.models.openai_responses.OpenAIResponsesModel`:

- **Prompt caching & inclusive token counters:**
  - `prompt_cache_key` and `prompt_cache_retention="24h"` both return `HTTP 200` and achieve automatic prefix caching (`2545 / 2657 = 95.8%` cached tokens on turn 2; `input_tokens` is inclusive so `input_tokens + output_tokens == total_tokens`). Verified end-to-end with `OpenAIResponsesModel` + `Agent` tool loop (`inputTokens=1250, outputTokens=129, totalTokens=1379, cacheReadInputTokens=226`).
  - **`prompt_cache_options={"ttl": "30m"}` fails with `HTTP 400 invalid_request_error: unknown parameter 'prompt_cache_options'`**, confirming `"promptCaching": "auto"` + `CacheConfig()` without `strategy="auto"`.
- **Reasoning effort matrix:** Across `muse-wonder-1.0`, `muse-spark-1.3-contributor`, and `muse-ember-1.0`, supported levels are `["minimal", "low", "medium", "high", "xhigh", "max"]`, whereas `reasoning={"effort": "none"}` fails with `HTTP 400` (`reasoning_effort 'none' is not supported...`).
- **Multimodal vision & native `web_search`:** Base64 PNG `input_image` succeeded across all three families (`muse-ember-1.0`, `muse-wonder-1.0`, `muse-spark-1.3-contributor`), so `_supports_media` stays `True`; `tools=[{"type": "web_search"}]` executed server-side `web_search_call` responses cleanly.
- **`GET /v1/models` catalog:** Returns 7 chat/reasoning models (`muse-wonder-1.0`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-spark-1.2`, `muse-spark-1.2-contributor`, `muse-spark-1.1`, `muse-ember-1.0`) alongside 3 non-chat assets (`muse-image-1.0`, `muse-voice-transcribe-1.0`, `sam-3.1`) — note `muse-image-1.0` shares the `muse-` prefix.
- **Encrypted reasoning replay:** `store=False` + `include=["reasoning.encrypted_content"]` returned a `1,426`-byte `encrypted_content` reasoning item on Turn 1 and replayed it cleanly on Turn 2.

## Use Case

Coding agents and high-context agentic CLIs (such as `CsabaConsulting/strands-code`) running Muse Wonder, Muse Spark (including contributor tiers), and Muse Ember natively via `resolve_model("meta/muse-spark-1.3-contributor", ...)` without LiteLLM indirection or manual `OpenAIResponsesModel(client_args=...)` boilerplate. Downstream `strands-code` currently ships a thin auto-retiring adapter checking `"meta" in _PROVIDERS` so it yields automatically once native `"meta"` support lands in `strands-harness`.

## Alternatives Solutions

- **Manual `OpenAIResponsesModel(client_args={"base_url": "https://api.meta.ai/v1", "api_key": ...})` per consumer:** Works for single invocations, but loses `provider/model` Harness ergonomics (`effort`, `web_fetch` small-model routing, `supports_thinking`, and `shared/model-info.json` context windows).
- **Pointing `AnthropicModel` / `ANTHROPIC_BASE_URL` at Meta's `/v1/messages`:** Uses a secondary stateless wire translator rather than Meta's native `/v1/responses` endpoint, strips Anthropic-specific beta headers, and collides with `ANTHROPIC_BASE_URL` configuration.
- **`litellm/meta/...`:** Adds a heavy optional dependency and goes through Chat Completions indirection rather than Meta's recommended Responses API.

## Additional Context

<details>
<summary>References in harness-sdk and downstream</summary>

- `LlamaAPIModel` deprecation notice: `strands-py` `src/strands/models/llamaapi.py` (scheduled for removal in v2.0.0).
- Existing `OpenAIResponsesModel`-backed custom-endpoint pattern in Harness: `_bedrock_mantle()` and `_PROVIDERS` in `harness-py/src/strands_harness/models.py`.
- OpenAI Responses verbatim output / encrypted reasoning item replay tracking: #3389.
- Downstream issue & live-verified Muse Spark/Ember integration: `CsabaConsulting/strands-code#21`.

</details>
```
