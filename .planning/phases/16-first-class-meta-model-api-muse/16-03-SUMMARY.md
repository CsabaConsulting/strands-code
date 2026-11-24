---
phase: 16-first-class-meta-model-api-muse
plan: "03"
subsystem: testing, docs, upstream
tags: [uattest, tmux, meta, muse, gpt-6.2-sol, quickstart, harness-sdk-6521, ci]
requires:
  - phase: 16-01
    provides: Meta adapter, first_run helpers, 1.66.0/0.5.0 resync, openai/gpt-6.2-sol default
  - phase: 16-02
    provides: Multimodal Muse media scope, filtered discovery, and cache-aware contributor /cost
provides:
  - Repeatable scripts/uattest/scenarios_meta.py (scenario_m1) registered in driver.py ("m1") and pinned in tests/rig/test_uattest_meta.py
  - Updated RIG_OPENAI_PRIMARY to openai/gpt-6.2-sol in scenarios_openai_anthropic.py and rig contracts (44/44 rig tests green)
  - Live Meta catalog discovery (7 chat models) and live driver.py m1 execution (M1 PASS, /tmp/uatr8/m1.log)
  - Meta Model API (api.meta.ai / Muse) and OpenAI GPT-6.2 Sol documentation in docs/QUICKSTART.md
  - Held upstream empirical probe follow-up draft in docs/upstream/harness_comment_6521_meta_probe.md
affects: []
tech-stack:
  added: []
  patterns: [reused _run_provider_rig parameterized UAT flow for m1, held upstream comment draft with AI disclosure]
key-files:
  created:
    - scripts/uattest/scenarios_meta.py
    - tests/rig/test_uattest_meta.py
    - docs/upstream/harness_comment_6521_meta_probe.md
  modified:
    - scripts/uattest/scenarios_openai_anthropic.py
    - scripts/uattest/driver.py
    - scripts/uattest/README.md
    - tests/rig/test_uattest_openai_anthropic.py
    - docs/QUICKSTART.md
key-decisions:
  - "Reuse scenarios_openai_anthropic._run_provider_rig() cleanly in scenarios_meta.py for m1 so zero-AWS isolation, /context, sentinel read, /cost, and /model switch assertions stay DRY"
  - "Hold empirical api.meta.ai/v1 probe follow-up comment in docs/upstream/harness_comment_6521_meta_probe.md with HOLD BEFORE POSTING banner per upstream AI policy"
requirements-completed: [MODEL-09]
metrics:
  completed: "2026-11-24"
---

# Phase 16 Plan 03: Repeatable `driver.py m1` Rig, `QUICKSTART.md` Guide, Held `#6521` Probe Draft & Full CI Summary

**Delivered the repeatable `driver.py m1` Meta Model API live-tmux rig (verified live: `M1 PASS`), bumped OpenAI's UAT primary to `openai/gpt-6.2-sol`, updated `docs/QUICKSTART.md`, drafted the held empirical probe follow-up comment for `strands-agents/harness-sdk#6521`, and verified all 6 CI gates across the full codebase (`1705/1705` default suite + `44/44` rig tests green).**

## Changes Made
- **`scripts/uattest/scenarios_meta.py`, `scenarios_openai_anthropic.py`, `driver.py`, `README.md`, `tests/rig/test_uattest_meta.py`, `tests/rig/test_uattest_openai_anthropic.py`:**
  - Added `scenario_m1()` (`RIG_META_PRIMARY = "meta/muse-spark-1.3-contributor"`, `RIG_META_SECONDARY = "meta/muse-ember-1.0"`, `META_SENTINEL_16`, `of 1.05M`, `M1 PASS`), wired `"m1"` in `driver.py`, bumped `RIG_OPENAI_PRIMARY` to `"openai/gpt-6.2-sol"`, and pinned contracts offline in `tests/rig/` (**44 passed**).
- **Live Verification (`MODEL_API_KEY` from `.env`, AWS credentials stripped):**
  - `_discover_meta_models()` -> **`online=True`, 7 chat models** (`muse-ember-1.0`, `muse-wonder-1.0`, `muse-spark-1.3-contributor`, `muse-spark-1.3`, `muse-spark-1.2-contributor`, `muse-spark-1.2`, `muse-spark-1.1`), filtering out `muse-image-1.0`, `muse-voice-transcribe-1.0`, and `sam-3.1`.
  - `python3 scripts/uattest/driver.py m1` -> **`M1 PASS`** (`/tmp/uatr8/m1.log`): zero-AWS boot (`config.yaml` absent), `/context` `0 (0% of 1.05M)`, live `read` turn returned `META_SENTINEL_16` (`8.24K (1%) $0.00`), `/cost` rendered `in 8.24K, out 140, $0.0009` (`Prices: LiteLLM bundled.`), and `/model meta/muse-ember-1.0` kept `4` messages.
- **`docs/QUICKSTART.md` & `docs/upstream/harness_comment_6521_meta_probe.md`:**
  - Documented `--extra meta`, `MODEL_API_KEY` / `META_API_KEY` / `META_BASE_URL`, priority order `Google -> Anthropic -> OpenAI -> Meta -> OpenRouter -> Bedrock`, contributor ambient default vs standard/Wonder/Ember choices, empirically verified `/v1/responses` behavior, and updated OpenAI default to `openai/gpt-6.2-sol`.
  - Drafted held upstream empirical follow-up comment in `docs/upstream/harness_comment_6521_meta_probe.md` (`HOLD BEFORE POSTING` + AI disclosure).

## Verification
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **119 files already formatted**
- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> **passed**
- `.venv/bin/lint-imports` -> **Contracts: 1 kept, 0 broken**
- `/home/csaba/.local/bin/uv lock --check` -> **Resolved 156 packages**
- `.venv/bin/pytest tests/rig/ -q` -> **44 passed**
- `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` (sandboxed) -> **1704 passed, 12 deselected**
- `.venv/bin/pytest tests/routing/test_routing.py -k "test_stub_server_systemone_decision_routes" -q` (`BypassSandbox: true`, loopback `127.0.0.1` bind) -> **1 passed** (**1705/1705** default suite green)
- `git diff ee42ea2 -- strands_code_agent/` -> **empty** (`D-24`)
