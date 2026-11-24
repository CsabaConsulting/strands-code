# Filed URL

https://github.com/strands-agents/harness-sdk/issues/6521

---

## Human Overview

`LlamaAPIModel` targets Meta's retired legacy Llama API and is slated for removal in v2.0, leaving no built-in Harness provider or `model_info.json` metadata for Meta's current Meta Model API (`https://api.meta.ai/v1`, serving Muse Wonder, Muse Spark, and Muse Ember). Since Meta recommends `/v1/responses` natively for agentic loops, adding a `meta/<model>` provider built on `OpenAIResponsesModel` (matching `bedrock-mantle`'s pattern) plus Muse `model_info` entries would support Meta's models cleanly without LiteLLM indirection or manual `client_args` plumbing.

## SDK Language

Python (with `shared/model-info.json` parity for TypeScript)

## Problem Statement

Today in `strands-agents/harness-sdk`:

1. `strands.models.llamaapi.LlamaAPIModel` is explicitly `@deprecated` (targets Meta's retired legacy Llama API via `llama_api_client`, slated for removal in `strands-agents v2.0.0`).
2. Meta's current developer platform — the **Meta Model API** (`https://api.meta.ai/v1`, serving `muse-wonder-1.0`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-ember-1.0`) — has **no** provider entry in `strands_harness/models.py` (`_PROVIDERS`) and **zero** `muse-*` entries in `shared/model-info.json`.
3. Callers cannot cleanly work around this via `ANTHROPIC_BASE_URL` alone: Meta's `/v1/messages` endpoint is a stateless wire translator that expects `Authorization: Bearer $MODEL_API_KEY` (not Anthropic's `x-api-key`) and strips Anthropic-only beta headers, whereas Meta's recommended native agentic protocol is **`POST /v1/responses`** (OpenAI Responses API compatible, supporting multi-step tool loops, search grounding, automatic prefix caching, and encrypted reasoning replay).

## Proposed Solution

1. **Add a `"meta"` provider in `strands-harness` (`meta/<model>`):**
   - Route `meta/<model>` (e.g., `meta/muse-spark-1.3`, `meta/muse-spark-1.3-contributor`, `meta/muse-wonder-1.0`, `meta/muse-ember-1.0`) through `strands.models.openai_responses.OpenAIResponsesModel` pointed at `https://api.meta.ai/v1` (overridable via `META_BASE_URL`) and authenticated with `MODEL_API_KEY` — reusing the existing `openai` SDK with zero new third-party dependencies (the same pattern `bedrock-mantle` already uses in `harness-py/src/strands_harness/models.py`).
   - Map `effort` onto `reasoning={"effort": ...}`, evaluate `_WEB_FETCH_MODELS["meta"]` (e.g., `muse-ember-1.0` or `muse-spark-1.3`), and verify automatic server-side caching (`caching=True` — confirming during implementation whether Meta accepts `prompt_cache_key` / `prompt_cache_options` or expects automatic prefix caching without OpenAI-specific fields, like `_gemini()`).

2. **Add Muse models to `shared/model-info.json`:**
   - Add `muse-wonder-1.0`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-spark-1.2`, `muse-spark-1.2-contributor`, `muse-spark-1.1`, and `muse-ember-1.0` (`contextWindow: 1048576`, `promptCaching: "auto"`, and appropriate output/capability metadata) so `Model.model_info.limits.context_window` and Harness effort/caching checks resolve automatically in both Python and TypeScript.

3. **Note critical synergy with `#3389` (encrypted reasoning replay on `OpenAIResponsesModel`):**
   - Meta's `/v1/responses` uses stateless encrypted reasoning replay when keeping multi-turn history client-side; omitting encrypted reasoning items across turns degrades chain-of-thought continuity and invalidates prefix caches (which is especially impactful given Meta's 50× cached input pricing on contributor tiers). Resolving `#3389` directly unlocks first-class multi-turn performance for Meta Model API as well.

## Use Case

Coding agents and high-context agentic CLIs (such as `CsabaConsulting/strands-code`) running Muse Wonder, Muse Spark (including contributor tiers), and Muse Ember natively via `resolve_model("meta/muse-spark-1.3", ...)` without LiteLLM indirection or manual `OpenAIResponsesModel(client_args=...)` boilerplate.

## Alternatives Solutions

- **Manual `OpenAIResponsesModel(client_args={"base_url": "https://api.meta.ai/v1", "api_key": ...})` per consumer:** Works for single invocations, but loses `provider/model` Harness ergonomics (`effort`, `web_fetch` small-model routing, `supports_thinking`, and `shared/model-info.json` context windows).
- **Pointing `AnthropicModel` / `ANTHROPIC_BASE_URL` at Meta's `/v1/messages`:** Uses a secondary stateless wire translator rather than Meta's native `/v1/responses` endpoint, runs into `Authorization: Bearer` vs `x-api-key` header mismatches, and drops Anthropic-specific beta headers.
- **`litellm/meta/...`:** Adds a heavy optional dependency and goes through Chat Completions indirection rather than Meta's recommended Responses API.

## Additional Context

<details>
<summary>References in harness-sdk and downstream</summary>

- `LlamaAPIModel` deprecation notice: `strands-py` `src/strands/models/llamaapi.py` (scheduled for removal in v2.0.0).
- Existing `OpenAIResponsesModel`-backed custom-endpoint pattern in Harness: `_bedrock_mantle()` and `_PROVIDERS` in `harness-py/src/strands_harness/models.py`.
- OpenAI Responses verbatim output / encrypted reasoning item replay tracking: #3389.
- Downstream issue & real-world Muse Spark coding build retrospective: `CsabaConsulting/strands-code#21`.

</details>
