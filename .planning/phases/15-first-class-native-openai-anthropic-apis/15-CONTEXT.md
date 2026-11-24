# Phase 15: First-Class Native OpenAI & Anthropic APIs - Context

**Gathered:** 2026-11-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Make native `openai/` (Responses API) and `anthropic/` (Messages API) first-class across packaging, startup, `/model`, caching, `/cost` & context accounting, provider mannerisms, and live verification without leaking choices or credentials to other providers (`MODEL-07`, `MODEL-08`, tracking `CsabaConsulting/strands-code#17` and `CsabaConsulting/strands-code#22`):
- Optional `openai` (`strands-agents[openai]`, `openai>=2.0.0`) and `anthropic` (`strands-agents[anthropic]`) extras in `pyproject.toml`, plus `_SDK_EXTRA_HINTS["openai"] = "openai"` and `_SDK_EXTRA_HINTS["anthropic"] = "anthropic"`.
- Preserving `caching=True` and native `web_search` when resolving models during `/model` switches (`apply_switch`) and `/route` pre-turn routing.
- Cache-aware `/cost` and post-turn context `%` accounting across Anthropic (exclusive `input_tokens`) and OpenAI (inclusive `input_tokens`) with a compact cache suffix when cache tokens > 0, plus `litellm_entry` bare-tail lookup and updated static pricing/limit fallbacks.
- Harness-preserving custom `base_url` configuration (passing strings through `create_harness` so `effort`/`CacheConfig`/`web_search` stay active, post-applying `base_url` to `OpenAIResponsesModel`/`AnthropicModel`, and optional `api_mode: chat` in `config.yaml` only for legacy Chat-Completions proxies).
- Fail-safe cross-provider thinking-signature gating (`anthropic/` ↔ `bedrock/anthropic.*` converts signed `reasoningContent` to `TRACE_LABEL` text while stashing raw blocks in `RichHistory` for switch-back) and safe `SummaryBlock` (`compact-2026-09-04`) / `temporary_messages` handling across model switches.
- Credential-gated live `/model` discovery (`openai.OpenAI().models.list()`, `anthropic.Anthropic().models.list()`), 24h Anthropic metadata cache (`max_input_tokens`, `max_tokens`, `capabilities`, `retires_at`) feeding `window_for()` and `/model`, curated offline fallbacks when keyed, and `_vendor_family()` grouping for `claude-*`, `gpt-*`, and `o1`/`o3`/`o4-*`.
- Updated ambient auto-pick defaults (`anthropic/claude-sonnet-5-5`, `openai/gpt-6.1-sol`), fail-soft `configure_openai_for_model()` guard for non-reasoning / effort-subset OpenAI models (+ upstream issue draft if confirmed), repeatable `driver.py` OpenAI (`o1`) and Anthropic (`a1`) UAT scenarios, and `docs/QUICKSTART.md` native OpenAI & Anthropic setup sections.

Out of scope: Meta Model API (`api.meta.ai` / Muse — **Phase 16**, `MODEL-09`), `DecisionModel` routing convergence (**Phase 17**, `UPSTREAM-02`), remote skills marketplaces (**Phase 18**, `SKILL-03`), Strands Box `box.toml`/`policy.dw` generator (**Phase 19**, `SANDBOX-01`), `/help`/`@file`/`/review` (**Phase 20**, `LOOP-06`/`TOOL-05`/`REVIEW-01`), `strands-agents-evals` (**Phase 21**, `EVAL-01`), and Admin-key-only organization billing APIs (`GET /v1/organization/costs`, `GET /v1/organizations/analytics/cost`).

</domain>

<decisions>
## Implementation Decisions

### Packaging & Install Hints
- **D-01 (`openai` & `anthropic` optional extras + `_SDK_EXTRA_HINTS`):** Add `openai = ["strands-agents[openai]", "openai>=2.0.0"]` (`OpenAIResponsesModel` enforces `openai>=2.0.0` at import time) and `anthropic = ["strands-agents[anthropic]"]` to `[project.optional-dependencies]` in `pyproject.toml` (zero upper pins during the experimental phase), and map `"openai": "openai"` and `"anthropic": "anthropic"` in `_SDK_EXTRA_HINTS` (`strands_code_cli/dispatch/core.py`) so missing SDKs surface `pip install strands-code-agent[openai]` / `[anthropic]` instead of the generic fallback pointer. — *Reversibility: easy — additive extras and two dict entries.*

