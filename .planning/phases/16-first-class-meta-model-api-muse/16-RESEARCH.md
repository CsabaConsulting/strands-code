# Phase 16: First-Class Meta Model API (`api.meta.ai` / Muse) & Upstream Enablement — Research

**Researched:** 2026-11-24
**Phase:** `16-first-class-meta-model-api-muse`
**Requirements:** `MODEL-09` (`CsabaConsulting/strands-code#21`, `strands-agents/harness-sdk#6521`) + folded upstream resync (`strands-agents>=1.66.0` / `strands-harness>=0.5.0`)
**Sources Verified Live:** `https://api.meta.ai/v1` (live probe with `MODEL_API_KEY` from `.env`), GitHub releases `python/v1.66.0` & `harness-python/v0.5.0`, bundled `litellm.model_cost`, installed `strands-agents==1.65.0` / `strands-harness==0.4.0`, and `radon` complexity scan (`a64f83c`).

---

## 1. Live Empirical Protocol Probe of `https://api.meta.ai/v1` (2026-11-24)

Probed directly via `openai.OpenAI(api_key=..., base_url="https://api.meta.ai/v1")`, `urllib.request`, and `strands.Agent` + `OpenAIResponsesModel`:

### 1.1 `GET /v1/models` Catalog & Filtering
Returned 10 models (`owned_by="meta"`, `extra_keys=[]`):
- **Chat / Responses reasoning models (7):**
  - `muse-spark-1.3-contributor`, `muse-spark-1.3`, `muse-spark-1.2-contributor`, `muse-spark-1.2`, `muse-spark-1.1`, `muse-wonder-1.0`, `muse-ember-1.0`
- **Non-chat models (3):**
  - `muse-image-1.0` (image generation — notice it shares the `muse-` prefix!)
  - `muse-voice-transcribe-1.0` (audio transcription)
  - `sam-3.1` (Segment Anything)
- **Implication for `discover_models()`:** Filtering solely on `muse-` is insufficient because `muse-image-1.0` would slip through. `_is_meta_chat_model(model_id)` MUST exclude `_META_NON_CHAT_TOKENS = ("image", "voice", "transcribe", "audio", "sam-", "embed", "tts", "video", "moderation")` and require `lowered.startswith("muse-")`.

### 1.2 Reasoning Effort Matrix (`POST /v1/responses`)
Tested `reasoning={"effort": eff}` across all three families (`muse-spark-1.3-contributor`, `muse-ember-1.0`, `muse-wonder-1.0`):
- **Supported values:** `["minimal", "low", "medium", "high", "xhigh", "max"]` (HTTP 200 across all three models).
- **Default (`effort=None`):** Returns HTTP 200 with server reasoning active (`out_types=['reasoning', ...]`).
- **`effort="none"`:** **HTTP 400 `BadRequestError` on all three models!** Exact server message:
  `reasoning_effort 'none' is not supported for model '...'. Supported values: [minimal, low, medium, high, xhigh, max]`
- **Implication for `meta/` adapter:** Map `effort=None|"auto"` → `"high"`, accept `minimal|low|medium|high|xhigh|max` verbatim, and **omit** `params["reasoning"]` completely when `effort in ("none", "off")` (matching `_normalize_meta_effort()`).

### 1.3 Prompt Caching Parameters & Inclusive Usage Semantics
- **`prompt_cache_key`:** HTTP 200; verified live 2-turn prefix reuse:
  - Turn 1: `usage={'input_tokens': 2657, 'input_tokens_details': {'cache_write_tokens': None, 'cached_tokens': 0}, 'output_tokens': 64, 'total_tokens': 2721}`
  - Turn 2: `usage={'input_tokens': 2657, 'input_tokens_details': {'cache_write_tokens': None, 'cached_tokens': 2545}, 'output_tokens': 64, 'total_tokens': 2721}` (**95.8% cached!**)
