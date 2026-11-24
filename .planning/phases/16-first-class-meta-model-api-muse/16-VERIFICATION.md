---
phase: 16-first-class-meta-model-api-muse
status: passed
score: 7/7
verified: "2026-11-24"
requirements:
  - MODEL-09
commits:
  - cc99d5a
  - 4857960
  - 44b9aa4
---

# Phase 16 Verification: First-Class Meta Model API (`api.meta.ai` / Muse) & Upstream Enablement (`MODEL-09`)

**Status:** Passed (`7/7` must-have truths verified + empirical live `https://api.meta.ai/v1` probe + live `_discover_meta_models()` + live `driver.py m1` `M1 PASS`)  
**Verified:** 2026-11-24 on branch `main`

## Truth-by-Truth Verification Matrix

| # | Decision / Truth | Evidence (Code & Tests) | Observed Status |
|---|---|---|---|
| 1 | `D-04`, `D-08`: Live empirical protocol probe against `https://api.meta.ai/v1` (`GET /v1/models`, `prompt_cache_key` vs `prompt_cache_options` HTTP 400, `[minimal..max]` effort vs `"none"` HTTP 400, native `web_search`, multimodal `input_image` on Spark/Wonder/Ember, `1,426`-byte encrypted replay, `/v1/messages` auth nuance) & held follow-up draft for `#6521` | [16-RESEARCH.md](16-RESEARCH.md), [harness_comment_6521_meta_probe.md](../../../docs/upstream/harness_comment_6521_meta_probe.md) (`HOLD BEFORE POSTING` + AI disclosure) | ✅ Verified |
| 2 | `D-05`: Intentional upstream resync to `strands-agents>=1.66.0` (`1.66.0`) & `strands-harness>=0.5.0` (`0.5.0`), retire `_gpt_62_model_info_fallback()`, bump `_AMBIENT_DEFAULT_MODELS["openai"]` to `openai/gpt-6.2-sol`, adapt `0.5.0` `#4683` & `#5997` deltas (`_web_search_kind` native gating) | `pyproject.toml`, `uv.lock`, `strands_code_cli/entry/first_run.py`, `strands_code_cli/model/model_switch.py`, `tests/model/test_model_switch.py::TestResolveSpike` & `TestSameProviderSummaryAndOpenAIGuard`, `cc99d5a` | ✅ Verified |
| 3 | `D-01`, `D-02`, `D-03`: `meta` optional extra (`strands-agents[openai]`, `openai>=2.0.0`), `_SDK_EXTRA_HINTS["meta"]`, `first_run` `has_meta_credentials()` / `meta_api_key()` (`MODEL_API_KEY` primary, `META_API_KEY` fallback) / `meta_base_url()` (validated `META_BASE_URL`), ambient default `meta/muse-spark-1.3-contributor` ordered `Google -> Anthropic -> OpenAI -> Meta -> OpenRouter -> Bedrock` | `pyproject.toml`, `strands_code_cli/dispatch/core.py`, `strands_code_cli/entry/first_run.py`, `tests/conftest.py`, `tests/dispatch/test_cli_entry.py`, `tests/entry/test_first_run.py`, `tests/cost/test_cost_context.py::TestLoopUsageWiring::test_no_credential_persistence_sinks` | ✅ Verified |
| 4 | `D-04`: Thin auto-retiring `meta/` adapter (`build_meta_model()`, `upstream_supports_meta()`, `model_id_of` `_strands_model_ref`, `CacheConfig()` without `strategy="auto"`, `prompt_caching="auto"`, omitted `reasoning` on `"none"`/`"off"`, `web_search` tool) across startup, `/model`, `/route`, and `/btw` | `strands_code_cli/model/model_switch.py`, `strands_code_cli/entry/main.py`, `strands_code_cli/dispatch/core.py`, `strands_code_cli/loop/btw.py`, `tests/model/test_model_switch.py::TestMetaModelAdapter`, `tests/loop/test_btw.py` | ✅ Verified |
| 5 | `D-06`: `_MEDIA_LESS` Bedrock Llama scoping (`supports_media == True` across Muse Spark/Wonder/Ember; Llama stays text-only), `("meta", "muse")` `_vendor_family()` grouping, filtered `GET /v1/models` `_discover_meta_models()` (`muse-image-*`/`muse-voice-transcribe-*`/`sam-*` excluded; zero unkeyed leak) | `strands_code_cli/model/model_switch.py`, `tests/model/test_model_switch.py::TestMetaModelAdapter` + live `_discover_meta_models()` (`online=True`, 7 chat models) | ✅ Verified |
| 6 | `D-07`: LiteLLM bare/meta lookup (`_litellm_keys`), static fallbacks (`muse-ember-1.0`, `muse-spark-*`, `muse-wonder-1.0`, `1_048_576` window), 50× contributor cache rates, inclusive usage accounting (`_extract_prompt_usage`), and `LLM_...`/`LLM\|...` credential scrubbing (`scrub_credentials()`) | `strands_code_cli/cost/live_pricing.py`, `strands_code_cli/cost/cost_context.py`, `tests/cost/test_live_pricing.py`, `tests/cost/test_cost_context.py` | ✅ Verified |
| 7 | `D-04`, `D-08`, `D-24`: Repeatable `driver.py m1` tmux UAT rig (`OPENAI_PRIMARY` → `gpt-6.2-sol`) + `tests/rig/` (**44 passed**), live `driver.py m1` **`M1 PASS`**, `docs/QUICKSTART.md` guide, and pristine `strands_code_agent/` | `scripts/uattest/*`, `tests/rig/test_uattest_meta.py`, `tests/rig/test_uattest_openai_anthropic.py`, `docs/QUICKSTART.md`, `/tmp/uatr8/m1.log` (`M1 PASS`), `git diff ee42ea2 -- strands_code_agent/` empty | ✅ Verified |

