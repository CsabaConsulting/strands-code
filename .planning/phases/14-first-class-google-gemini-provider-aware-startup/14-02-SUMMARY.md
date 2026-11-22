---
phase: 14-first-class-google-gemini-provider-aware-startup
plan: 02
subsystem: model, loop, cost
tags: [gemini, reasoningSignature, thinking_config, discovery, pricing]
dependency_graph:
  requires: ["14-01"]
  provides:
    - google/ reasoning support and cross-vendor toolUse["reasoningSignature"] stripping
    - decimal-safe _vendor_family() grouping for gemini-2.5-pro and gpt-5.4
    - configure_gemini_for_model() thinking_level -> thinking_budget guard across 4 wiring sites
    - credential-gated multi-provider discover_models() with CURATED_GEMINI_MODELS fallback
    - gemini/ and bare Gemini key lookup in live_pricing.litellm_entry() + static fallback prices/limits + non-Bedrock Price List skip
  affects:
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/loop/core.py
    - strands_code_cli/loop/btw.py
    - strands_code_cli/cost/live_pricing.py
    - strands_code_cli/cost/cost_context.py
    - tests/model/test_model_switch.py
    - tests/loop/test_btw.py
    - tests/cost/test_live_pricing.py
    - tests/cost/test_cost_context.py
tech_stack:
  added: []
  patterns:
    - "_canonical_block + _convert_tool_use_block isolate toolUse['reasoningSignature'] handling"
    - "_discover_google_models checks first_run.has_google_credentials() without touching os.environ"
    - "_THINKING_LIMIT_KEY API constant documented cleanly under test_no_budgets_or_enforcement_vocabulary"
key_files:
  modified:
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/loop/core.py
    - strands_code_cli/loop/btw.py
    - strands_code_cli/cost/live_pricing.py
    - strands_code_cli/cost/cost_context.py
    - tests/model/test_model_switch.py
    - tests/loop/test_btw.py
    - tests/cost/test_live_pricing.py
    - tests/cost/test_cost_context.py
decisions:
  - "Delegate loop/core.py:_has_thinking to model_switch._has_reasoning so RichHistory stashes and restores Gemini toolUse['reasoningSignature'] turns even when no reasoningContent block is present."
  - "_vendor_family splits on '.' only when the prefix matches [A-Za-z][A-Za-z0-9_]* (pure vendor ids), avoiding decimal version splits like 2.5 in gemini-2.5-pro or 5.4 in gpt-5.4."
  - "Non-Bedrock direct providers (google/, anthropic/, openai/, ollama/) skip bedrock_live_price lookups via _is_bedrock_model() before falling back to litellm_entry / static tables."
metrics:
  completed: "2026-11-21"
---

# Phase 14 Plan 02: Gemini Cross-Provider Safety, Thinking Guard, Discovery & `/cost` Summary

## What Was Built

1. **Cross-Provider `reasoningSignature` Safety, Grouping & Gemini 2.5 Thinking Guard (`D-04`, `D-07`):**
   - Added `"google"` to `supports_reasoning()` in `strands_code_cli/model/model_switch.py` plus fallback row `(None, "google", "gemini", None)`.
   - Extracted `_canonical_block()` and `_convert_tool_use_block()` so `convert_history()` strips `toolUse["reasoningSignature"]` on cross-vendor switches (verified against `LiteLLMModel.format_request_message_tool_call` keeping `id` free of `__thought__`), preserves it on same-vendor `google/ -> google/` switches, ignores it in `canonical_prefix_hash()`, and restores it via `RichHistory` (`_has_reasoning` + `loop/core.py:_has_thinking`).
   - Updated `_vendor_family()` to avoid decimal dot-splitting so `gemini-2.5-pro` groups under `("google", "gemini")` while keeping `bedrock/x -> ("x", "x")`.
   - Added `configure_gemini_for_model(model_id, resolved)` to translate `params["thinking_config"]["thinking_level"]` emitted by `strands_harness` onto Gemini 2.5 `thinking_budget` (`0` for `"off"`/`"none"`, `-1` otherwise) while leaving Gemini 3+ untouched, and wired it across `apply_switch`, `entry/main.py:build_agent`, `loop/core.py:_route_side_spawn`, and `loop/btw.py:build_btw_agent`. Annotated `_THINKING_LIMIT_KEY = "thinking_budget"` clearly so `TestLoopUsageWiring.test_no_budgets_or_enforcement_vocabulary` passes honestly.

2. **Credential-Gated Multi-Provider `/model` Discovery (`D-05`):**
   - Defined `CURATED_GEMINI_MODELS` and extracted `_append_bedrock_profiles`, `_discover_bedrock_models`, `_is_google_chat_model`, and `_discover_google_models` in `strands_code_cli/model/model_switch.py`.
   - `_discover_google_models()` checks `first_run.has_google_credentials()` (keeping `os.environ` absent from `model_switch.py`), enumerates `generateContent` `gemini-*` models via `google.genai.Client().models.list()`, falls back offline to `CURATED_GEMINI_MODELS` only when Google credentials exist, and merges with Bedrock results without duplicates.

3. **LiteLLM `gemini/` Keys, Static Pricing/Limits & Bedrock Price List Skip (`D-06`):**
   - Extended `live_pricing.litellm_entry()` for `gemini/<tail>` and bare `<tail>` keys (`litellm.model_cost`).
   - Added ordered curated Gemini rows (`-flash-lite`, `-flash`, `-2.5-pro`, `gemini-3-flash-preview`, `gemini-3.5-flash`) and `1_048_576` context limits to `MODEL_PRICING` / `MODEL_LIMITS` in `strands_code_cli/cost/cost_context.py`, plus `_is_bedrock_model()` in `_live_price()` so non-Bedrock direct providers skip AWS Price List lookups.

## Verification

- `.venv/bin/pytest tests/model/test_model_switch.py tests/loop/test_btw.py tests/cost/ -q`: **324 passed**
- `.venv/bin/ruff check strands_code_cli tests scripts`: **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts`: **113 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli/model/ strands_code_cli/cost/ strands_code_cli/loop/ strands_code_cli/entry/`: **exit 0**
- `.venv/bin/lint-imports`: **Contracts: 1 kept, 0 broken**