### Switch & Route Feature Preservation
- **D-02 (Preserve `caching` & native `web_search` on `/model` and `/route` switches):** Forward `caching=True` (`caching_explicit=False`, so non-caching providers like `ollama` continue failing soft with a warning rather than raising) and native `web_search=supports_web_search(...)` in both `apply_switch()` (`strands_code_cli/model/model_switch.py:948-956`) and pre-turn routing (`strands_code_cli/loop/core.py:509`), matching `create_harness()`'s `DEFAULT_CACHING` + native search behavior so switches never silently drop prompt caching or built-in web search. — *Reversibility: easy — parameter forwarding at existing `resolve_model` call sites.*

### Cache-Aware `/cost` & Usage Display
- **D-03 (Cache-aware accounting with compact cache suffix):**
  - Extract `cacheReadInputTokens` and `cacheWriteInputTokens` directly from `response.metrics.get_summary()["accumulated_usage"]` inside `record_turn_metrics()` (`strands_code_cli/loop/core.py`), keeping `strands_code_agent/utils.py` byte-pristine (`D-24`).
  - Handle provider input-token counting semantics accurately:
    - **Anthropic (`anthropic/`):** `inputTokens` **excludes** `cacheReadInputTokens` and `cacheWriteInputTokens`; total prompt tokens = `inputTokens + cacheReadInputTokens + cacheWriteInputTokens`; estimated cost = `inputTokens * in_rate + cache_read * read_rate + cache_write * write_rate + output * out_rate`.
    - **OpenAI (`openai/`, `bedrock-mantle/`):** `inputTokens` **includes** `cacheReadInputTokens` (and `cacheWriteInputTokens` where reported on GPT-5.6+); uncached input = `max(0, inputTokens - cache_read - cache_write)`; total prompt tokens = `inputTokens`; estimated cost applies discounted cache read/write rates. *(Verify Bedrock Converse cache-counter inclusivity during Phase 15 research so Bedrock rows remain accurate.)*
  - Render compact cache indicators **only when cache tokens > 0** (zero-cache turns remain byte-identical):
    - Post-turn usage line: `165.60K (17%, 75% cached) $0.14` (where `cached % = cache_read / total_prompt`).
    - `/cost` per-turn row: `in 165.60K (125.00K cached, 40.50K write), out 305, $0.1420` (omitting `write` when `0`; omitting the parenthetical completely when both `cache_read` and `cache_write` are `0`).
  - Extend `live_pricing.litellm_entry()` (`strands_code_cli/cost/live_pricing.py`) to check bare `tail` forms for `openai/` and `anthropic/` (since `litellm.model_cost` keys native models without provider prefixes) and return `cache_read` / `cache_write` per-1M rates alongside `in` / `out` / `window`; add static fallbacks in `MODEL_PRICING` and `MODEL_LIMITS` (plus cache rate tables/multipliers) for `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5-2` (1M), `gpt-5.4`, `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.6-sol`, `gpt-6-luna`, `gpt-6.1-terra`, `gpt-6.1-sol`, `gpt-6-astra`, `o3`, and `o4-mini`. — *Reversibility: easy — display-only accounting and lookup additions.*

### Custom `base_url` Handling (Harness-Preserving)
- **D-04 (Harness-first `base_url` post-application + opt-in `api_mode: chat`):**
  - Always pass `"openai/..."` and `"anthropic/..."` as **strings** into `create_harness(model=...)` so 100% of `strands-harness` features (`effort`, `CacheConfig`, native `web_search`, `max_tokens`, and `parent_config` for `/btw` side-agents) remain active — `strands_harness/models.py:555-569` treats pre-built `Model` instances as unknown providers and strips those defaults.
  - Native env vars (`OPENAI_BASE_URL`, `OPENAI_ORG_ID`, `OPENAI_PROJECT`, `ANTHROPIC_BASE_URL`) flow natively through `strands-harness` (including `resolve_web_fetch_model` custom-endpoint fallback).
  - When `ProviderConfig.base_url` is set in `config.yaml` on `openai/` or `anthropic/`:
    - Default (`api_mode` unset or `"responses"`): let `create_harness()` resolve the provider string first, then post-apply `base_url` onto the resolved model right after `create_harness` (same seam as `configure_streaming_for_model` / `configure_gemini_for_model` in `entry/main.py`): update `client_args["base_url"] = base_url` on `OpenAIResponsesModel`, rebind `AnthropicModel`'s `AsyncAnthropic(base_url=base_url)` client, and configure `builtin_tools={"web_fetch": {"model": effective_model}}` so `web_fetch` does not probe a vended summarizer on the custom proxy.
    - Opt-in `api_mode: chat` in `ProviderConfig` (`config.yaml`, validated as `"responses" | "chat"`), or `litellm/` with `base_url`: construct legacy Chat Completions `strands.models.openai.OpenAIModel(model_id=tail, client_args={"base_url": base_url})` — fixing the existing bug in `model_for_config()` that forwarded `"openai/..."` unstripped as `model_id`.
  — *Reversibility: moderate — touches `ProviderConfig`, `entry/main.py`, and post-build helpers.*