## Live Verification Results (With `MODEL_API_KEY` from `.env`, AWS Stripped)

- **Live `_discover_meta_models()` (`BypassSandbox: true`):** Returned **`online=True`**, **7** Meta Muse chat/reasoning models (`meta/muse-ember-1.0`, `meta/muse-wonder-1.0`, `meta/muse-spark-1.3-contributor`, `meta/muse-spark-1.3`, `meta/muse-spark-1.2-contributor`, `meta/muse-spark-1.2`, `meta/muse-spark-1.1`), excluding non-chat assets (`muse-image-1.0`, `muse-voice-transcribe-1.0`, `sam-3.1`).
- **Live `python3 scripts/uattest/driver.py m1` (`M1 PASS`, `/tmp/uatr8/m1.log`):**
  - Zero-AWS boot (`env -u AWS_*`, isolated `XDG_CONFIG_HOME=/tmp/uatr8/m1/.xdg`, `config.yaml` confirmed absent prior to `/model`).
  - `/context`: `Context — meta/muse-spark-1.3-contributor` / `input tokens: 0 (0% of 1.05M)`.
  - Live `read` tool turn: returned `META_SENTINEL_16` and rendered `8.24K (1%) $0.00`.
  - `/cost`: rendered `Cost — meta/muse-spark-1.3-contributor` / `turn 1: in 8.24K, out 140, $0.0009` / `Prices: LiteLLM bundled.` / `Display only — no budgets or enforcement.`.
  - `/model meta/muse-ember-1.0`: switched cleanly (`Model: meta/muse-ember-1.0 — conversation continued (4 messages kept).`).

## CI Gate Verification (After Wave 3 Final Code & Docs Commit `44b9aa4`)

- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **119 files already formatted**
- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> **passed** (`CC <= C 20`)
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken** (39 files, 86 dependencies)
- `/home/csaba/.local/bin/uv lock --check` -> **Resolved 156 packages** (`strands-agents==1.66.0`, `strands-harness==0.5.0`)
- `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` (sandboxed) -> **1704 passed, 12 deselected**
- `.venv/bin/pytest tests/routing/test_routing.py -k "test_stub_server_systemone_decision_routes" -q` (`BypassSandbox: true`, loopback `127.0.0.1` bind) -> **1 passed** (**1705/1705** default suite green)
- `.venv/bin/pytest tests/rig/ -q` -> **44 passed**
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
