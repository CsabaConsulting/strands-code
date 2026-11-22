---
phase: 14-first-class-google-gemini-provider-aware-startup
plan: 03
subsystem: uattest, docs, ci
tags: [gemini, uattest, quickstart, upstream-issue, ci-gates]
dependency_graph:
  requires: ["14-01", "14-02"]
  provides:
    - repeatable zero-AWS live-tmux UAT scenario driver.py g1 and rig contract tests
    - Quickstart guide for Google Gemini, Developer Program Ultra credits, and Vertex ADC
    - upstream issue draft for strands-harness Gemini 2.5 thinking_config
    - full 6-gate CI verification across all Phase 14 changes
  affects:
    - scripts/uattest/scenarios_gemini.py
    - scripts/uattest/driver.py
    - scripts/uattest/README.md
    - tests/rig/test_uattest_gemini.py
    - docs/QUICKSTART.md
    - docs/upstream/harness_issue_gemini25_thinking.md
tech_stack:
  added: []
  patterns:
    - "scenario_g1 strips AWS_* env vars, passes UV_NO_SYNC=1, isolates XDG_CONFIG_HOME, and verifies --model never creates config.yaml"
key_files:
  created:
    - scripts/uattest/scenarios_gemini.py
    - tests/rig/test_uattest_gemini.py
    - docs/upstream/harness_issue_gemini25_thinking.md
  modified:
    - scripts/uattest/driver.py
    - scripts/uattest/README.md
    - docs/QUICKSTART.md
decisions:
  - "Documented Google AI Pro ($10/mo), AI Ultra 5x ($40/mo), and AI Ultra 20x ($100/mo) Google Developer Program credits via aistudio.google.com while keeping consumer Gemini CLI OAuth unsupported."
metrics:
  completed: "2026-11-22"
---

# Phase 14 Plan 03: Repeatable `g1` Rig, Quickstart Docs & Full CI Verification Summary

## What Was Built

1. **Repeatable `driver.py g1` Live-Tmux UAT Scenario & Rig Tests (`D-07`):**
   - Added `tests/rig/test_uattest_gemini.py` (TDD first) pinning `RIG_GEMINI_FLASH`, `RIG_GEMINI_PRO`, zero-AWS `env -u AWS_*` posture, isolated `XDG_CONFIG_HOME`, session-scoped `--model`, `config.yaml` non-creation, `/context` (`1.05M`/`1.00M`), `GEMINI_SENTINEL_14`, `/cost`, and `/model` switch.
   - Created `scripts/uattest/scenarios_gemini.py`, wired `"g1": scenario_g1` into `scripts/uattest/driver.py`, and documented `g1` in `scripts/uattest/README.md`.
   - Live `driver.py g1` probe with ambient `GEMINI_API_KEY` booted cleanly with all `AWS_*` vars stripped (`[boot] seen`, `[prompt] seen`), verified `/context` (`gemini-2.5-flash` + `of 1.05M`), and reached the live GenAI endpoint before rejecting the non-production/invalid ambient `GEMINI_API_KEY` (`400 INVALID_ARGUMENT: API key not valid`). Full live turn execution remains a manual verification once an active AI Studio / Vertex key is supplied (`D-07`).

2. **Quickstart Docs & Upstream Gemini 2.5 Issue Draft (`D-07`, `D-08`):**
   - Updated `docs/QUICKSTART.md` (`First run` + `Optional providers`) covering provider-aware startup, session-scoped `--model`, `uv sync --extra gemini`, AI Studio API keys with Google AI Pro (\$10/mo) / AI Ultra 5x (\$40/mo) / AI Ultra 20x (\$100/mo) Developer Program credits, explicit exclusion of consumer Gemini CLI OAuth, and Vertex ADC with mutual-exclusion rules.
   - Created `docs/upstream/harness_issue_gemini25_thinking.md` documenting `strands_harness.models._gemini()` (`strands-harness==0.4.0`) passing `thinking_level` to `gemini-2.5-*` models and `_WEB_FETCH_MODELS["google"] = "gemini-3.5-flash"`.

## Full CI Gate Results (Standard `uv sync --locked --extra litellm`)

- `/home/csaba/.local/bin/uv lock --check`: **exit 0** (147 packages)
- `.venv/bin/pytest tests/ -q`: **1641 passed, 11 integration deselected** sandboxed + **1 passed** loopback test (`test_stub_server_systemone_decision_routes`) outside sandbox = **1642 passed, 0 failed**
- `.venv/bin/ruff check strands_code_cli tests scripts`: **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts`: **115 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts`: **exit 0**
- `.venv/bin/lint-imports`: **Contracts: 1 kept, 0 broken**
- `CLEANUP-01` & `git diff ee42ea2 -- strands_code_agent/`: **clean / empty (`D-24`)**
