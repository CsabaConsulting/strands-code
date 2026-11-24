---
phase: 15-first-class-native-openai-anthropic-apis
plan: "01"
subsystem: entry, dispatch, model, loop
tags: [openai, anthropic, provider-config, api-mode, base-url, harness, uv]
requires:
  - phase: 14-google-gemini-api-integration
    provides: ProviderConfig base_url, first-run preflight, Gemini configure helper, and harness resolver patterns
provides:
  - openai ("strands-agents[openai]", "openai>=2.0.0") and anthropic ("strands-agents[anthropic]") optional extras + uv.lock sync
  - Updated _AMBIENT_DEFAULT_MODELS (anthropic/claude-sonnet-5-5, openai/gpt-6.1-sol), has_openai_credentials(), has_anthropic_credentials(), and explicit Anthropic base_url preflight allowance
  - ProviderConfig.api_mode ("responses" | "chat") validated YAML persistence
  - Harness-preserving base_url plumbing (configure_base_url_for_model + web_fetch pinning) and stripped-tail OpenAIModel fallback in api_mode="chat"
  - Shared resolve_harness_model() preserving caching=True, caching_explicit=False, and web_search=True across apply_switch() and _route_side_spawn(), plus /btw base_url propagation
affects: [15-02, 15-03]
tech-stack:
  added: [anthropic==2.13.0, aws-bedrock-token-generator==1.1.0, openai==2.54.0]
  patterns: [resolve_harness_model shared switch/route factory, post-applied ProviderConfig.base_url]
key-files:
  created: []
  modified:
    - pyproject.toml
    - uv.lock
    - tests/conftest.py
    - strands_code_cli/dispatch/core.py
    - strands_code_cli/entry/first_run.py
    - strands_code_cli/entry/provider_config.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/loop/core.py
    - strands_code_cli/loop/btw.py
    - tests/dispatch/test_cli_entry.py
    - tests/entry/test_first_run.py
    - tests/model/test_model_switch.py
    - tests/routing/test_routing.py
    - tests/loop/test_loop_routing.py
    - tests/loop/test_btw.py
    - tests/cost/test_cost_context.py
key-decisions:
  - "Declare openai>=2.0.0 alongside strands-agents[openai] and anthropic extras in pyproject.toml and map both in _SDK_EXTRA_HINTS (D-01)"
  - "Pass openai/ and anthropic/ model IDs as strings into create_harness in default responses mode, pinning web_fetch and post-applying base_url via configure_base_url_for_model(); restrict pre-built OpenAIModel construction to litellm/ or explicit api_mode='chat' (D-04)"
  - "Unify apply_switch() and _route_side_spawn() on resolve_harness_model() forwarding caching=True, caching_explicit=False, web_search=True when supported, effort, and base_url (D-02)"
requirements-completed: [MODEL-07, MODEL-08]
metrics:
  completed: "2026-11-24"
---

# Phase 15 Plan 01: Provider Extras, Preflight, `api_mode`, & Harness-Preserving Switch/Routing Plumbing Summary

**Delivered optional `openai`/`anthropic` extras synced in `uv.lock`, credential-gated OpenAI/Anthropic preflight helpers, validated `ProviderConfig.api_mode`, harness-preserving `base_url` plumbing, and shared `resolve_harness_model()` parity across `/model`, `/route`, and `/btw`.**

## Changes Made
- **`pyproject.toml` & `uv.lock`:** Declared `openai = ["strands-agents[openai]", "openai>=2.0.0"]` and `anthropic = ["strands-agents[anthropic]"]`; locked (`Resolved 156 packages`) and synced (`anthropic==2.13.0`, `aws-bedrock-token-generator==1.1.0`, `openai==2.54.0` alongside extras).
- **`tests/conftest.py`:** Scrubbed `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL` in test fixtures.
- **`strands_code_cli/dispatch/core.py`:** Mapped `"openai"` and `"anthropic"` in `_SDK_EXTRA_HINTS`.
- **`strands_code_cli/entry/first_run.py`:** Bumped `_AMBIENT_DEFAULT_MODELS` to `("anthropic/claude-sonnet-5-5", ...)` and `("openai/gpt-6.1-sol", ...)`; added non-empty presence-only `has_openai_credentials()` and `has_anthropic_credentials()`; allowed explicit `anthropic/` + `base_url` gateways during preflight.
- **`strands_code_cli/entry/provider_config.py`:** Added `VALID_API_MODES = ("responses", "chat")`, `ProviderConfig.api_mode`, `_validate_provider_fields()` (preserving `xenon C`), and YAML load/save serialization (no secrets persisted).
- **`strands_code_cli/entry/main.py`, `strands_code_cli/model/model_switch.py`, `strands_code_cli/loop/core.py`, `strands_code_cli/loop/btw.py`:**
  - Updated `model_for_config()` and `build_agent()` so default `openai/` and `anthropic/` pass strings into `create_harness` while post-applying `base_url` via `configure_base_url_for_model()`, pinning `builtin_tools["web_fetch"]`, and propagating `_base_url` into `/btw` rebuilds without leaking extra harness kwargs.
  - Built stripped-tail `OpenAIModel(model_id=rest, client_args={"base_url": base_url})` only when `api_mode == "chat"` on `openai/` (or for `litellm/` custom URLs).
  - Extracted `resolve_harness_model()` and wired both `apply_switch()` and `_route_side_spawn()` through it so `caching=True, caching_explicit=False`, `web_search=True` (when supported), `effort`, and `base_url` stay intact.

## Verification
- `.venv/bin/pytest tests/entry/ tests/dispatch/test_cli_entry.py tests/model/test_model_switch.py tests/routing/test_routing.py tests/loop/test_btw.py tests/loop/test_loop_routing.py tests/cost/test_cost_context.py -k "not stub" -q` -> **581 passed, 6 deselected**
- `.venv/bin/ruff check strands_code_cli tests scripts` -> passed
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **115 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli/entry/ strands_code_cli/dispatch/ strands_code_cli/model/ strands_code_cli/loop/` -> passed (`CC <= C`)
- `/home/csaba/.local/bin/uv lock --check` -> **Resolved 156 packages**
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
