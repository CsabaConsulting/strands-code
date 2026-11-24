---
phase: 16-first-class-meta-model-api-muse
plan: "01"
subsystem: entry, dispatch, model, loop
tags: [meta, muse, strands-agents, strands-harness, preflight, openai-responses, uv]
requires:
  - phase: 15-first-class-native-openai-anthropic-apis
    provides: resolve_harness_model, scoped_base_url, configure_base_url_for_model, GPT-6.2 temporary bridge
provides:
  - Resynced dependencies to strands-agents>=1.66.0 (1.66.0) and strands-harness>=0.5.0 (0.5.0), retired _gpt_62_model_info_fallback(), and bumped OpenAI ambient default to openai/gpt-6.2-sol
  - Declared meta optional extra ("strands-agents[openai]", "openai>=2.0.0") + _SDK_EXTRA_HINTS["meta"]
  - Added first_run Meta credential/endpoint helpers (MODEL_API_KEY primary, META_API_KEY fallback, validated META_BASE_URL defaulting to https://api.meta.ai/v1) with priority Google -> Anthropic -> OpenAI -> Meta -> OpenRouter -> Bedrock
  - Shipped thin auto-retiring meta/ adapter (build_meta_model, upstream_supports_meta, model_id_of _strands_model_ref) across startup, /model, /route, and /btw without prompt_cache_options or reasoning.effort='none' errors
affects: [16-02, 16-03]
tech-stack:
  added: [strands-agents==1.66.0, strands-harness==0.5.0]
  patterns: [auto-retiring build_meta_model via upstream _PROVIDERS probe, _strands_model_ref identity preservation, _web_search_kind native gating]
key-files:
  created: []
  modified:
    - pyproject.toml
    - uv.lock
    - tests/conftest.py
    - strands_code_cli/entry/first_run.py
    - strands_code_cli/dispatch/core.py
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/loop/btw.py
    - tests/dispatch/test_cli_entry.py
    - tests/entry/test_first_run.py
    - tests/model/test_model_switch.py
    - tests/loop/test_btw.py
key-decisions:
  - "Upgrade to strands-agents 1.66.0 (#6265/#6396/#5997/#4683) and strands-harness 0.5.0; retire _gpt_62_model_info_fallback() and bump _AMBIENT_DEFAULT_MODELS['openai'] to openai/gpt-6.2-sol (D-05)"
  - "Gate resolve_harness_model(web_search=True) on _web_search_kind(normalized) == 'native' alongside supports_web_search() so Harness 0.5.0 Bedrock AgentCore web_search does not leak native web_search=True into resolve_model (preserving routing contracts)"
  - "Construct Meta OpenAIResponsesModel with ModelCapabilities(prompt_caching='auto') and plain CacheConfig() (omitting strategy='auto' warning and HTTP-400 prompt_cache_options), omitting reasoning on 'none'/'off' and attaching _strands_model_ref for cross-seam identity"
requirements-completed: [MODEL-09]
metrics:
  completed: "2026-11-24"
---

# Phase 16 Plan 01: Upstream `1.66.0`/`0.5.0` Resync, `meta` Extra/Preflight & Auto-Retiring `meta/` Adapter Summary

**Resynced `uv.lock` onto `strands-agents==1.66.0` & `strands-harness==0.5.0`, retired `_gpt_62_model_info_fallback()`, bumped OpenAI's ambient default to `openai/gpt-6.2-sol`, added `meta` packaging/credential helpers (`meta/muse-spark-1.3-contributor` ordered after OpenAI), and wired an auto-retiring `meta/` `OpenAIResponsesModel` adapter across startup, `/model`, `/route`, and `/btw`.**

## Changes Made
- **`pyproject.toml`, `uv.lock`, `tests/conftest.py`:** Raised dependency floors to `strands-agents>=1.66.0` and `strands-harness>=0.5.0` (no upper pins; `Resolved 156 packages`), added `meta = ["strands-agents[openai]", "openai>=2.0.0"]`, and scrubbed `MODEL_API_KEY`, `META_API_KEY`, and `META_BASE_URL` in test fixtures.
- **`strands_code_cli/entry/first_run.py`:** Added `META_DEFAULT_BASE_URL = "https://api.meta.ai/v1"`, `has_meta_credentials()`, `meta_api_key()` (`MODEL_API_KEY` primary, `META_API_KEY` fallback), `meta_base_url()` (validated via `provider_config._validate_base_url`), `_validate_meta_env()`, `_PROVIDER_ENV_KEYS["meta"]`, `_LITELLM_ANY_KEYS` entries, updated `BEDROCK_SETUP_POINTER`, and ordered `_AMBIENT_DEFAULT_MODELS` `anthropic/claude-sonnet-5-5 -> openai/gpt-6.2-sol -> meta/muse-spark-1.3-contributor` (`D-01`, `D-02`, `D-03`, `D-05`).
- **`strands_code_cli/model/model_switch.py`:**
  - Retired `_gpt_62_model_info_fallback()` cleanly now that `strands-agents 1.66.0` natively resolves `gpt-6.2-sol` (`1,050,000` window, `cache_points`), keeping `_target_openai_effort()` `gpt-6.2-` clamping (`D-05`).
  - Updated `resolve_harness_model()` to require `_web_search_kind(normalized) == "native"` alongside `supports_web_search()` (`strands-harness 0.5.0` `#5997`).
  - Added `upstream_supports_meta()`, `_normalize_meta_effort()` (omits `reasoning` on `"none"`/`"off"`), `_meta_model_info()` (`prompt_caching="auto"`, `1_048_576`/`131_072`), and `build_meta_model()` (`CacheConfig()`, `web_search` tool, `_strands_model_ref`), updated `model_id_of()`, `configure_base_url_for_model()`, and `resolve_harness_model()` (`D-04`).
- **`strands_code_cli/entry/main.py`, `strands_code_cli/dispatch/core.py`, `strands_code_cli/loop/btw.py`:**
  - Added `"meta": "meta"` to `_SDK_EXTRA_HINTS` and wired `_model_message()` to validate `meta/` via `build_meta_model()` until upstream adds `"meta"` to `_PROVIDERS`.
  - Wired `model_for_config()`, `build_agent()` (`caching=False` on `_strands_model_ref` pre-built Meta instances + `web_fetch` pinning), and `build_btw_agent()` (`caching=False` safety + `scoped_base_url()` isolation).
- **`tests/`:** Updated 5 `TestResolveSpike`/`TestNormalizeModelRef`/`TestSwapSeam`/`TestIdleOnlySwap` assertions in `test_model_switch.py` for `strands-harness 0.5.0` `#4683` (`AnthropicModel` wrapping `AsyncAnthropicBedrock` for Claude-on-Bedrock alongside `BedrockModel` for Nova), retired `_gpt_62_model_info_fallback` test into native SDK verification, and added full unit coverage for `first_run`, `dispatch`, `model_switch`, and `btw`.

## Verification
- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **117 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli` -> **passed**
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken** (39 files, 86 dependencies)
- `/home/csaba/.local/bin/uv lock --check` -> **Resolved 156 packages**
- `.venv/bin/pytest tests/entry/ tests/dispatch/test_cli_entry.py tests/model/test_model_switch.py tests/routing/test_routing.py tests/loop/test_btw.py tests/loop/test_loop_routing.py tests/cost/test_cost_context.py -k "not test_stub_server_systemone_decision_routes" -q` -> **612 passed, 6 deselected**
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
