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

**Status:** Passed (`8/8` must-have truths verified + live `driver.py g1` passed)  
**Verified:** 2026-11-22 on branch `main`

## Truth-by-Truth Verification Matrix

| # | Decision / Truth | Evidence (Code & Tests) | Observed Status |
|---|---|---|---|
| 1 | `D-01`: `gemini` optional extra & `_SDK_EXTRA_HINTS["google"] = "gemini"` | `pyproject.toml`, `uv.lock` (`147` packages, `uv lock --check` exit `0`), `strands_code_cli/dispatch/core.py`, `tests/dispatch/test_cli_entry.py` (`TestSdkHints`) | ✅ Verified |
| 2 | `D-02`, `D-03`: Box-compatible provider-aware startup preflight, Vertex mutual-exclusion & project gate, ambient auto-pick, session-scoped `--model`, `model_id=effective_model` forwarded to `run_loop`, all `os.environ` reads isolated in `entry/first_run.py` | `strands_code_cli/entry/first_run.py`, `strands_code_cli/entry/main.py`, `tests/conftest.py`, `tests/entry/test_first_run.py`, `tests/entry/test_session_resume.py`, `tests/cost/test_cost_context.py::TestLoopUsageWiring::test_no_credential_persistence_sinks` (`109 passed` entry+dispatch+rig) | ✅ Verified |
| 3 | `D-04`: `supports_reasoning("google/...")` (covering Gemini 2.5, 3.x, 4.x) + cross-vendor `toolUse["reasoningSignature"]` stripping (verifying `LiteLLMModel.format_request_message_tool_call`), `RichHistory` / `canonical_prefix_hash` preserve/restore, `_vendor_family` decimal dot fix | `strands_code_cli/model/model_switch.py`, `strands_code_cli/loop/core.py`, `tests/model/test_model_switch.py` (`TestGeminiCrossProviderSafety`) | ✅ Verified |
| 4 | `D-07`: `configure_gemini_for_model()` rewrites Gemini-3 `thinking_level` to `thinking_budget` AND clears built-in `gemini_tools=[]` on Gemini 2.5 (leaving Gemini 3.8+ & 4+ untouched) across `apply_switch`, `build_agent`, `_route_side_spawn`, and `build_btw_agent` + upstream issue draft | `strands_code_cli/model/model_switch.py`, `strands_code_cli/entry/main.py`, `strands_code_cli/loop/core.py`, `strands_code_cli/loop/btw.py`, `docs/upstream/harness_issue_gemini25_thinking.md`, `tests/model/test_model_switch.py`, `tests/loop/test_btw.py` (`326 passed` model/btw/cost) | ✅ Verified |
| 5 | `D-05`: Credential-gated `google.genai.Client().models.list()` discovery merged with Bedrock + expanded `CURATED_GEMINI_MODELS` (`2.5`, `3.8-flash`, `4-hydrogen/neon/argon/carbon`) fallback only when `has_google_credentials()` is True | `strands_code_cli/model/model_switch.py`, `tests/model/test_model_switch.py` (`TestDiscoverModels`) + live `genai.Client().models.list()` check | ✅ Verified |
| 6 | `D-06`: `live_pricing.litellm_entry` `gemini/<tail>` + `<tail>` keys, curated Gemini `MODEL_PRICING` / `MODEL_LIMITS` (`2.5`, `3.x` incl. `3.8-flash`, `4-hydrogen`, `4-neon`, `4-argon`, `4-carbon`, all `1_048_576`), and Bedrock Price List skip for non-Bedrock direct routes | `strands_code_cli/cost/live_pricing.py`, `strands_code_cli/cost/cost_context.py`, `tests/cost/test_live_pricing.py`, `tests/cost/test_cost_context.py` | ✅ Verified |
| 7 | `D-07`: Repeatable zero-AWS `driver.py g1` scenario & rig contract tests + **live `driver.py g1` `G1 PASS`** | `scripts/uattest/scenarios_gemini.py`, `scripts/uattest/driver.py`, `scripts/uattest/README.md`, `tests/rig/test_uattest_gemini.py` (`39 passed`), live `/tmp/uatr8/g1.log` (`G1 PASS`) | ✅ Verified |
| 8 | `D-08` + CI Gates: `docs/QUICKSTART.md` (`uv sync --extra gemini`, AI Studio Pro/Ultra credits, Vertex mutual-exclusion, OAuth exclusion) + `.gitignore` excludes `.env` + all 6 CI gates green + `strands_code_agent/` untouched | `docs/QUICKSTART.md`, `.gitignore`, `.github/workflows/gates.yml` checks (`uv lock --check`, `ruff`, `xenon`, `lint-imports`, `pytest`, `CLEANUP-01`, `git diff ee42ea2 -- strands_code_agent/` empty) | ✅ Verified |

## Live Verification Results (With `.env` Key & `[gemini]` Extra)

- **Live `genai.Client().models.list()`:** Enumerated live `generateContent` models including `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.8-flash`, `gemini-4-hydrogen`, `gemini-4-neon`, `gemini-4-argon`, `gemini-4-carbon`.
- **Live tool-call probes:** Verified real `read` tool execution on `google/gemini-2.5-flash`, `google/gemini-2.5-pro`, `google/gemini-3.8-flash`, and `google/gemini-4-hydrogen`.
- **Live `python3 scripts/uattest/driver.py g1` (`G1 PASS`):**
  - Zero-AWS boot (`env -u AWS_*`, isolated `XDG_CONFIG_HOME`, no `config.yaml` written before `/model`).
  - `/context`: rendered `Context — google/gemini-3.8-flash` (`0% of 1.05M`).
  - Live `read` tool turn: returned `GEMINI_SENTINEL_14`.
  - `/cost`: rendered `Cost — google/gemini-3.8-flash`, `$0.0054`, `Prices: LiteLLM bundled.`, `Display only — no budgets or enforcement.`.
  - `/model google/gemini-4-hydrogen`: switched cleanly with `Model: google/gemini-4-hydrogen — conversation continued (4 messages kept).` and zero `Dropping reasoningContent` warnings.
  - Prior live `driver.py g1` run on `google/gemini-2.5-flash` -> `google/gemini-2.5-pro` also passed (`G1 PASS`, `$0.0020`, `1.05M`), and `first_run.py` now defaults ambient Google sessions to `google/gemini-3.8-flash` ahead of Gemini 2.5's Dec 1, 2026 AI Studio auto-reroute.

## CI Gate Verification (After Final Code/Test Edit, `uv sync --locked --extra litellm`)

- `/home/csaba/.local/bin/uv lock --check`: **exit 0** (`Resolved 147 packages`)
- `.venv/bin/pytest tests/ -q` (sandboxed): **1644 passed, 11 integration deselected** (`test_stub_server_systemone_decision_routes` failed on sandbox loopback bind)
- `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` (standalone outside sandbox): **1 passed** (total **1645 passed, 0 failed**)
- `.venv/bin/ruff check strands_code_cli tests scripts`: **All checks passed!**
- `.venv/bin/ruff format --check strands_code_cli tests scripts`: **115 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts`: **exit 0**
- `.venv/bin/lint-imports`: **Contracts: 1 kept, 0 broken**
- `CLEANUP-01` & `git diff ee42ea2 -- strands_code_agent/`: **clean / empty (`D-24`)**