### Cross-Provider Thinking & Compaction Safety
- **D-05 (Same-provider thinking-signature gating & Anthropic `SummaryBlock` / `temporary_messages` safety):**
  - Require **same provider AND same vendor** when gating raw `reasoningContent` round-trips inside `convert_history()` so switching across `anthropic/claude-*` ↔ `bedrock/anthropic.claude-*` converts signed thinking blocks to `TRACE_LABEL` text while keeping raw blocks stashed in `RichHistory` for lossless switch-back to the original provider.
  - Handle Anthropic server-side compaction `SummaryBlock` (`{"summary": {"provider": "anthropic", ...}}` from `compact-2026-09-04`) across `convert_history()`, `canonical_prefix_hash()`, and `estimate_messages_tokens()`: keep verbatim on `anthropic/` targets, convert to labeled summary text (preserving raw blocks in `RichHistory`) on non-Anthropic targets so switches never crash downstream adapters.
  - Keep `InjectedBlock` / `temporary_messages` (`mid-conversation-system-clear-at-2026-08-21`) safety intact across model switches and `/btw` forks. — *Reversibility: easy — localized to `model_switch.py` and `cost_context.py`.*

### Live `/model` Discovery, Metadata Cache & Family Grouping
- **D-06 (Credential-gated OpenAI & Anthropic `/model` discovery, 24h Anthropic metadata cache & `_vendor_family` grouping):**
  - Keep all `os.environ` presence checks strictly inside `strands_code_cli/entry/first_run.py` (`has_openai_credentials()`, `has_anthropic_credentials()`, preserving `test_no_credential_persistence_sinks`).
  - OpenAI discovery (only when OpenAI credentials exist): lazily import `openai`, call `openai.OpenAI().models.list()`, filter strictly to Responses-capable chat models (excluding embeddings, Whisper/TTS/audio/transcribe/realtime, DALL-E/gpt-image, Sora, moderation, legacy completions), and emit `openai/<id>`, falling back to curated `CURATED_OPENAI_MODELS` when offline or SDK missing.
  - Anthropic discovery (only when Anthropic credentials exist): lazily import `anthropic`, call `anthropic.Anthropic().models.list()`, emit `anthropic/<id>`, and fall back to curated `CURATED_ANTHROPIC_MODELS` when offline or SDK missing. Cache Anthropic `/v1/models` metadata (`max_input_tokens`, `max_tokens`, `capabilities`, `line`, `retires_at`) for 24h in `~/.cache/strands-code/anthropic-models.json` (honoring `STRANDS_CODE_NO_LIVE_PRICING` and `STRANDS_CODE_CACHE_DIR`), feeding `window_for()` and surfacing retiring models in `/model`.
  - Fix `_vendor_family()` in `model_switch.py` so bare tails `claude-*` → `("anthropic", "claude")`, `gpt-*` → `("openai", "gpt")` (preserving compound `gpt-oss-*` → `("openai", "gpt-oss")`), and `o1`/`o3`/`o4-*` → `("openai", "o1"|"o3"|"o4")` group cleanly in `/model` trees and match `model-capabilities.yaml` rules. — *Reversibility: easy — fail-soft discovery and deterministic grouping.*

### Ambient Defaults, Lean API Extras & Mannerism Guards
- **D-07 (Updated ambient defaults, lean extras posture & OpenAI/Anthropic mannerism guards):**
  - Update `_AMBIENT_DEFAULT_MODELS` in `strands_code_cli/entry/first_run.py`:
    - `ANTHROPIC_API_KEY` → `"anthropic/claude-sonnet-5-5"` (1M context, 128K output, `cachePoints`, \$2/\$10)
    - `OPENAI_API_KEY` → `"openai/gpt-6.1-sol"` (1.05M context, `cachePoints`, \$2/\$10)
  - Keep lean harness-first API extras: wire Anthropic `/v1/models` 24h cache directly; keep harness defaults for caching, web search, and effort plus local char/4 token estimation (no extra per-turn token-count API calls or unsolicited slash commands); document `use_native_token_count`, `service_tier` (`flex`/`priority`), `prompt_cache_retention`/`prompt_cache_options`, `anthropic-version: 2026-10-21` sampling-parameter removal, `max_tokens` ceilings & extended thinking constraints, PDF/plain-text document constraints, `pause_turn` server tools, and upstream `strands-agents/harness-sdk#3389` encrypted-reasoning replay limits.
  - Add a fail-soft `configure_openai_for_model()` post-config seam (mirroring `configure_gemini_for_model()`) guarding non-reasoning (`gpt-4o`, `gpt-4.1`, `gpt-4o-mini`) and effort-subset (`o3`/`o4-mini`, `gpt-6-astra`/`gpt-6.1-sol`) OpenAI models whenever `strands_harness.models._openai()` emits an unsupported `reasoning.effort` payload, and draft a targeted upstream `strands-agents/harness-sdk` issue in `docs/upstream/` if confirmed during Phase 15 research. — *Reversibility: easy — isolated post-config helper and defaults tuple.*

