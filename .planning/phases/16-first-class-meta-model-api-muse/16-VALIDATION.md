---
phase: "16"
slug: "first-class-meta-model-api-muse"
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-24"
validated: "2026-11-24"
---

# Phase 16 — Validation Strategy

> Per-phase Nyquist validation contract for feedback sampling during Phase 16 execution (`MODEL-09`).

---

## Test Infrastructure

| Property | Value |
| :--- | :--- |
| **Framework** | `pytest` (installed in `.venv`) via `/home/csaba/.local/bin/uv run pytest` or `.venv/bin/pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `.venv/bin/pytest tests/model/test_model_switch.py tests/entry/test_first_run.py tests/dispatch/test_cli_entry.py tests/cost/ tests/loop/test_btw.py tests/rig/ -k "not test_stub_server_systemone_decision_routes" -q` |
| **Full suite command** | `.venv/bin/pytest tests/ -q` |
| **Static / complexity gates** | `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check` |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted verification command (`< 25s`).
- **After every plan wave:** Run `.venv/bin/pytest tests/ -q` + `ruff check` + `ruff format --check` + `xenon --max-absolute C` + `lint-imports`.
- **Before `/gsd-verify-work 16`:** All 6 CI workflow checks must pass cleanly (`strands_code_agent/` diff empty).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Decision / Anchor | Secure / Correct Behavior | Test Type | Automated Command | File Exists | Status |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `16-01-T1` | 01 | 1 | `MODEL-09` | `D-01`, `D-02`, `D-03`, `D-05` | Resync `pyproject.toml`/`uv.lock` onto `strands-agents>=1.66.0` (`1.66.0`) & `strands-harness>=0.5.0` (`0.5.0`), retire `_gpt_62_model_info_fallback()`, bump OpenAI ambient default to `openai/gpt-6.2-sol`, adapt `0.5.0` `#4683` (`AnthropicModel` on Bedrock) & `#5997` (`_web_search_kind`), add `meta` extra + `_SDK_EXTRA_HINTS["meta"]`, `first_run` `has_meta_credentials`/`meta_api_key`/`meta_base_url` + priority order, and `conftest.py` scrubbing | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/dispatch/test_cli_entry.py tests/entry/test_first_run.py tests/model/test_model_switch.py -k "meta or gpt_62 or bedrock or first_run or uninstallable" -q` | ✅ | ✅ green (`cc99d5a`) |
| `16-01-T2` | 01 | 1 | `MODEL-09` | `D-04` | Thin auto-retiring `meta/` adapter (`build_meta_model()`, `upstream_supports_meta()`, `_meta_model_info()` `prompt_caching="auto"`, plain `CacheConfig()`, omitted `reasoning` on `"none"`/`"off"`, `web_search` tool, `_strands_model_ref`) wired across `model_for_config()`, `build_agent()`, `_model_message()`, `apply_switch()`, `_route_side_spawn()`, and `build_btw_agent()` (`caching=False`) | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/entry/ tests/dispatch/test_cli_entry.py tests/model/test_model_switch.py tests/routing/test_routing.py tests/loop/test_btw.py tests/loop/test_loop_routing.py tests/cost/test_cost_context.py -k "not test_stub_server_systemone_decision_routes" -q` | ✅ | ✅ green (`cc99d5a`, `612 passed, 6 deselected`) |
| `16-02-T1` | 02 | 2 | `MODEL-09` | `D-06` | Narrow `_MEDIA_LESS` to `bedrock/meta/llama3|llama4` (keeping multimodal `supports_media == True` for `meta/muse-*`), `("meta", "muse")` `_vendor_family()` grouping, credential-gated `_discover_meta_models()` filtering non-chat tokens (`muse-image-*`, `muse-voice-transcribe-*`, `sam-*`), offline curated fallback, zero unkeyed leakage | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/model/test_model_switch.py -k "meta or muse or llama" -q` | ✅ | ✅ green (`4857960`) |
| `16-02-T2` | 02 | 2 | `MODEL-09` | `D-07` | LiteLLM bare/meta key lookup (`_litellm_keys`), static fallbacks (`muse-spark-*-contributor`, `muse-spark-*`, `muse-wonder-1.0`, `muse-ember-1.0`, `1_048_576` window), `50×` contributor cache rates (`_default_cache_rates()`), inclusive Meta usage accounting (`_extract_prompt_usage`), and `LLM_...`/`LLM\|...` scrubbing in `scrub_credentials()` | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/cost/ tests/model/test_model_switch.py -k "not test_stub_server_systemone_decision_routes" -q` | ✅ | ✅ green (`4857960`, `316 passed, 1 deselected`) |
| `16-03-T1` | 03 | 3 | `MODEL-09` | `D-08` | Repeatable `driver.py m1` scenario (`scripts/uattest/scenarios_meta.py`), bumped `RIG_OPENAI_PRIMARY` to `openai/gpt-6.2-sol`, offline rig contracts (`tests/rig/test_uattest_meta.py`, `test_uattest_openai_anthropic.py`), and live `api.meta.ai/v1` `m1` verification (`M1 PASS`) | rig contract + live tmux UAT | `.venv/bin/pytest tests/rig/ -q && .venv/bin/ruff check scripts/uattest tests/rig && .venv/bin/xenon --max-absolute C scripts/uattest tests/rig` | ✅ | ✅ green (`44b9aa4`, `44 passed`) |
| `16-03-T2` | 03 | 3 | `MODEL-09` | `D-07`, `D-08` + Gates | [QUICKSTART.md](file:///home/csaba/repos/AWS/strands-code/docs/QUICKSTART.md) Meta & GPT-6.2 Sol guides, held empirical `#6521` probe notes, and all 6 CI gates (`pytest`, `ruff`, `xenon`, `lint-imports`, `uv lock --check`, `strands_code_agent/` clean) | full suite + CI gates | `.venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports && .venv/bin/pytest tests/ -q && git diff ee42ea2 -- strands_code_agent/` | ✅ | ✅ green (`44b9aa4`, `1705/1705` default suite) |
| `16-UAT-T1` | uat | 4 | `MODEL-09` | `D-01`..`D-08` | Applied live `strands-agents/harness-sdk#6521` title/body revision (`aab271f`) and full 6/6 conversational & live UAT (`16-UAT.md`): zero-AWS auto-pick (`run_uat16_test1.py`), `driver.py m1` (`M1 PASS`) & `driver.py o1` (`O1 PASS`), live 7-model Meta discovery (`run_uat16_test3.py`), live `effort="none"` & `/btw` (`run_uat16_test4.py`), `QUICKSTART.md`/`#6521` review, and all 6 CI gates | live UAT + CI gates | `python3 scripts/uattest/driver.py m1 && python3 scripts/uattest/driver.py o1` + `16-UAT.md` | ✅ | ✅ green (`2247b47`, `6/6 PASS`) |
| `16-SEC-T1` | sec | 4 | `MODEL-09` | `T-16-02`..`T-16-04` | ASVS L1 audit (`16-SECURITY.md`, `10/10 closed`, `threats_open: 0`): `_meta_openai_client_args()` isolating all 6 `OPENAI_*` env vars & `OpenAI-*` tenant headers from Meta/custom proxies, `_validate_base_url()` in `configure_base_url_for_model()`, `_has_unsafe_model_chars()` guard on Meta IDs, bounded `timeout=5.0, max_retries=0` discovery, widened `LLM_`/`LLM\|` regex, and `MODEL_API_KEY` canary leakage test | security unit + CI gates | `.venv/bin/pytest tests/model/test_model_switch.py tests/entry/test_first_run.py tests/cost/test_cost_context.py -k "not test_stub_server_systemone_decision_routes" -q` | ✅ | ✅ green (`4d32cbc`, `1706/1706` default suite) |
| `16-VAL-T1` | val | 4 | `MODEL-09` | `D-02`..`D-07` | Nyquist edge branch coverage (zero runtime changes): `_is_meta_chat_model` `None`/blank/control chars, `_normalize_meta_effort` `auto`/`MINIMAL`/`ultra`, `_discover_meta_models` filtered-empty & `RuntimeError` fallbacks, `upstream_supports_meta` `ImportError`, `build_meta_model` non-meta/empty & `web_search=False, caching=False`, `configure_base_url_for_model` overwrite vs preserve, `resolve_harness_model` `_web_search_kind` (`agentcore`/`native`/`None`), `entry_main.model_for_config` `ImportError` & string `web_fetch`, explicit `meta/` `META_BASE_URL` exit `2` vs explicit `base_url`, `_model_message` invalid value & `upstream_supports_meta=True` auto-retire, `muse-spark-1.2-contributor`/`1.1` rates & `muse-spark-1.3` LiteLLM keys, and `/btw` foreign `_base_url_provider` isolation | unit (Nyquist) | `.venv/bin/pytest tests/model/test_model_switch.py tests/entry/test_first_run.py tests/dispatch/test_cli_entry.py tests/cost/ tests/loop/test_btw.py tests/rig/ -k "not test_stub_server_systemone_decision_routes" -q` (`488 passed, 2 deselected`) + full suite | ✅ | ✅ green (**1711/1711** default suite + **44/44** rig) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing test infrastructure covers Plans `16-01` and `16-02`; `tests/rig/test_uattest_meta.py` is created TDD-first in Plan `16-03` Task 1 (`16-03-T1`).

