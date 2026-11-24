---
phase: 15-first-class-native-openai-anthropic-apis
status: passed
score: 8/8
verified: "2026-11-24"
requirements:
  - MODEL-07
  - MODEL-08
commits:
  - 27bedc5
  - 15d98a4
  - eeceb59
  - b102735
  - 3b8ab4f
---

# Phase 15 Verification: First-Class Native OpenAI & Anthropic APIs (`MODEL-07`, `MODEL-08`)

**Status:** Passed (`8/8` must-have truths verified + live `driver.py o1` `O1 PASS` and live `driver.py an1` `AN1 PASS` + upstream issues filed)  
**Verified:** 2026-11-24 on branch `main`

## Truth-by-Truth Verification Matrix

| # | Decision / Truth | Evidence (Code & Tests) | Observed Status |
|---|---|---|---|
| 1 | `D-01`, `D-07`: `openai` (`openai>=2.0.0`) & `anthropic` extras, `_SDK_EXTRA_HINTS`, `first_run` presence-only helpers + `_AMBIENT_DEFAULT_MODELS` bumped (`claude-sonnet-5-5`, `gpt-6.1-sol`) | `pyproject.toml`, `uv.lock` (`156` packages; `anthropic==2.13.0`, `openai==2.54.0`), `strands_code_cli/dispatch/core.py`, `strands_code_cli/entry/first_run.py`, `tests/conftest.py`, `tests/dispatch/test_cli_entry.py`, `tests/entry/test_first_run.py`, `tests/model/test_model_switch.py::TestUninstallableProvider` | ✅ Verified |
| 2 | `D-02`, `D-04`: `resolve_harness_model()` preserves `caching=True, caching_explicit=False` & `web_search=True` across `apply_switch()` + `_route_side_spawn()`; `ProviderConfig.api_mode` (`responses|chat`), harness string forwarding, `web_fetch` pinning, `configure_base_url_for_model()`, `/btw` `_base_url` propagation | `strands_code_cli/entry/provider_config.py`, `strands_code_cli/entry/main.py`, `strands_code_cli/model/model_switch.py`, `strands_code_cli/loop/core.py`, `strands_code_cli/loop/btw.py`, `tests/entry/test_first_run.py`, `tests/model/test_model_switch.py`, `tests/routing/test_routing.py`, `tests/loop/test_loop_routing.py`, `tests/loop/test_btw.py`, `tests/cost/test_cost_context.py::TestLoopUsageWiring::test_no_credential_persistence_sinks` | ✅ Verified |
| 3 | `D-03`, `D-24`: Inclusive vs exclusive `accumulated_usage` normalization in `record_turn_metrics()`, cache-discounted spend + compact suffix in `usage_line()` & `cost_report()` (zero-cache turns byte-identical), bare-tail `litellm_entry` + `cache_read`/`cache_write`, updated `MODEL_PRICING` / `MODEL_LIMITS`, `SummaryBlock` token counting; `strands_code_agent/` untouched | `strands_code_cli/cost/live_pricing.py`, `strands_code_cli/cost/cost_context.py`, `strands_code_cli/loop/core.py`, `tests/cost/test_live_pricing.py::TestOpenAIAnthropicLivePricing`, `tests/cost/test_cost_context.py::TestCacheAwareUsageAndCost`, `git diff ee42ea2 -- strands_code_agent/` empty | ✅ Verified |
| 4 | `D-05`: `same_provider()` AND `same_vendor()` gate raw signed `reasoningContent` across `anthropic/` <-> `bedrock/anthropic.*`; `SummaryBlock` (`SUMMARY_LABEL`) & `RichHistory` / `canonical_prefix_hash()` / `fork_btw_history()` switch safety | `strands_code_cli/model/model_switch.py`, `strands_code_cli/loop/core.py`, `strands_code_cli/loop/btw.py`, `tests/model/test_model_switch.py::TestSameProviderSummaryAndOpenAIGuard`, `tests/loop/test_btw.py::TestForkBtwHistory::test_converts_anthropic_summary_blocks_to_text` | ✅ Verified |
| 5 | `D-07`: Fail-soft `configure_openai_for_model()` strips `reasoning` on non-reasoning OpenAI models (`gpt-4o*`, `gpt-4.1*`, `gpt-4-turbo`, `chat-latest`, `gpt-3.5*`) and clamps effort subsets (`o1`/`o3`/`o4-mini`, `gpt-5`..`5.2`, `gpt-6-astra`/`gpt-6.1-sol`) across all 4 call sites + filed upstream bug report | `strands_code_cli/model/model_switch.py`, `strands_code_cli/entry/main.py`, `strands_code_cli/loop/core.py`, `strands_code_cli/loop/btw.py`, `docs/upstream/harness_issue_openai_reasoning_guard.md` (`strands-agents/harness-sdk#6522`), `tests/model/test_model_switch.py::TestSameProviderSummaryAndOpenAIGuard`, `tests/loop/test_btw.py::TestBuildBtwAgent::test_build_btw_agent_calls_configure_openai_for_model` | ✅ Verified |
| 6 | `D-06`: Credential-gated live OpenAI (`_is_openai_chat_model` filtered) & Anthropic (`store_anthropic_models` 24h `anthropic-models.json` feeding `window_for()` & retiring-date `route_label()`) `/model` discovery, `_vendor_family` grouping, zero unkeyed leakage | `strands_code_cli/model/model_switch.py`, `strands_code_cli/cost/live_pricing.py`, `strands_code_cli/cost/cost_context.py`, `tests/model/test_model_switch.py::TestLiveOpenAIAndAnthropicDiscovery` + live `/v1/models` probes | ✅ Verified |
| 7 | `D-08` (Docs & Rigs + OpenAI live `o1`): `docs/QUICKSTART.md`, `scripts/uattest/scenarios_openai_anthropic.py`, `driver.py`, `scenarios_upstream.py` (`USAGE_END_RE`), `tests/rig/test_uattest_openai_anthropic.py` (**42 passed**) + **live `driver.py o1` `O1 PASS`** | `docs/QUICKSTART.md`, `scripts/uattest/*`, `tests/rig/test_uattest_openai_anthropic.py`, `/tmp/uatr8/o1.log` (`O1 PASS`) | ✅ Verified |
| 8 | `D-08` (Anthropic live `an1`): Zero-AWS `--model anthropic/claude-sonnet-5-5` launch, `/context` (`1.00M`), live `read` tool turn (`ANTHROPIC_SENTINEL_15`), cache-aware usage & `/cost`, and same-provider `/model anthropic/claude-haiku-5-5` switch + **live `driver.py an1` `AN1 PASS`** | `scripts/uattest/scenarios_openai_anthropic.py`, `/tmp/uatr8/an1.log` (`AN1 PASS`) | ✅ Verified |

