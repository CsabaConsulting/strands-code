# Phase 15: First-Class Native OpenAI & Anthropic APIs — Research

**Researched:** 2026-11-23
**Phase:** `15-first-class-native-openai-anthropic-apis`
**Requirements:** `MODEL-07` (`CsabaConsulting/strands-code#17`), `MODEL-08` (`CsabaConsulting/strands-code#22`)
**Sources Verified Live in `.venv`:** `strands-agents==1.65.0`, `strands-harness==0.4.0`, `litellm`, `radon`, and Phase 14/15 codebase (`2986804`).

---

## 1. Upstream SDK & Harness Inspection (`strands-agents==1.65.0`, `strands-harness==0.4.0`)

### 1.1 Packaging & Extra Bounds
- Live metadata from `.venv` (`importlib.metadata.requires`):
  - `strands-agents==1.65.0`:
    - `anthropic<3.0.0,>=0.21.0; extra == 'anthropic'`
    - `aws-bedrock-token-generator<2.0.0,>=1.1.0; extra == 'openai'`
    - `openai<4.0.0,>=1.68.0; extra == 'openai'`
  - `strands-harness==0.4.0`:
    - `strands-agents[anthropic]; extra == 'anthropic'`
    - `openai<3.0.0,>=2.0.0; extra == 'openai'`
    - `strands-agents[openai]; extra == 'openai'`
- **Important version floor (`OpenAIResponsesModel`):** `strands/models/openai_responses.py:38-54` enforces `_MIN_OPENAI_VERSION = Version("2.0.0")` at import time (`ImportError` on older `openai 1.x`). Therefore `pyproject.toml` `[project.optional-dependencies]` MUST declare:
  - `openai = ["strands-agents[openai]", "openai>=2.0.0"]`
  - `anthropic = ["strands-agents[anthropic]"]`
  *(No upper pins during the experimental phase, matching `D-01`.)*
- Currently `_SDK_EXTRA_HINTS` in `strands_code_cli/dispatch/core.py:77-81` maps only `litellm`, `bedrock`, and `google`. Adding `"openai": "openai"` and `"anthropic": "anthropic"` surfaces `pip install strands-code-agent[openai]` / `[anthropic]` on `ImportError`.

### 1.2 Switch & Route `caching` / `web_search` Gap
- `strands_harness/agent.py:407-415` (`create_harness`) passes `caching=caching_on` (default `True`, `DEFAULT_CACHING`) and `web_search=web_search == "native"` into `resolve_model(...)`.
- However, both mid-session switching and side-agent routing omit those kwargs:
  - `strands_code_cli/model/model_switch.py:948-956` (`apply_switch`): calls `resolve_model(new_string, default or new_string[, effort=effort])` -> `caching=False`, `web_search=False`!
  - `strands_code_cli/loop/core.py:509` (`_route_side_spawn`): calls `resolve_model(pick.model, pick.model, effort=pick.effort)` -> `caching=False`, `web_search=False`!
- In `strands_harness/models.py:583-598`, when `caching=True` and `caching_explicit=False`, providers without caching (`ollama`) cleanly log a warning and continue without raising, while `anthropic/`, `openai/`, `bedrock`, `bedrock-mantle`, `google`, and `litellm` activate caching (`CacheConfig` / server-side). Calling `supports_web_search(target)` enables native search cleanly without touching non-native models.
- **Test-contract note:** Existing tests in `tests/model/test_model_switch.py:2412-2430` and `tests/routing/test_routing.py:2267, 2284` monkeypatch `resolve_model` and assert exact `{}` / `{"effort": "high"}` kwargs. Those tests must be updated alongside `apply_switch` in Plan `15-01-T2` (`D-02`).

### 1.3 Harness-Preserving Custom `base_url` Architecture
- `strands_harness/models.py:79` defines `_CUSTOM_ENDPOINT_VARS = {"anthropic": "ANTHROPIC_BASE_URL", "openai": "OPENAI_BASE_URL"}`. When those env vars are set:
  - `OpenAIResponsesModel` / `AnthropicModel` read `OPENAI_BASE_URL` / `OPENAI_ORG_ID` / `OPENAI_PROJECT` / `ANTHROPIC_BASE_URL` automatically inside `openai.AsyncOpenAI()` / `anthropic.AsyncAnthropic()`.
  - `resolve_web_fetch_model()` automatically reuses the main model instead of probing a vended summarizer (`gpt-5.6-luna` / `claude-haiku-4-5`) on the custom endpoint.
