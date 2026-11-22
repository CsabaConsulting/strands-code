---
phase: 14-first-class-google-gemini-provider-aware-startup
status: passed
score: 8/8
verified: "2026-11-22"
requirements:
  - MODEL-06
commits:
  - 947c5a7
  - 52b0963
  - a2395d4
---

# Phase 14 Verification: First-Class Google Gemini & Provider-Aware Startup (`MODEL-06`)

**Status:** Passed (`8/8` must-have truths verified)  
**Verified:** 2026-11-22 on branch `main` (`947c5a7`, `52b0963`, `a2395d4`)

## Truth-by-Truth Verification Matrix

| # | Decision / Truth | Evidence (Code & Tests) | Observed Status |
|---|---|---|---|
| 1 | `D-01`: `gemini` optional extra & `_SDK_EXTRA_HINTS["google"] = "gemini"` | `pyproject.toml`, `uv.lock` (`147` packages, `uv lock --check` exit `0`), `strands_code_cli/dispatch/core.py`, `tests/dispatch/test_cli_entry.py` (`TestSdkHints`, `34 passed`) | ✅ Verified |
| 2 | `D-02`, `D-03`: Box-compatible provider-aware startup preflight, Vertex mutual-exclusion & project gate, ambient auto-pick, session-scoped `--model`, all `os.environ` reads isolated in `entry/first_run.py` | `strands_code_cli/entry/first_run.py`, `strands_code_cli/entry/main.py`, `tests/conftest.py`, `tests/entry/test_first_run.py`, `tests/entry/test_session_resume.py`, `tests/cost/test_cost_context.py::TestLoopUsageWiring::test_no_credential_persistence_sinks` (`137 passed`) | ✅ Verified |
| 3 | `D-04`: `supports_reasoning("google/...")` + cross-vendor `toolUse["reasoningSignature"]` stripping (verifying `LiteLLMModel.format_request_message_tool_call`), `RichHistory` / `canonical_prefix_hash` preserve/restore, `_vendor_family` decimal dot fix | `strands_code_cli/model/model_switch.py`, `strands_code_cli/loop/core.py`, `tests/model/test_model_switch.py` (`TestGeminiCrossProviderSafety`) | ✅ Verified |
| 4 | `D-07`: `configure_gemini_for_model()` rewrites Gemini-3 `thinking_level` to `thinking_budget` on Gemini 2.5 across `apply_switch`, `build_agent`, `_route_side_spawn`, and `build_btw_agent` + upstream issue draft | `strands_code_cli/model/model_switch.py`, `strands_code_cli/entry/main.py`, `strands_code_cli/loop/core.py`, `strands_code_cli/loop/btw.py`, `docs/upstream/harness_issue_gemini25_thinking.md`, `tests/model/test_model_switch.py`, `tests/loop/test_btw.py` (`324 passed` across model/btw/cost) | ✅ Verified |
| 5 | `D-05`: Credential-gated `google.genai.Client().models.list()` discovery merged with Bedrock + `CURATED_GEMINI_MODELS` fallback only when `has_google_credentials()` is True | `strands_code_cli/model/model_switch.py`, `tests/model/test_model_switch.py` (`TestDiscoverModels`) | ✅ Verified |
| 6 | `D-06`: `live_pricing.litellm_entry` `gemini/<tail>` + `<tail>` keys, curated Gemini `MODEL_PRICING` / `MODEL_LIMITS`, and Bedrock Price List skip for non-Bedrock direct routes | `strands_code_cli/cost/live_pricing.py`, `strands_code_cli/cost/cost_context.py`, `tests/cost/test_live_pricing.py`, `tests/cost/test_cost_context.py` | ✅ Verified |
| 7 | `D-07`: Repeatable zero-AWS `driver.py g1` scenario & rig contract tests | `scripts/uattest/scenarios_gemini.py`, `scripts/uattest/driver.py`, `scripts/uattest/README.md`, `tests/rig/test_uattest_gemini.py` (`39 passed` in `tests/rig/`) | ✅ Verified |
| 8 | `D-08` + CI Gates: `docs/QUICKSTART.md` (`uv sync --extra gemini`, AI Studio Pro/Ultra credits, Vertex mutual-exclusion, OAuth exclusion) + all 6 CI gates green + `strands_code_agent/` untouched | `docs/QUICKSTART.md`, `.github/workflows/gates.yml` checks (`uv lock --check`, `ruff`, `xenon`, `lint-imports`, `pytest`, `CLEANUP-01`, `git diff ee42ea2 -- strands_code_agent/` empty) | ✅ Verified |

## CI Gate Verification (After Final Edit, `uv sync --locked --extra litellm`)

- `/home/csaba/.local/bin/uv lock --check`: **exit 0** (`Resolved 147 packages`)
- `.venv/bin/pytest tests/ -q` (sandboxed): **1641 passed, 11 integration deselected** (`test_stub_server_systemone_decision_routes` failed on sandbox loopback bind)
- `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` (standalone outside sandbox): **1 passed** (total **1642 passed, 0 failed**)
- `.venv/bin/ruff check strands_code_cli tests scripts`: **All checks passed!**
- `.venv/bin/ruff format --check strands_code_cli tests scripts`: **115 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts`: **exit 0**
- `.venv/bin/lint-imports`: **Contracts: 1 kept, 0 broken**
- `CLEANUP-01` & `git diff ee42ea2 -- strands_code_agent/`: **clean / empty (`D-24`)**

## Optional Live `driver.py g1` Observation & Manual Verification Scope

- With `uv sync --locked --all-extras` temporarily active, running `python3 scripts/uattest/driver.py g1` outside sandbox with all `AWS_*` variables stripped verified **zero-AWS startup** (`[boot] seen`, `[prompt] seen`), ran `/context` showing `gemini-2.5-flash` (`of 1.05M`, `[context] seen`), and reached `generativelanguage.googleapis.com` before that endpoint rejected the host environment's invalid/stale `GEMINI_API_KEY` (`400 INVALID_ARGUMENT: API key not valid`).
- Live turn execution (`GEMINI_SENTINEL_14`, `/cost`, `/model google/gemini-2.5-pro`, and `G1 PASS`) remains queued as a manual verification under `14-VALIDATION.md` / `/gsd-verify-work 14` once a valid AI Studio or Vertex credential is exported.