### Verification & Documentation Posture
- **D-08 (Hermetic CI + repeatable `driver.py` OpenAI/Anthropic scenarios + `docs/QUICKSTART.md`):**
  - Keep all default CI suites (`pytest tests/ -q`, `ruff`, `xenon --max-absolute C`, `import-linter`) 100% hermetic (zero network / zero keys).
  - Add repeatable `driver.py` tmux UAT scenarios for native OpenAI (`o1`) and native Anthropic (`a1`) in `scripts/uattest/` (pinned by offline contract tests under `tests/rig/`), run live opportunistically whenever `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is present.
  - Add **Native OpenAI API** and **Native Anthropic API** setup sections to `docs/QUICKSTART.md` covering extras install (`uv sync --extra openai` / `--extra anthropic`), env vars, custom `base_url` + `api_mode: chat`, cache/cost display, and provider mannerisms. — *Reversibility: easy — isolated rig scripts and docs.*

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/REQUIREMENTS.md` — `MODEL-07` (`#17`) and `MODEL-08` (`#22`)
- `.planning/ROADMAP.md` — Phase 15 goal & 3 success criteria
- `pyproject.toml` — Optional extras (`agentcore`, `litellm`, `gemini`; add `openai`, `anthropic`) & CI gates
- `strands_code_cli/entry/first_run.py` — `_AMBIENT_DEFAULT_MODELS`, `_PROVIDER_ENV_KEYS`, `preflight_credentials`, Box/dotenv guards
- `strands_code_cli/entry/provider_config.py` — `ProviderConfig` (`model`, `base_url`, `codeact`; add optional `api_mode`)
- `strands_code_cli/entry/main.py` — `model_for_config`, `build_agent` post-config seams (`L179-219`), `_root`
- `strands_code_cli/model/model_switch.py` — `supports_reasoning`, `same_vendor`, `canonical_prefix_hash`, `convert_history`, `discover_models`, `_vendor_family`, `configure_gemini_for_model`, `apply_switch` (`L923-957`)
- `strands_code_cli/dispatch/core.py` — `_SDK_EXTRA_HINTS` (`L77-99`), `_model_message`
- `strands_code_cli/loop/core.py` — `record_turn_metrics` (`L317-360`), `/route` `resolve_model` call (`L509`) and main-loop routing call site
- `strands_code_cli/cost/live_pricing.py` — `_live_disabled`, `_cache_dir`, `litellm_entry` (`L480-524`), `cached_tables`
- `strands_code_cli/cost/cost_context.py` — `MODEL_PRICING`, `MODEL_LIMITS`, `_live_price`, `window_for`, `cost_for`, `usage_line`, `cost_report`, `estimate_messages_tokens`
- `tests/cost/test_cost_context.py` — `test_no_budgets_or_enforcement_vocabulary` (`L959-987`), `test_no_credential_persistence_sinks` (`L988-1009`)
- `tests/model/test_model_switch.py` & `tests/entry/test_first_run.py` — Existing switch, pricing, and preflight contracts
- `docs/QUICKSTART.md` — Provider & first-run documentation
- Installed SDK/Harness references in `.venv`: `strands_harness/models.py`, `strands/models/anthropic.py`, `strands/models/openai_responses.py`, `strands/models/openai.py`, `strands/models/_thinking_binding.py`, `strands/models/_openai_cache.py`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `configure_streaming_for_model()` and `configure_gemini_for_model()` (`model_switch.py:773-858`) already demonstrate the exact post-`create_harness` / post-`resolve_model` adjustment pattern (called from `entry/main.py:build_agent` and `model_switch.py:apply_switch`, and mirrored in `loop/core.py` routing sites). `configure_openai_for_model()` and post-applied `base_url` can follow this exact seam cleanly.
- `live_pricing._read_cache()`, `_write_cache()`, `_cache_dir()`, and `_live_disabled()` (`live_pricing.py:62-114`) provide a tested 24h file-cache foundation to reuse for `~/.cache/strands-code/anthropic-models.json`.
- `scripts/uattest/scenarios_gemini.py` and `scenarios_upstream.py` show the exact `driver.py` isolated `XDG_CONFIG_HOME` tmux test pattern ready to mirror for `o1` / `a1`.

