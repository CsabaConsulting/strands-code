---
phase: 15-first-class-native-openai-anthropic-apis
plan: "02"
subsystem: cost, model, loop, entry
tags: [openai, anthropic, cache-pricing, summary-block, same-provider, reasoning-guard, model-discovery]
requires:
  - phase: 15-01
    provides: openai/anthropic extras, credential preflight helpers, api_mode, and resolve_harness_model()
provides:
  - Bare-tail LiteLLM key lookup + cache_read/cache_write rates and 24h Anthropic /v1/models cache (anthropic-models.json)
  - Inclusive vs exclusive usage normalization in record_turn_metrics() + cache-aware usage_line() and cost_report() (byte-identical zero-cache turns)
  - SummaryBlock token counting in estimate_messages_tokens() and window_for() Anthropic metadata precedence
  - same_provider() gating for signed reasoningContent and Anthropic SummaryBlock conversion + RichHistory/btw safety
  - _vendor_family() bare claude-/gpt-/o1/o3/o4- grouping and fail-soft configure_openai_for_model() across all 4 call sites
  - Credential-gated live OpenAI/Anthropic /model discovery, curated offline fallbacks, and retiring-date route_label()
affects: [15-03]
tech-stack:
  added: []
  patterns: [same_provider signed thinking isolation, cache_prices_for discounted accounting, configure_openai_for_model effort guard]
key-files:
  created: []
  modified:
    - strands_code_cli/cost/live_pricing.py
    - strands_code_cli/cost/cost_context.py
    - strands_code_cli/loop/core.py
    - strands_code_cli/loop/btw.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/model/model_switch.py
    - tests/cost/test_live_pricing.py
    - tests/cost/test_cost_context.py
    - tests/model/test_model_switch.py
    - tests/loop/test_btw.py
key-decisions:
  - "Normalize exclusive (Anthropic/Bedrock) vs inclusive (OpenAI/Gemini) accumulated_usage inputTokens using the SDK inputTokens + outputTokens == totalTokens invariant without altering strands_code_agent/utils.py (D-03, D-24)"
  - "Emit cache suffixes and discounted costs only when cache_read_tokens > 0 or cache_write_tokens > 0 so zero-cache turns stay byte-identical (D-03)"
  - "Gate raw signed reasoningContent round-trips on same_provider() AND same_vendor() and convert Anthropic SummaryBlock across non-Anthropic switches via RichHistory stash/restore (D-05)"
  - "Strip or clamp unsupported params['reasoning']['effort'] on native OpenAI models fail-soft across build_agent, apply_switch, _route_side_spawn, and build_btw_agent (D-07)"
requirements-completed: [MODEL-07, MODEL-08]
metrics:
  completed: "2026-11-24"
---

# Phase 15 Plan 02: Cache-Aware `/cost`, Cross-Provider Thinking & `SummaryBlock` Safety, OpenAI Reasoning Guard, & Live Discovery Summary

**Implemented cache-aware `/cost` and usage normalization across inclusive/exclusive SDK backends, bare-tail LiteLLM and 24h Anthropic metadata caching, same-provider thinking & `SummaryBlock` isolation, fail-soft `configure_openai_for_model()` effort guards, and credential-gated live OpenAI/Anthropic `/model` discovery.**

## Changes Made
- **`strands_code_cli/cost/live_pricing.py`:** Extracted `_litellm_keys()` and `_parse_litellm_entry()` to match bare OpenAI/Anthropic IDs alongside `cache_read` / `cache_write` rates; added `store_anthropic_models()`, `anthropic_models_cache()`, and `anthropic_model_entry()` using 24h `anthropic-models.json` honoring `STRANDS_CODE_NO_LIVE_PRICING` and `STRANDS_CODE_CACHE_DIR`.
- **`strands_code_cli/cost/cost_context.py` & `strands_code_cli/loop/core.py`:**
  - Normalized inclusive vs exclusive `accumulated_usage` in `record_turn_metrics()` (`_is_exclusive_usage_provider()`, `_extract_prompt_usage()`).
  - Updated `MODEL_PRICING` & `MODEL_LIMITS` (specific 5.x/6.x entries before generic prefixes), added `cache_prices_for()`, `_anthropic_cached_window()`, cache-aware `cost_for()`, `usage_line()`, extracted `_format_input_cell()` / `_format_turn_row()` / `_fold_routing_events()` for `cost_report()`, and counted `SummaryBlock` text in `estimate_messages_tokens()`.
- **`strands_code_cli/model/model_switch.py`, `strands_code_cli/loop/core.py`, `strands_code_cli/loop/btw.py`, `strands_code_cli/entry/main.py`:**
  - Added `same_provider()`, `SUMMARY_LABEL`, `_convert_summary_block()`, `_convert_block()`, `_should_restore_rich()`, and `_fork_message_content()` to keep signed thinking & Anthropic `SummaryBlock` isolated across `anthropic/` <-> `bedrock/anthropic.*` <-> non-Anthropic switches and `/btw` forks.
  - Added `_infer_bare_vendor()` in `_vendor_family()` for `claude-*`, `gpt-*`, `gpt-oss-*`, and `o1`/`o3`/`o4-*`.
  - Added `configure_openai_for_model()` (stripping `reasoning` on `gpt-4o`/`gpt-4.1*`/`gpt-4-turbo`/`chat-latest`/`gpt-3.5*` and clamping effort subsets on `o1`/`o3`/`o4-mini`, `gpt-5`..`5.2`, `gpt-6-astra`/`gpt-6.1-sol`) wired into `resolve_harness_model()`, `build_agent()`, and `build_btw_agent()`.
  - Implemented `CURATED_OPENAI_MODELS`, `CURATED_ANTHROPIC_MODELS`, `_is_openai_chat_model()`, `_discover_openai_models()`, `_extract_anthropic_model_meta()`, `_discover_anthropic_models()`, merged `discover_models()`, and `route_label()` retiring-date annotations (`(retires YYYY-MM-DD)`).

## Verification & Complexity (`radon cc -s -n C`)
- `.venv/bin/pytest tests/ -k "not stub" -q` -> **1677 passed, 12 deselected**
- `.venv/bin/ruff check strands_code_cli tests scripts` -> passed
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **115 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> passed
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken**
- Modified function complexities (all `<= C 20`): `cost_report` `C (12)`, `estimate_messages_tokens` `C (12)`, `apply_model_action` `C (13)`, `_extract_prompt_usage` `C (13)`, `fork_btw_history` `C (13)`, `configure_base_url_for_model` `C (15)`, `_target_openai_effort` `C (11)`, `litellm_entry` & `convert_history` `< C (<= 10)`.
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
