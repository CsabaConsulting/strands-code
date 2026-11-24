# Upstream Comment Draft (`harness-sdk#6521` Empirical Probe Findings)

> **HOLD BEFORE POSTING:** Review and approve the comment below before running `gh issue comment 6521 -R strands-agents/harness-sdk`.

# Target Issue

https://github.com/strands-agents/harness-sdk/issues/6521

---

## Draft Comment for `strands-agents/harness-sdk#6521`

- **Policy note:** Includes explicit AI-assistance disclosure and concise, verified engineering measurements per `team/AI_USAGE_POLICY.md`.

```markdown
*(Disclosure: drafted with AI assistance and reviewed/edited by me; see `team/AI_USAGE_POLICY.md`.)*

Follow-up with empirical probe results from running `OpenAIResponsesModel` directly against live `https://api.meta.ai/v1` (verified 2026-11-24 with `MODEL_API_KEY`):

### 1. Caching behavior (`CacheConfig` / `model-info.json`)
- **Works:** `prompt_cache_key` and `prompt_cache_retention="24h"` both return HTTP 200 and trigger automatic prefix caching (`2545 / 2657 = 95.8%` cached tokens on turn 2; `input_tokens` is inclusive so `input_tokens + output_tokens == total_tokens`).
- **Rejects `prompt_cache_options`:** Sending `prompt_cache_options={"ttl": "30m"}` fails with `HTTP 400 invalid_request_error: unknown parameter 'prompt_cache_options'`.
- **Implementation impact:** In `shared/model-info.json`, Meta Muse entries should set `"promptCaching": "auto"` (not `"cachePoints"`/`"cache_points"`), and `_meta()` should instantiate `CacheConfig()` without `strategy="auto"` (avoiding `warn_on_cache_config_not_supported` when `supports_message_caching=False`).

### 2. Reasoning effort matrix (`POST /v1/responses`)
Tested across all three families (`muse-wonder-1.0`, `muse-spark-1.3-contributor`, `muse-ember-1.0`):
- **Supported:** `["minimal", "low", "medium", "high", "xhigh", "max"]` (default when `reasoning` is omitted runs server reasoning).
- **Rejected:** `reasoning={"effort": "none"}` returns `HTTP 400: reasoning_effort 'none' is not supported for model '...'. Supported values: [minimal, low, medium, high, xhigh, max]`.
- **Implementation impact:** `_meta()` should omit `params["reasoning"]` whenever `effort` resolves to `"none"` / `"off"`.

### 3. `GET /v1/models` catalog & non-chat filtering
`GET https://api.meta.ai/v1/models` returns non-chat assets sharing the `muse-` prefix alongside chat models:
- Chat/reasoning (`7`): `muse-wonder-1.0`, `muse-spark-1.3`, `muse-spark-1.3-contributor`, `muse-spark-1.2`, `muse-spark-1.2-contributor`, `muse-spark-1.1`, `muse-ember-1.0`
- Non-chat (`3`): `muse-image-1.0`, `muse-voice-transcribe-1.0`, `sam-3.1`

### 4. Multimodal vision, `web_search`, encrypted replay & `/v1/messages` correction
- **Multimodal vision (`input_image`):** Base64 PNG input succeeded on all three families (`muse-ember-1.0`, `muse-wonder-1.0`, and `muse-spark-1.3-contributor`), so `_supports_media` should stay `True` across Muse.
- **Native `web_search`:** `tools=[{"type": "web_search"}]` executed server-side `web_search_call` responses cleanly.
- **Encrypted reasoning replay (`#3389`):** `store=False` + `include=["reasoning.encrypted_content"]` returned a `1,426`-byte `encrypted_content` reasoning item on Turn 1 and replayed it cleanly on Turn 2, reinforcing `#3389`'s importance for Muse contributor tiers (50× cached discount).
- **Correction to original `/v1/messages` note above:** Live probing showed `POST https://api.meta.ai/v1/messages` in fact accepted both `x-api-key` and `Authorization: Bearer` headers (`HTTP 200`); however `/v1/responses` remains Meta's recommended native agentic protocol and cleanly avoids `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` env collisions.

Downstream `strands-code` now ships a thin auto-retiring `meta/` adapter checking `"meta" in _PROVIDERS` so it yields automatically once native `"meta"` support lands in `strands-harness`.
```