### Constraints & Watchpoints
- **`test_no_credential_persistence_sinks` (`tests/cost/test_cost_context.py:988-1009`):** Strictly forbids `os.getenv` / `os.environ` inside `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, and `entry/main.py`! All env-presence checks MUST remain inside `strands_code_cli/entry/first_run.py` (never inspect vendor key prefixes like `sk-ant-...` or `sk-...` so Strands Box phantom tokens keep passing).
- **`test_no_budgets_or_enforcement_vocabulary` (`tests/cost/test_cost_context.py:959-987`):** Strictly forbids literal `"budget"`, `"enforce"`, `"quota"`, or `"halt"` substrings (case-insensitive) in `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, and `strands_code_agent/utils.py` unless `"display only"`, `"never"`, or `"no "` appears in a two-line window. Avoid using those substrings in identifiers/comments in those files (e.g., mirror Phase 14's `_THINKING_LIMIT_KEY` rather than writing `budget` in `model_switch.py`).
- **Maintain `strands_code_agent/` byte-pristine (`D-24`):** Do NOT modify `strands_code_agent/utils.py`; read `cacheReadInputTokens` / `cacheWriteInputTokens` directly from `result.metrics.get_summary()["accumulated_usage"]` inside `strands_code_cli/loop/core.py:record_turn_metrics`.
- **Complexity ceiling (`xenon --max-absolute C`, `CC <= 20`) & `import-linter`:** Keep `record_turn_metrics`, `apply_switch`, `discover_models`, `convert_history`, and `cost_report` cleanly factored into small helpers with zero circular imports between `entry/`, `model/`, `cost/`, and `loop/`.

</code_context>

<specifics>
## Specific Ideas

- For `OpenAIResponsesModel` post-applied `base_url`: verify during Phase 15 research/planning whether `resolved_model.client_args["base_url"] = base_url` (or `update_config` / `client_args` mutation) suffices before `_get_client()` instantiates `openai.AsyncOpenAI(**self._resolve_client_args())` per request, and for `AnthropicModel` rebind `resolved_model.client = anthropic.AsyncAnthropic(base_url=base_url)` cleanly when `ANTHROPIC_BASE_URL` env is not overriding it. Also ensure `parent_config` (`agent._harness_kwargs`) preserves `web_fetch` model / post-config hooks for `/btw` side agents.
- Verify during research how `BedrockModel` (`bedrock/anthropic.*`, `bedrock/amazon.nova-*`, etc.) reports `inputTokens` vs `cacheReadInputTokens` / `cacheWriteInputTokens` (Bedrock Converse also treats `inputTokens` as exclusive of cache tokens!) so updating `cost_context.py` fixes Anthropic & OpenAI without breaking existing Bedrock tests.
- Keep `MODEL_LIMITS` and `MODEL_PRICING` key ordering in `cost_context.py` specific-before-general so `claude-sonnet-5-5` (1M, \$2/\$10) matches ahead of any prefix fallback.

</specifics>

<deferred>
## Deferred Ideas

- Native Meta Model API (`https://api.meta.ai/v1` / Muse Wonder / Spark / Ember) and upstream `strands-agents/harness-sdk` `meta/` proposal — **Phase 16 (`MODEL-09`, `#21`)**.
- `DecisionModel` routing convergence — **Phase 17 (`UPSTREAM-02`)**.
- Admin-key-only organization spend/cost analytics endpoints (`/v1/organization/costs`, `/v1/organizations/analytics/cost`) — **Out of Scope** for developer-key CLI sessions.
- Explicit CLI / `config.yaml` toggles for OpenAI `service_tier` (`flex`/`priority`), `prompt_cache_retention`, or per-turn `use_native_token_count` (`count_tokens`) — keep documented via harness `params` unless a clean need emerges later.
- Strands Box `policy.dw` egress templates for `api.openai.com` (`Authorization: Bearer`) and `api.anthropic.com` (`x-api-key`) — **Phase 19 (`SANDBOX-01`)**.

</deferred>

*Phase: 15-first-class-native-openai-anthropic-apis*
*Context gathered: 2026-11-23*
