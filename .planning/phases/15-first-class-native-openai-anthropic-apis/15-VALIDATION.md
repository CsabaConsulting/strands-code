---
phase: "15"
slug: "first-class-native-openai-anthropic-apis"
status: verified
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-23"
verified: "2026-11-24"
---

# Phase 15 — Validation Strategy

> Per-phase Nyquist validation contract for feedback sampling during Phase 15 execution (`MODEL-07`, `MODEL-08`).

---

## Test Infrastructure

| Property | Value |
| :--- | :--- |
| **Framework** | `pytest` (installed in `.venv`) via `/home/csaba/.local/bin/uv run pytest` or `.venv/bin/pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `.venv/bin/pytest tests/entry/ tests/dispatch/test_cli_entry.py tests/model/test_model_switch.py tests/cost/ tests/routing/test_routing.py tests/loop/test_btw.py tests/rig/ -q` |
| **Full suite command** | `.venv/bin/pytest tests/ -q` |
| **Static / complexity gates** | `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check` |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` verification command (`< 20s`).
- **After every plan wave:** Run `.venv/bin/pytest tests/ -q` + `ruff check` + `ruff format --check` + `xenon --max-absolute C` + `lint-imports`.
- **Before `/gsd-verify-work 15`:** All 6 CI workflow checks from `.github/workflows/gates.yml` must pass cleanly (`strands_code_agent/` diff empty).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Decision / Anchor | Secure / Correct Behavior | Test Type | Automated Command | File Exists | Status |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `15-01-T1` | 01 | 1 | `MODEL-07`, `MODEL-08` | `D-01`, `D-06`, `D-07` | `pyproject.toml` declares `openai` (`openai>=2.0.0`) & `anthropic` extras, `uv.lock` resolves, `_SDK_EXTRA_HINTS` maps both, `first_run.has_openai_credentials`/`has_anthropic_credentials` check presence only, `_AMBIENT_DEFAULT_MODELS` bumped to `claude-sonnet-5-5` & `gpt-6.1-sol`, hermetic uninstallable test | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/dispatch/test_cli_entry.py tests/entry/test_first_run.py tests/model/test_model_switch.py -k "cli_entry or first_run or uninstallable" -q` | ✅ | ✅ green (`27bedc5`) |
| `15-01-T2` | 01 | 1 | `MODEL-07`, `MODEL-08` | `D-02`, `D-04` | `resolve_harness_model` preserves `caching=True, caching_explicit=False` & native `web_search` on `apply_switch` and `_route_side_spawn`; `ProviderConfig.api_mode` (`responses`/`chat`) + `model_for_config` keeps strings for harness goodies + post-applies `base_url` + pins `web_fetch` | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/entry/ tests/model/test_model_switch.py tests/routing/test_routing.py tests/loop/test_btw.py tests/cost/test_cost_context.py -k "not stub" -q` | ✅ | ✅ green (`27bedc5`, 581 passed) |
| `15-02-T1` | 02 | 2 | `MODEL-07`, `MODEL-08` | `D-03`, `D-06` | Inclusive vs exclusive `inputTokens` normalization in `record_turn_metrics`, cache-discounted spend + compact suffix in `usage_line` & `cost_report` (zero-cache byte-identical), bare-tail `litellm_entry` + `cache_read`/`cache_write`, 24h `anthropic-models.json` cache feeding `window_for()`, `SummaryBlock` token counting | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/cost/ tests/loop/test_btw.py tests/model/test_model_switch.py -k "cost or pricing or usage or estimate_messages or no_budgets or no_credential" -q` | ✅ | ✅ green (`15d98a4`, 339 passed) |
| `15-02-T2` | 02 | 2 | `MODEL-07`, `MODEL-08` | `D-05`, `D-06`, `D-07` | `same_provider()` gates signed `reasoningContent` round-trips across `anthropic/` <-> `bedrock/anthropic.*` with `RichHistory` stash/restore; `SummaryBlock` conversion & hash/btw safety; `_vendor_family` grouping for `claude-*`/`gpt-*`/`o1`/`o3`/`o4-*`; `configure_openai_for_model` guards non-reasoning & effort-subset OpenAI models across 4 sites | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/model/test_model_switch.py tests/loop/test_btw.py tests/loop/test_loop_routing.py tests/cost/test_cost_context.py -k "same_vendor or same_provider or summary or vendor_family or configure_openai or rich or no_budgets" -q` | ✅ | ✅ green (`15d98a4`, 401 passed) |
| `15-02-T3` | 02 | 2 | `MODEL-07`, `MODEL-08` | `D-06` | Credential-gated `openai.OpenAI().models.list()` (filtered to Responses chat models) & `anthropic.Anthropic().models.list()` (persisting `/v1/models` metadata + retiring labels), offline fallbacks only when keyed, zero unkeyed leakage | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/model/test_model_switch.py tests/cost/test_cost_context.py -k "discover or route_label or model_tree or no_credential" -q` | ✅ | ✅ green (`15d98a4`, 1677 passed) |
| `15-03-T1` | 03 | 3 | `MODEL-07`, `MODEL-08` | `D-08` | Repeatable `driver.py o1` & `driver.py an1` scenarios in `scripts/uattest/scenarios_openai_anthropic.py` (zero-AWS `env -u AWS_*`, isolated `XDG_CONFIG_HOME`) + offline rig contract tests (`tests/rig/test_uattest_openai_anthropic.py`) | rig contract | `.venv/bin/pytest tests/rig/ -q && .venv/bin/ruff check scripts/uattest tests/rig && .venv/bin/xenon --max-absolute C scripts/uattest tests/rig` | ✅ | ✅ green (`eeceb59`, `b102735`, `3b8ab4f`, 42 passed) |
| `15-03-T2` | 03 | 3 | `MODEL-07`, `MODEL-08` | `D-07`, `D-08` + Gates | `docs/QUICKSTART.md` OpenAI & Anthropic guides + mannerisms, held `docs/upstream/harness_issue_openai_reasoning_guard.md`, and all 6 CI gates (`pytest`, `ruff`, `xenon`, `lint-imports`, `uv lock --check`, `strands_code_agent/` clean) | full suite + CI gates | `.venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports && .venv/bin/pytest tests/ -q && git diff ee42ea2 -- strands_code_agent/` | ✅ | ✅ green (**1681/1681** default suite) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing test infrastructure covers Plans `15-01` and `15-02`; `tests/rig/test_uattest_openai_anthropic.py` is created TDD-first in Plan `15-03` Task 1 (`15-03-T1`).

---

## Manual / Opportunistic Live Verifications

| Behavior | Requirement | Why Live Creds Required | Test Instructions | Status |
| :--- | :--- | :--- | :--- | :--- |
| Live native OpenAI `openai/gpt-6.1-sol` zero-AWS launch, tool turn, `/context`, `/cost`, and `/model openai/gpt-6.1-terra` switch (`driver.py o1`) | `MODEL-07` | Requires `OPENAI_API_KEY` (+ `--extra openai`) | `python3 scripts/uattest/driver.py o1` | ✅ `O1 PASS` (`/tmp/uatr8/o1.log`; 49% cached, `\$0.0181`) |
| Live native Anthropic `anthropic/claude-sonnet-5-5` zero-AWS launch, tool turn, `/context`, `/cost`, and `/model anthropic/claude-haiku-5-5` switch (`driver.py an1`) | `MODEL-08` | Requires `ANTHROPIC_API_KEY` (+ `--extra anthropic`) | `python3 scripts/uattest/driver.py an1` | ⚠️ blocked on external Anthropic billing credits (live `/v1/models` 15 models PASS, boot + `1.00M` `/context` + `api.anthropic.com` auth PASS) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with TDD / automated verification
- [x] Wave 0 gaps identified (`test_uattest_openai_anthropic.py` in `15-03-T1`)
- [x] No watch-mode flags
- [x] Fast feedback latency (< 20s per task)
- [x] `nyquist_compliant: true` set in frontmatter