- **`prompt_cache_retention="24h"`:** HTTP 200 (same 95.8% cache hit).
- **`prompt_cache_options={"ttl": "30m"}`:** **HTTP 400 `BadRequestError`**: `unknown parameter 'prompt_cache_options'`.
- **`strands/models/_openai_cache.py` interaction:**
  - `OpenAIResponsesModel` emits `prompt_cache_options` whenever `model_info.capabilities.prompt_caching == "cache_points"` AND `cache_config.ttl in {"30m", "12h"}`. Setting `ModelInfo(capabilities=ModelCapabilities(prompt_caching="auto"), ...)` prevents `prompt_cache_options` AND skips per-message `cache_control` breakpoints cleanly.
  - Note `strands/models/_validation.py` via `_openai_cache.py:96`: if `CacheConfig(strategy="auto")` is passed while `supports_message_caching=False`, `warn_on_cache_config_not_supported` emits a `UserWarning` about `strategy`! Passing plain `CacheConfig()` sets `prompt_cache_key="strands-<session_id>"` cleanly with **zero warnings** and **zero `prompt_cache_options`**.
- **Usage inclusivity:**
  - Raw probe: `input_tokens (2657) + output_tokens (64) == total_tokens (2721)` even with `cached_tokens=2545` — **inclusive**.
  - Strands SDK `OpenAIResponsesModel` + `Agent` tool loop: `usage={'inputTokens': 1250, 'outputTokens': 129, 'totalTokens': 1379, 'cacheReadInputTokens': 226}` (`1250 + 129 == 1379`).
  - Matches `strands_code_cli/loop/core.py:_is_exclusive_usage_provider("meta/...") == False` and `_extract_prompt_usage()`'s `raw_in + raw_out == total_tok` check out of the box!

### 1.4 Native `web_search`, Multimodal Vision, Encrypted Replay & `/v1/messages`
- **Native `web_search`:** `tools=[{"type": "web_search"}]` returned `status=completed`, `out_types=['reasoning', 'message', 'web_search_call', 'reasoning', 'message']`, answering live queries (`https://www.python.org`).
- **Multimodal Vision (`input_image` base64 PNG):** Accepted on **all three** families — `muse-ember-1.0` (`'Red'`), `muse-wonder-1.0` (`'Red'`), and `muse-spark-1.3-contributor` (HTTP 200).
  - **Implication for `_MEDIA_LESS` (`model_switch.py:59`):** Remove wildcard `(None, "meta", None, None)` and keep Bedrock-scoped Llama rows `("bedrock", "meta", "llama3", None)` & `("bedrock", "meta", "llama4", None)` (alongside existing `(None, None, None, "llama")`), preserving existing tests `meta.llama3-70b-instruct-v1:0` and `litellm/openrouter/meta/llama-x` while allowing all Muse models (`meta/muse-*`) to pass `supports_media(...) == True`.
- **Stateless Encrypted Reasoning Replay (`store=False, include=["reasoning.encrypted_content"]`):**
  - Works natively on `api.meta.ai/v1`: Turn 1 returned `('reasoning', True, 1426)` + `('message', False, 0)` (`391`), and Turn 2 replayed it cleanly (`392`).
  - `strands.models.openai_responses.OpenAIResponsesModel` (tracked in `#3389`) does not yet request `include=["reasoning.encrypted_content"]` or store opaque encrypted reasoning blocks in `agent.messages` (storing only `text`/`toolUse`/`toolResult`), confirming:
    1. `supports_reasoning("meta/...")` MUST remain `False` so switches from `anthropic/`/`bedrock/`/`google/` → `meta/` convert signed thinking to `TRACE_LABEL` text and stash raw blocks in `RichHistory`.
    2. Upstream `#3389` remains high-value for Meta contributor tiers (50× cached discount).