- **The `model_for_config()` trap:** `strands_harness/models.py:563-569` treats any pre-built `Model` instance passed to `create_harness(model=...)` as an unknown provider — skipping `effort`, `CacheConfig`, and native `web_search`. In addition, `strands_code_cli/entry/main.py:105-113` (`model_for_config`) currently constructs legacy Chat Completions `strands.models.openai.OpenAIModel(model_id=model, client_args={"base_url": base_url})` whenever `base_url` is set on `openai/` (without even stripping the `"openai/"` prefix!) and ignores `base_url` for `anthropic/`.
- **Clean `D-04` architecture:**
  1. Pass `"openai/..."` and `"anthropic/..."` as **strings** into `create_harness(model=...)` unless `ProviderConfig.api_mode == "chat"` (or `litellm/` with `base_url`).
  2. When `config.base_url` is set on `openai/` or `anthropic/` (default `api_mode` = `None` / `"responses"`):
     - Pass `web_fetch={"model": effective_model}` in `builtin_tools` so `web_fetch` doesn't probe vended small models on custom endpoints.
     - Post-apply `config.base_url` via `configure_base_url_for_model(target_id, resolved_model, base_url=base_url)` right after `create_harness` (mirroring `configure_streaming_for_model` & `configure_gemini_for_model`):
       - On `OpenAIResponsesModel`: `resolved.client_args["base_url"] = base_url` (because `_get_client()` builds `openai.AsyncOpenAI(**self._resolve_client_args())` per request, and `bedrock_mantle_config` is absent).
       - On `AnthropicModel`: rebind `resolved.client = anthropic.AsyncAnthropic(base_url=base_url)` when no custom client/env override conflicts (or set `base_url` on a fresh `AsyncAnthropic` reusing any configured kwargs).
     - Store `base_url` on `agent._base_url` / apply via `apply_switch(..., base_url=...)` and `build_btw_agent()` / `_route_side_spawn()` so switches and `/btw` side agents preserve custom endpoints cleanly!
  3. Opt-in `api_mode: chat` in `ProviderConfig` (`config.yaml`, validated `"responses" | "chat"`): construct `OpenAIModel(model_id=tail, client_args={"base_url": base_url})` (stripping `"openai/"`!) inside `model_for_config()`.

### 1.4 Confirmed Upstream Bug: `strands_harness` Emits `reasoning.effort` Unconditionally on OpenAI Models
- Probed live in `.venv` (`strands-harness==0.4.0`):
  ```text
  openai/gpt-4o     -> OpenAIResponsesModel params: {'reasoning': {'effort': 'high'}, ...}
  openai/gpt-4.1    -> OpenAIResponsesModel params: {'reasoning': {'effort': 'high'}, ...}
  openai/o3         -> OpenAIResponsesModel params: {'reasoning': {'effort': 'high'}, ...}
  openai/gpt-6.1-sol -> OpenAIResponsesModel params: {'reasoning': {'effort': 'high'}, ...}
  ```
- OpenAI's `/v1/responses` API rejects `reasoning: {"effort": ...}` on non-reasoning models (`gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4-turbo`, `chat-latest`) with HTTP 400 (`Unsupported parameter: 'reasoning'`).
- Effort-subset rules on OpenAI Responses models:
  - `o1`, `o3`, `o3-mini`, `o3-pro`, `o4-mini`: accept only `("low", "medium", "high")` — reject `"minimal"`, `"xhigh"`, `"none"` (note: `"xhigh"`/`"minimal"` downgrade cleanly to `"high"`/`"low"`, `"none"` strips `reasoning`).
  - `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-5-pro`, `gpt-5.1`, `gpt-5.2`, `gpt-5.2-pro`: accept `("minimal", "low", "medium", "high")` (older GPT-5 lacks `"none"`/`"xhigh"`).
  - `gpt-5.4*`, `gpt-5.5*`, `gpt-5.6*`: accept `("none", "minimal", "low", "medium", "high", "xhigh")` (model_info defaultEffort applies).
  - `gpt-6-astra`, `gpt-6.1-sol`: mirror Bedrock's `_BEDROCK_GPT_NO_NONE_LEVELS` (disallow `"none"` / `"minimal"`, minimum `"low"`).
