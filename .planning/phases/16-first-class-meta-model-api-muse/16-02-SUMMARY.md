---
phase: 16-first-class-meta-model-api-muse
plan: "02"
subsystem: model, cost
tags: [meta, muse, media, discovery, pricing, litellm, cost-context, scrub]
requires:
  - phase: 16-01
    provides: first_run Meta credential/base_url helpers and auto-retiring meta/ adapter
provides:
  - Scoped _MEDIA_LESS Bedrock Llama 3/4 rules so all multimodal meta/muse-* models keep media while Llama stays text-only
  - Credential-gated GET /v1/models Meta discovery (_discover_meta_models filtering out muse-image-*, muse-voice-transcribe-*, sam-*) and ("meta", "muse") _vendor_family() grouping
  - LiteLLM bare/meta lookup (_litellm_keys), static fallbacks for muse-ember-1.0 / muse-spark-* / muse-wonder-1.0 (1_048_576 window), 50x contributor cache rates, inclusive usage normalization, and LLM_.../LLM|... credential scrubbing
affects: [16-03]
tech-stack:
  added: []
  patterns: [Bedrock-scoped _MEDIA_LESS, _META_NON_CHAT_TOKENS discovery filtering, Meta cache-rate multipliers]
key-files:
  created: []
  modified:
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/cost/live_pricing.py
    - strands_code_cli/cost/cost_context.py
    - tests/model/test_model_switch.py
    - tests/cost/test_live_pricing.py
    - tests/cost/test_cost_context.py
key-decisions:
  - "Filter _META_NON_CHAT_TOKENS including 'image' alongside 'voice'/'transcribe'/'sam-' because api.meta.ai/v1/models lists muse-image-1.0 under the muse- prefix"
  - "Leave cost_context.price_table untouched (already xenon CC 20) while extending MODEL_PRICING, MODEL_LIMITS, _default_cache_rates(), and _CRED_PATTERNS"
requirements-completed: [MODEL-09]
metrics:
  completed: "2026-11-24"
---

# Phase 16 Plan 02: Multimodal Muse Media Scope, Filtered Discovery & Cache-Aware `/cost` Summary

**Scoped `_MEDIA_LESS` so multimodal Muse models keep native media while Bedrock/OpenRouter Llama stay text-only, added filtered Meta `GET /v1/models` discovery with `("meta", "muse")` tree grouping, and wired 50× contributor cache discounts, static `muse-ember-1.0` pricing/1M windows, and `LLM_...`/`LLM|...` redaction.**

## Changes Made
- **`strands_code_cli/model/model_switch.py`:**
  - Narrowed `_MEDIA_LESS` from blanket `(None, "meta", None, None)` to `("bedrock", "meta", "llama3", None)` and `("bedrock", "meta", "llama4", None)` (preserving existing `(None, None, None, "llama")` coverage).
  - Updated `_infer_bare_vendor()` so `muse-*` tails map cleanly to `("meta", base)` -> `("meta", "muse")` in `build_model_tree()`.
  - Added `CURATED_META_MODELS`, `_META_NON_CHAT_TOKENS`, `_is_meta_chat_model()`, and credential-gated `_discover_meta_models()` merged into `discover_models()` (all env access via `first_run` helpers).
- **`strands_code_cli/cost/live_pricing.py` & `strands_code_cli/cost/cost_context.py`:**
  - Extended `_litellm_keys()` for `meta/` prefixes and bare `muse-` tails so LiteLLM's bundled Meta entries (`muse-spark-1.3-contributor` \$0.10/\$0.002/\$0.20, `muse-wonder-1.0` \$4.00/\$0.20/\$20.00) resolve with `1,048,576` windows.
  - Added static `MODEL_PRICING`, `MODEL_LIMITS["muse-"] = 1_048_576`, and `_default_cache_rates()` (`-contributor` `0.02`, `muse-ember-` `0.04`, `muse-wonder-` `0.05`, `muse-spark-` `0.12`).
  - Extended `_CRED_PATTERNS` (`scrub_credentials()`) with `LLM[_|]\d+[_|][A-Za-z0-9\-_]{12,}` and `|` inside `Bearer` patterns.
- **`tests/model/test_model_switch.py`, `tests/cost/test_live_pricing.py`, `tests/cost/test_cost_context.py`:** Added full offline contract coverage across media/thinking conversion, discovery filtering (`muse-image-1.0`, `muse-voice-transcribe-1.0`, `sam-3.1`), unkeyed isolation, LiteLLM + static pricing, inclusive Meta usage, key redaction, `test_no_credential_persistence_sinks`, and `test_no_budgets_or_enforcement_vocabulary`.

## Verification
- `.venv/bin/pytest tests/cost/ tests/model/test_model_switch.py -k "not test_stub_server_systemone_decision_routes" -q` -> **316 passed, 1 deselected**
- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **117 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli` -> **passed**
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken**
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