- **`POST /v1/messages` Auth Nuance:**
  - Tested both `x-api-key: $MODEL_API_KEY` and `Authorization: Bearer $MODEL_API_KEY` on `https://api.meta.ai/v1/messages`: **both returned HTTP 200** (`usage={'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0, 'input_tokens': 12, 'output_tokens': 32, 'output_tokens_details': {'thinking_tokens': 30}}`).
  - Record this nuanced correction candidly in `docs/upstream/harness_comment_6521_meta_probe.md` (whereas `/v1/responses` remains Meta's recommended native agentic protocol with zero `OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL` env collisions).

---

## 2. Upstream `strands-agents 1.66.0` & `strands-harness 0.5.0` Delta (`D-05`)

Checked official release notes (`python/v1.66.0` at `2026-11-23T17:42:10Z` and `harness-python/v0.5.0` at `2026-11-23T17:42:32Z`):
- **Relevant fixes & features landing in `1.66.0` / `0.5.0`:**
  - `#6265`: Adds `gpt-6.2-sol` and `gpt-6.2-astra` to `shared/model-info.json` → cleanly **retires** `_gpt_62_model_info_fallback()` in `model_switch.py`!
  - `#6396`: Moves GPT-6.2 system prompt to leading `developer` message on Responses API so prompt caching works → unblocks bumping OpenAI ambient default (`_AMBIENT_DEFAULT_MODELS["openai"]`) from `openai/gpt-6.1-sol` to **`openai/gpt-6.2-sol`**!
  - `#6284`: Haiku 5.5 injected text sent as plain text (`InjectedBlock` compatibility check needed during Wave 1 test verification).
  - `#5698`: Anthropic `max_tokens` now defaults from `model_info.limits.max_output_tokens` and **raises when `model_info` has none** — watch tests constructing custom/synthetic `anthropic/<custom>` IDs without `max_tokens`!
  - `#4683`: Bedrock Anthropic client default bumped to Claude Opus 5.5 (`DEFAULT_MODEL` / client defaults).
  - `#5997`: Harness `web_search` on Bedrock uses AgentCore `InvokeWebSearch` (`supports_web_search` / `create_harness` checks).
  - `#6291`: OpenAI Chat Completions tools support for GPT-5.6 / GPT-6.
  - `#6421`, `#6364`, `#6112`: Bedrock stops defaulting to EOL Llama 3.2; Gemini 4 Neon & Hydrogen context windows added.
  - `#6254`, `#6255`: `O_NOFOLLOW` session reads; skip tool start when cancel arrives during `BeforeToolCall` hooks (`test_steering.py` verification check!).
- **Provider check in current `strands-harness`:** `_PROVIDERS` contains `['anthropic', 'bedrock', 'bedrock-mantle', 'google', 'litellm', 'ollama', 'openai']` — **no `"meta"` yet**. Therefore `build_meta_model()` MUST check `"meta" in strands_harness.models._PROVIDERS` dynamically (`upstream_supports_meta()`) so `strands-code`'s thin adapter automatically retires once upstream adds `"meta"`.

---

## 3. Extension Seams, Pricing & Guardrails

### 3.1 Cleanest Thin Retireable `meta/` Adapter Architecture
- **Pre-built `Model` trap avoided cleanly:** Passing `kwargs["caching"] = False` alongside a pre-built Meta `OpenAIResponsesModel` in `entry/main.py:build_agent()` prevents `create_harness()` from logging `"prompt caching not applied to a pre-built Model instance"` (`strands_harness/models.py:568`), while `CacheConfig()`, `params={"reasoning": ...}`, `params={"tools": [{"type": "web_search"}]}`, and `model_info=ModelInfo(...)` are already configured cleanly on the instance AND `resolve_web_fetch_model` reuses the main Meta instance without probing OpenAI/Anthropic.
- **`model_id_of()` fidelity (`model_switch.py:946`):** Setting `model._strands_model_ref = f"meta/{tail}"` on the constructed `OpenAIResponsesModel` and reading `getattr(model, "_strands_model_ref", None)` first in `model_id_of()` ensures `_provider_of()`, `scoped_base_url()`, `/btw` `build_btw_agent()`, `/cost`, and `/context` always see `"meta/<tail>"` rather than bare `"muse-..."` (which bare-ID rules would otherwise classify as `"bedrock"`!).
- **Uniform wiring across all 4 lifecycle seams:**
  1. **Startup:** `entry/main.py:model_for_config(model, base_url, api_mode)` calls `build_meta_model(model, base_url=base_url)` when `_provider_of(model) == "meta"` and `not upstream_supports_meta()`. `build_agent()` sets `caching=False` when `getattr(model, "_strands_model_ref", None)` is set (no unknown kwargs forwarded).
  2. **`/model` validation (`dispatch/core.py:_model_message`):** Calls `resolve_harness_model(selection, DEFAULT_MODEL)` — or validates `"meta"` prefix via `build_meta_model` — catching `ImportError` to surface `pip install strands-code-agent[meta]` via `_SDK_EXTRA_HINTS["meta"] = "meta"`. *(Note: existing unit tests patch `strands_harness.models.resolve_model` on `dispatch.core` / `model_switch`; routing only `meta/` when `not upstream_supports_meta()` through `build_meta_model` preserves 100% compatibility with existing `resolve_model` mocks!)*
  3. **`/model` & `/route` swaps (`model_switch.py:resolve_harness_model`):** Checks `if _provider_of(normalized) == "meta" and not upstream_supports_meta(): return build_meta_model(normalized, effort=effort, base_url=base_url)`.
  4. **`/btw` forks (`loop/btw.py:build_btw_agent`):** Replays `parent_kwargs["model"]` (preserving `_strands_model_ref`), refreshes base URL safely via `configure_base_url_for_model()`, and respects `scoped_base_url()`.

### 3.2 `litellm_entry`, Static Pricing & Credential Scrubbing
- **Bundled `litellm.model_cost` verified (`a64f83c`):**
  - `meta/muse-wonder-1.0`: `in=$4.00`, `cache_read=$0.20` (20× discount), `out=$20.00`, `max_input_tokens=1_048_576`, `max_output_tokens=131_072`
  - `meta/muse-spark-1.3`: `in=$1.25`, `cache_read=$0.15`, `out=$4.25`, `max_input_tokens=1_048_576`, `max_output_tokens=131_072`
  - `meta/muse-spark-1.3-contributor`: `in=$0.10`, `cache_read=$0.002` (**50× discount**), `out=$0.20`, `max_input_tokens=1_048_576`, `max_output_tokens=131_072`
  - `meta/muse-spark-1.2`, `meta/muse-spark-1.2-contributor`: same rates, `1_048_576` window
  - Missing in LiteLLM: `meta/muse-ember-1.0` (`\$0.10` / `\$0.004` cached / `\$0.50` `<200K`; `\$0.30` / `\$0.012` / `\$1.50` `>200K`, `1_048_576` window).
- **`live_pricing._litellm_keys()`:** Add `elif lowered.startswith("meta/"): keys = [model_id, tail]` so `"meta/muse-spark-1.3-contributor"` hits LiteLLM immediately without prepending `bedrock/`.
- **Complexity guard on `cost_context.py`:** `price_table` is at `C (20)` — do **NOT** modify `price_table()`. Only update module dicts (`MODEL_PRICING`, `MODEL_LIMITS`) and small helpers (`_default_cache_rates`, `_CRED_PATTERNS`).
- **Meta API key scrubbing (`scrub_credentials()`):** Public Meta docs show keys formatted `LLM_<digits>_<secret>` (or `LLM|<digits>|<secret>`). Extending `_CRED_PATTERNS` (`cost_context.py:815-820`) with `re.compile(r"LLM[_|]\d+[_|][A-Za-z0-9\-_]{12,}")` and adding `|` to `Bearer` (`[A-Za-z0-9\-._~+/|]+=*`) redacts Meta tokens on compaction without ever introducing prefix checks into `first_run.py`!

### 3.3 Complexity & Security Baseline (`radon cc -s -n C`)
- Highest functions across Phase 16 files:
  - `cost_context.price_table`: `C (20)` *(untouched)*
  - `loop/core.run_loop`: `C (18)` *(untouched)*
  - `loop/core._route_side_spawn`: `C (17)` *(already delegates to `resolve_harness_model`!)*
  - `model_switch.configure_base_url_for_model`: `C (15)` *(keep `<= C 17` or add helper)*
  - `first_run._check_explicit_provider`: `C (14)` *(keep `<= C 14`: `_PROVIDER_ENV_KEYS["meta"]` reuses existing `in _PROVIDER_ENV_KEYS` branch!)*
- Strictly keep ALL `os.environ` reads (`MODEL_API_KEY`, `META_API_KEY`, `META_BASE_URL`) inside `strands_code_cli/entry/first_run.py` (`test_no_credential_persistence_sinks`).