- Mirroring Phase 14's `configure_gemini_for_model()`, add `configure_openai_for_model(model_id, resolved)` across the same 4 instantiation sites (`entry/main.py`, `model_switch.py`, `loop/core.py`, `loop/btw.py`), and draft a held upstream issue in `docs/upstream/harness_issue_openai_reasoning_guard.md` (`15-03-T2`).

### 1.5 Verified SDK `Usage` Cache-Token Semantics Across All Providers
- Inspected `.venv` `strands/models/anthropic.py`, `openai_responses.py`, `openai.py`, `gemini.py`, `bedrock.py`, and `strands/telemetry/metrics.py:193-204`:
  - **`strands/telemetry/metrics.py:198-203` (`_total_prompt_tokens`)** captures the exact invariant:
    ```python
    if input_tokens + output_tokens == total_tokens:
        return input_tokens  # inclusive (OpenAI Responses/Chat, Gemini)
    return input_tokens + usage.get("cacheReadInputTokens", 0) + usage.get("cacheWriteInputTokens", 0)  # exclusive (Anthropic, Bedrock Converse)
    ```
  - Specifically verified:
    - **`AnthropicModel` (`anthropic.py:74-92`):** `inputTokens` is uncached+unwritten base input only (**excludes** `cacheReadInputTokens` and `cacheWriteInputTokens`); `totalTokens = input + output + cache_read + cache_write`.
    - **`OpenAIResponsesModel` (`openai_responses.py:1091-1108`):** `inputTokens = input_tokens` (**includes** `cached_tokens` / `cacheReadInputTokens`, and includes `cache_write_tokens` on GPT-5.6+ where `cacheWriteInputTokens` is also reported); `totalTokens = total_tokens`.
    - **`BedrockModel` (`bedrock.py:1898`):** Converse usage has `inputTokens` excluding cache read/write tokens while `totalTokens` sums all four.
    - **`GeminiModel` (`gemini.py:596-607`):** `inputTokens = prompt_token_count` (includes `cached_content_token_count`!).
  - **Normalization in `record_turn_metrics()` (`strands_code_cli/loop/core.py`):**
    - Read `accumulated_usage` directly from `result.metrics.get_summary()` (keeping `strands_code_agent/utils.py` byte-pristine under `D-24`).
    - Compute total prompt tokens (`total_in`) via the inclusive-vs-exclusive rule (`input_tokens + output_tokens == total_tokens` -> inclusive; when `total_tokens` is absent/0, use provider fallback: `anthropic/` and `_is_bedrock_model(model_id)` are exclusive; others inclusive).
    - Derive `uncached_in = inputTokens` (exclusive) or `max(0, total_in - cache_read - cache_write)` (inclusive).
    - Store `input_tokens = total_in` in `session_turns` (so existing `format_usage(total_in, window)` computes exact context `%` on Anthropic too!) and store `cache_read_tokens` / `cache_write_tokens` on `row` only when `> 0`.

