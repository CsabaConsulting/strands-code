---
phase: 15-first-class-native-openai-anthropic-apis
plan: "03"
subsystem: rig, docs, upstream
tags: [openai, anthropic, uattest, quickstart, upstream-draft, ci-gates]
requires:
  - phase: 15-02
    provides: cache-aware /cost, same-provider thinking gating, OpenAI reasoning guard, live discovery
provides:
  - Repeatable zero-AWS live-tmux UAT scenarios o1 and an1 (scripts/uattest/scenarios_openai_anthropic.py) wired into driver.py and scripts/uattest/README.md
  - Offline hermetic rig contract tests (tests/rig/test_uattest_openai_anthropic.py) keeping a1/a2 CodeAct intact
  - Updated docs/QUICKSTART.md covering Native OpenAI & Anthropic setup, custom base_url + api_mode, cache-aware /cost, and provider mannerisms
  - Held upstream bug report draft docs/upstream/harness_issue_openai_reasoning_guard.md with HOLD BEFORE PUBLISHING notice
  - All 6 blocking CI gates verified green and empty strands_code_agent/ diff
affects: []
tech-stack:
  added: []
  patterns: [shared _run_provider_rig zero-AWS UAT fixture, held upstream issue draft wrapper]
key-files:
  created:
    - scripts/uattest/scenarios_openai_anthropic.py
    - tests/rig/test_uattest_openai_anthropic.py
    - docs/upstream/harness_issue_openai_reasoning_guard.md
  modified:
    - scripts/uattest/driver.py
    - scripts/uattest/README.md
    - docs/QUICKSTART.md
key-decisions:
  - "Wire native OpenAI and Anthropic live-tmux scenarios at driver.py slots o1 and an1, leaving a1/a2 CodeAct intact (D-08)"
  - "Hold docs/upstream/harness_issue_openai_reasoning_guard.md locally behind HOLD BEFORE PUBLISHING per team/AI_USAGE_POLICY.md (D-07)"
requirements-completed: [MODEL-07, MODEL-08]
metrics:
  completed: "2026-11-24"
---

# Phase 15 Plan 03: Repeatable `driver.py o1`/`an1` UAT Rigs, `QUICKSTART.md` Guides, Held Upstream Draft & CI Gates Summary

**Added zero-AWS `o1`/`an1` live-tmux UAT scenarios and offline rig contract tests, documented native OpenAI & Anthropic workflows in `docs/QUICKSTART.md`, drafted the held upstream OpenAI reasoning-guard bug report, and verified all 6 blocking CI gates.**

## Changes Made
- **`scripts/uattest/scenarios_openai_anthropic.py`, `scripts/uattest/driver.py`, `scripts/uattest/README.md`:**
  - Implemented shared `_run_provider_rig(...)`, `scenario_o1()` (`openai/gpt-6.1-sol` -> `openai/gpt-6.1-terra`), and `scenario_an1()` (`anthropic/claude-sonnet-5-5` -> `anthropic/claude-haiku-5-5`) stripping all `AWS_*` env vars under isolated `XDG_CONFIG_HOME`, verifying absent `config.yaml`, `/context`, a `read` tool turn (`OPENAI_SENTINEL_15` / `ANTHROPIC_SENTINEL_15`), `/cost`, and same-provider `/model` switches.
  - Registered `"o1"` and `"an1"` in `scripts/uattest/driver.py` (preserving `"a1"`, `"a2"`, `"g1"` intact) and updated `scripts/uattest/README.md`.
- **`tests/rig/test_uattest_openai_anthropic.py`:** Pinned hermetic offline contract assertions covering `driver.py` dispatch, model constants, AWS/XDG isolation, `/context`, `/cost`, and pass markers without running `tmux` in pytest.
- **`docs/QUICKSTART.md`:** Updated ambient defaults (`anthropic/claude-sonnet-5-5`, `openai/gpt-6.1-sol`), `--extra openai` / `--extra anthropic` install instructions, dedicated **OpenAI (zero AWS required)** and **Anthropic (zero AWS required)** sections (`base_url`, `api_mode: chat`, `configure_openai_for_model`, `use_native_token_count`, `anthropic-version: 2026-10-21`, `SummaryBlock`, upstream `#3389`), and cache-aware `/cost` docs.
- **`docs/upstream/harness_issue_openai_reasoning_guard.md`:** Captured the verified `strands-harness 0.4.0` reproduction of `_openai()` emitting `reasoning.effort` on `gpt-4o`/`gpt-4.1-mini` and forwarding unsupported effort values on `o3`/`gpt-5`/`gpt-6.1-sol` under `HOLD BEFORE PUBLISHING`.

## Verification (All 6 Blocking CI Gates)
- `.venv/bin/ruff check strands_code_cli tests scripts` -> passed
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **117 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> passed
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken**
- `/home/csaba/.local/bin/uv lock --check` -> **Resolved 156 packages**
- `.venv/bin/pytest tests/ -q` (sandboxed: **1679 passed**, loopback stub blocked only on `127.0.0.1` bind; standalone `.venv/bin/pytest tests/routing/test_routing.py -k "test_stub_server_systemone_decision_routes" -q` with `BypassSandbox: true`: **1 passed** -> **1680/1680 default suite tests green**, 11 `integration`-marked deselected)
- `.venv/bin/pytest tests/rig/ -q` -> **41 passed**
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