## Live Verification Results (With `.env` Keys & `openai` / `anthropic` Extras)

- **Live `_discover_openai_models()` (`BypassSandbox: true`):** Returned **`ok=True`**, **52** Responses-capable chat/reasoning models, exposing both `openai/gpt-6.1-sol` and `openai/gpt-6.1-terra`.
- **Live `_discover_anthropic_models()` (`BypassSandbox: true`):** Returned **`ok=True`**, **15** Claude models (exposing `anthropic/claude-sonnet-5-5` and `anthropic/claude-haiku-5-5`), and populated `/home/csaba/.cache/strands-code/anthropic-models.json` (**15** entries with `max_input_tokens`, `max_tokens`, `line`, and real `retires_at` timestamps on `claude-opus-4-5-20251101` `2027-01-22T20:00:00+00:00` and `claude-sonnet-4-5-20250929` `2026-11-30T17:00:00+00:00`).
- **Live `python3 scripts/uattest/driver.py o1` (`O1 PASS`, `/tmp/uatr8/o1.log`):**
  - Zero-AWS boot (`env -u AWS_*`, isolated `XDG_CONFIG_HOME=/tmp/uatr8/o1/.xdg`, `config.yaml` confirmed absent prior to `/model`).
  - `/context`: `Context — openai/gpt-6.1-sol` / `input tokens: 0 (0% of 1.05M)`.
  - Live `read` tool turn: returned `OPENAI_SENTINEL_15` and rendered Phase 15 cache-aware usage line `13.39K (1%, 49% cached) $0.02`.
  - `/cost`: rendered `Cost — openai/gpt-6.1-sol` / `turn 1: in 13.39K (6.62K cached, 6.68K write), out 51, $0.0181` / `Total: in 13.39K, out 51, $0.0181` / `Prices: LiteLLM bundled.` / `Display only — no budgets or enforcement.`.
  - `/model openai/gpt-6.1-terra`: switched cleanly (`Model: openai/gpt-6.1-terra — conversation continued (4 messages kept).`).
- **Live `python3 scripts/uattest/driver.py an1` (`AN1 PASS`, `/tmp/uatr8/an1.log`):**
  - Zero-AWS boot (`env -u AWS_*`, isolated `XDG_CONFIG_HOME=/tmp/uatr8/an1/.xdg`, `config.yaml` confirmed absent prior to `/model`).
  - `/context`: `Context — anthropic/claude-sonnet-5-5` / `input tokens: 0 (0% of 1.00M)`.
  - Live `read` tool turn: returned `ANTHROPIC_SENTINEL_15` and rendered Phase 15 normalized exclusive-usage cache-aware line `14.29K (1%, 49% cached) $0.02` (`Memory proposal` async dialogs cleanly dismissed via `_wait_idle_prompt()`).
  - `/cost`: rendered `Cost — anthropic/claude-sonnet-5-5` / `turn 1: in 14.29K (7.06K cached, 7.16K write), out 89, $0.0196` / `Total: in 14.29K, out 89, $0.0196` / `Prices: LiteLLM bundled.` / `Display only — no budgets or enforcement.`.
  - `/model anthropic/claude-haiku-5-5`: switched cleanly (`Model: anthropic/claude-haiku-5-5 — conversation continued (4 messages kept).`) with zero `Dropping reasoningContent` warnings.

## CI Gate Verification (After Final Code/Test Edit `3b8ab4f`)

- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **117 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> **passed** (`CC <= C 20`)
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken** (39 files, 84 dependencies)
- `/home/csaba/.local/bin/uv lock --check` -> **Resolved 156 packages**
- `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` (sandboxed) -> **1680 passed, 12 deselected**
- `.venv/bin/pytest tests/routing/test_routing.py -k "test_stub_server_systemone_decision_routes" -q` (`BypassSandbox: true`, loopback `127.0.0.1` bind) -> **1 passed** (**1681/1681** default suite green)
- `.venv/bin/pytest tests/rig/ -q` -> **42 passed**
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)

## Upstream Issues Filed on `strands-agents/harness-sdk`

- **OpenAI `_openai()` reasoning guard (`#17` / `MODEL-07`):** `https://github.com/strands-agents/harness-sdk/issues/6522` ([harness_issue_openai_reasoning_guard.md](../../../docs/upstream/harness_issue_openai_reasoning_guard.md))
- **Meta Model API (`api.meta.ai` / Muse) feature proposal (`#21` / Phase 16 `MODEL-09`):** `https://github.com/strands-agents/harness-sdk/issues/6521` ([harness_issue_meta_model_api.md](../../../docs/upstream/harness_issue_meta_model_api.md))