### 1.6 LiteLLM Pricing Keys, SDK `model_info.json`, & Anthropic `/v1/models` Metadata
- Verified live against `litellm.model_cost` in `.venv`:
  - Native Anthropic and OpenAI models are keyed **bare** (no `anthropic/` or `openai/` prefix):
    - `claude-sonnet-5-5`: `in=$2.00`, `out=$10.00`, `cache_read=$0.10`, `cache_write=$2.50`, `window=1_000_000`
    - `claude-opus-5-5`: `in=$4.00`, `out=$20.00`, `cache_read=$0.20`, `cache_write=$5.00`, `window=1_000_000`
    - `gpt-5.4`: `in=$2.50`, `out=$15.00`, `cache_read=$0.25`, `cache_write=None`, `window=1_050_000`
    - `gpt-6.1-sol`: `in=$2.00`, `out=$10.00`, `cache_read=$0.10`, `cache_write=$2.50`, `window=922_000` (SDK `model_info.json` reports `1_050_000`, which wins `window_for()` first!)
  - Adding bare `tail` (plus `f"anthropic/{tail}"` / `f"openai/{tail}"` before generic `bedrock/` when prefixed `anthropic/` or `openai/`) in `live_pricing.litellm_entry()`, and parsing optional `cache_read_input_token_cost` -> `entry["cache_read"]` (`* 1M`) and `cache_creation_input_token_cost` -> `entry["cache_write"]` (`* 1M`), unlocks cache-accurate pricing across Anthropic, OpenAI, and Bedrock automatically.
  - Note: For OpenAI GPT-5.6+ where LiteLLM lacks `cache_creation_input_token_cost` (`None`), fall back to `in_rate` (or documented `1.25x` if cache-write is nonzero? Safe conservative rule: use explicit `cache_write` rate when known, else `in_rate` for uncached/write delta or `1.25 * in_rate` for Anthropic when `cache_write` missing — let's document explicit per-rate lookup + standard `0.10x` / `1.25x` fallback when a cache-rate row or static entry omits it, or explicit static `MODEL_CACHE_PRICING` table).
- Anthropic `GET https://api.anthropic.com/v1/models` returns per-model fields:
  - `id`, `display_name`, `created_at`, `max_input_tokens`, `max_tokens`, `capabilities`, `line`, `retires_at`.
  - Storing a 24h file cache at `_cache_dir() / "anthropic-models.json"` (honoring `STRANDS_CODE_NO_LIVE_PRICING` and `STRANDS_CODE_CACHE_DIR`) lets `window_for("anthropic/...")` pick up live newly-released model windows ahead of static/LiteLLM fallbacks and lets `route_label()` display `(retires YYYY-MM-DD)` for retiring models without mutating the selectable model ID string!

### 1.7 Anthropic `SummaryBlock` Shape & Cross-Provider Thinking Safety
- Inspected `strands/types/content.py`: `SummaryBlock` is `{"provider": str | None, "signature": str | None, "text": str}` wrapped in `{"summary": SummaryBlock}`.
- Inspected `strands/models/anthropic.py:114-130, 798-803`: `_format_summary` emits `{"type": "compaction", "content": ..., "signature": ...}` only when `provider == "anthropic"` and `server_side_summary is True`; any other Strands model adapter (`BedrockModel`, `OpenAIResponsesModel`, `GeminiModel`, `LiteLLMModel`, `OllamaModel`) either drops or raises `TypeError` on unknown `"summary"` blocks!
- In `model_switch.py`:
  - `same_vendor("anthropic/claude-x", "bedrock/anthropic.claude-y")` is asserted `True` by `tests/model/test_model_switch.py:603`! Keep `same_vendor()` untouched and add `same_provider(first_id, second_id)` (`_provider_of(...) == _provider_of(...)`) alongside `same_vendor()` when gating raw signed thinking preservation inside `convert_history()` and `apply_model_action()` (so `anthropic/claude-*` ↔ `bedrock/anthropic.*` converts signed `reasoningContent` to `TRACE_LABEL` text and restores from `RichHistory` when returning to the original provider).
  - Add `_convert_summary_block()` in `model_switch.py`: preserve `{"summary": ...}` verbatim only when target provider is `"anthropic"` and source is `"anthropic"`; otherwise convert to `{"text": f"{SUMMARY_BLOCK_LABEL}\n{summary_text}"}` (while stashing raw `{"summary": ...}` in `RichHistory` for switch-back!). Note: include `"summary"` checks in `_canonical_block()` / `_has_thinking()` so `RichHistory` stashes and restores `"summary"` blocks seamlessly!

---

## 2. Existing Code Seams, Complexity Budget & Test Contracts

### 2.1 Existing Tests & Hard Contracts to Honor
1. **`tests/cost/test_cost_context.py:988-1009` (`test_no_credential_persistence_sinks`):**
   - Strictly forbids `"os.getenv"` and `"os.environ"` across `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, and `entry/main.py`.
   - Keep `has_openai_credentials(env=None)` and `has_anthropic_credentials(env=None)` strictly inside `strands_code_cli/entry/first_run.py`!
2. **`tests/cost/test_cost_context.py:959-987` (`test_no_budgets_or_enforcement_vocabulary`):**
   - Strictly forbids literal `"budget"`, `"enforce"`, `"quota"`, or `"halt"` (case-insensitive) in `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, and `strands_code_agent/utils.py` outside a 2-line display-only negation window! Never write `"thinking_budget"` or `"budget_tokens"` inside `model_switch.py` — use `_THINKING_LIMIT_KEY` or docstrings in `docs/` instead.
3. **Hermetic test updates required by new Phase 15 contracts:**
   - `tests/entry/test_first_run.py:142-147` (`test_anthropic_and_openai_ambient_auto_pick`): expects `"anthropic/claude-sonnet-4-6"` / `"openai/gpt-5.4"` -> update to `"anthropic/claude-sonnet-5-5"` and `"openai/gpt-6.1-sol"`.
   - `tests/model/test_model_switch.py:2105-2116` (`test_uninstallable_provider_reply_fail_soft`): passes `"/model anthropic/claude-3-7-sonnet-latest"` relying on `anthropic` NOT being installed in `.venv` — update to mock `ImportError` so installing `[anthropic]` never breaks the test.
   - `tests/model/test_model_switch.py:2412-2430` and `tests/routing/test_routing.py:2267, 2284`: assert exact `resolve_model` kwargs without `caching`/`web_search` -> update to assert `caching=True, caching_explicit=False` (+ `web_search` when enabled).
   - `tests/model/test_model_switch.py:2327-2353` (`test_model_for_config_shapes`): expects `model_for_config("openai/nemotron-70b", "https://proxy.local/v1")` to fall back cleanly when `strands.models.openai` is missing; preserve that contract for `api_mode="chat"` while verifying default `"responses"` passes strings cleanly through `create_harness` and post-applies `base_url`.
4. **`scripts/uattest/driver.py` slot names:** `a1` and `a2` are already bound to `scenarios_codeact.py`. Name the new Phase 15 scenarios `o1` (OpenAI) and `an1` (Anthropic) in `scenarios_openai_anthropic.py`.

### 2.2 Cyclomatic Complexity Baseline (`radon cc -s -n B`, hard ceiling `xenon --max-absolute C`, `CC <= 20`)
Measured baseline before edits:
- `cost_context.cost_report`: **`C (20)`** — AT CEILING! Must extract `_format_input_cell()` and `_format_turn_row()` before adding cache display logic, bringing `cost_report` down cleanly (`<= 14`).
- `cost_context.price_table`: **`C (20)`** — do NOT touch unless needed (keep `C 20`).
- `loop.core.apply_model_action`: **`C (19)`** — extract `_should_restore_rich()` before adding `same_provider()` + `SummaryBlock` check so it stays `<= 19`.
- `loop.core.run_loop`: **`C (18)`** — keep untouched or pass thin helpers (`<= 18`).
- `loop.core._route_side_spawn`: **`C (17)`** — call `resolve_harness_model()` helper rather than inline branching!
- `entry.provider_config.ProviderConfig.load` (**`C 16`**) & `.save` (**`C 15`**) — extract `_validate_provider_fields()` before adding `api_mode` validation!
- `cost.live_pricing.litellm_entry`: **`C (15)`** — extract `_litellm_keys()` & `_parse_litellm_entry()` so `litellm_entry` drops below `10`.
- `model_switch.convert_history` (**`C 14`**) & `_canonical_block` (**`C 14`**) — extract `_convert_summary_block()` and `_has_compaction_summary()`.
- `entry.first_run._check_explicit_provider`: **`C (14)`** — plenty of headroom.
- `dispatch.core._setup_decision_entries`: **`C (20)`** — unrelated; do not touch.

### 2.3 `import-linter` Contract & `D-24`
- `pyproject.toml` forbids feature modules (`model/`, `cost/`, `dispatch/`, `loop/`) from importing `strands_code_cli.entry.main`; importing `strands_code_cli.entry.first_run` and `strands_code_cli.entry.provider_config` respects the contract cleanly (already done in `routing/` and `model_switch.py`).
- `strands_code_agent/` MUST remain byte-pristine (`git diff ee42ea2 -- strands_code_agent/` empty).