---

## Manual / Opportunistic Live Verifications

| Behavior | Requirement | Why Live Creds Required | Test Instructions | Status |
| :--- | :--- | :--- | :--- | :--- |
| Live Meta Model API `meta/muse-spark-1.3-contributor` zero-AWS launch, `read` tool turn, `/context`, `/cost`, and `/model meta/muse-ember-1.0` switch (`driver.py m1`) | `MODEL-09` | Requires `MODEL_API_KEY` or `META_API_KEY` (+ `--extra meta`) | `python3 scripts/uattest/driver.py m1` | ✅ `M1 PASS` (`/tmp/uatr8/m1.log`; `0% of 1.05M`, `META_SENTINEL_16`, `\$0.0009`, `4 messages kept`) |
| Live OpenAI `openai/gpt-6.2-sol` zero-AWS regression launch, `read` tool turn, `/context`, `/cost`, and `/model openai/gpt-6.1-terra` switch (`driver.py o1`) | `MODEL-07`, `MODEL-09` | Requires `OPENAI_API_KEY` (+ `--extra openai`) | `python3 scripts/uattest/driver.py o1` | ✅ `O1 PASS` (`/tmp/uatr8/o1.log`; `0% of 1.05M`, `OPENAI_SENTINEL_15`, `49% cached`, `\$0.0185`, `4 messages kept`) |
| Live Meta `/v1/models` discovery, non-chat asset exclusion, and `("meta", "muse")` grouping (`run_uat16_test3.py`) | `MODEL-09` | Requires `MODEL_API_KEY` | Run `discover_models()` with competing creds stripped | ✅ `TEST 3 PASS` (`offline=False`, `7` chat models, `muse-image-1.0`/`muse-voice-transcribe-1.0`/`sam-3.1` excluded, `1_048_576` window) |
| Live `effort="none"` (`Agent`) + `/btw` side turn via `build_btw_agent()` (`run_uat16_test4.py`) | `MODEL-09` | Requires `MODEL_API_KEY` | Run live `Agent(effort="none")` and `build_btw_agent()` against `api.meta.ai/v1` | ✅ `TEST 4 PASS` (`'7'`, `0` `UserWarning`s, live `/btw` `'ORION'`) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with TDD / automated verification
- [x] Wave 0 gaps identified (`test_uattest_meta.py` in `16-03-T1`)
- [x] No watch-mode flags
- [x] Fast feedback latency (< 25s per targeted verification run)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-11-24 (`1710 passed, 12 deselected` sandboxed + standalone loopback stub `1 passed` = **1711 passed, 0 failed**; `tests/rig/` **44 passed**; `ruff check`, `ruff format --check` `119 files`, `xenon --max-absolute C`, `lint-imports` `1 kept / 0 broken`, `uv lock --check` `156 packages` all green; `git diff ee42ea2 -- strands_code_agent/` empty; `16-UAT.md` `6/6 PASS`; `16-SECURITY.md` `10/10 closed`)
