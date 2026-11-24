---
status: complete
phase: 14-first-class-google-gemini-provider-aware-startup
source: [14-01-SUMMARY.md, 14-02-SUMMARY.md, 14-03-SUMMARY.md, 14-VERIFICATION.md]
started: 2026-11-23T16:35:00Z
updated: 2026-11-23T23:47:30Z
---

# Phase 14 User Acceptance Testing (`MODEL-06`)

## Current Test

[testing complete — 6/6 PASS]

## Tests

### 1. Zero-AWS Gemini Launch, Session-Scoped `--model` & Vertex Conflict Guard (`D-02`, `D-03`)
expected: With AWS credentials unset and GOOGLE_API_KEY or GEMINI_API_KEY exported, launching `strands-code` (with `--model google/gemini-3.8-flash` and without `--model` under a clean XDG_CONFIG_HOME) boots directly to the REPL on `google/gemini-3.8-flash` without calling AWS STS or writing `config.yaml`; setting both `GOOGLE_GENAI_USE_VERTEXAI=true` and `GEMINI_API_KEY` fails fast (exit 2) naming the conflicting vars before creating `.agent/sessions`.
result: pass
evidence:
- Executed via `run_uat_test1.py` (2026-11-23T16:39:28Z, exit `0`, isolated `XDG_CONFIG_HOME`, AWS/other provider env vars stripped):
  - `1a` (`--model google/gemini-3.8-flash`): booted to REPL, `/context` reported `Context — google/gemini-3.8-flash` / `input tokens: 0 (0% of 1.05M)`, `config_yaml_exists: False`.
  - `1b` (ambient auto-pick, no `--model`, `GEMINI_API_KEY` set): booted to REPL, `/context` reported `Context — google/gemini-3.8-flash` / `input tokens: 0 (0% of 1.05M)`, `config_yaml_exists: False`.
  - `1c` (`GOOGLE_GENAI_USE_VERTEXAI=true` + `GEMINI_API_KEY`): exited `2` with `GOOGLE_GENAI_USE_VERTEXAI and GOOGLE_API_KEY / GEMINI_API_KEY are mutually exclusive; unset one before launching.` and created no `.agent/sessions` directory (`sessions_dir_exists: False`).

### 2. Live Gemini Tool Turn, `/context` (`1.05M`), `/cost` Pricing & Same-Vendor `/model` Switch (`D-04`, `D-06`, `D-07` — `driver.py g1`)
expected: Running `python3 scripts/uattest/driver.py g1` (or performing the flow interactively) boots with AWS env stripped, shows `Context — google/gemini-3.8-flash` with `1.05M`/`1.00M` window, executes a `read` tool turn returning `GEMINI_SENTINEL_14`, shows `/cost` with USD spend (`$`) and `Display only — no budgets or enforcement.` (skipping Bedrock Price List), and switches via `/model google/gemini-4-hydrogen` keeping messages with zero `Dropping reasoningContent` warning.
result: pass
evidence:
- Live `driver.py g1` (`G1 PASS`, exit `0`, 2026-11-23T16:44:15Z, `/tmp/uatr8/g1.log`, session `cc990411-f64f-431c-9be1-8f4d98993b3a`, AWS env stripped, isolated `XDG_CONFIG_HOME`):
  - Booted `--model google/gemini-3.8-flash` cleanly with zero `config.yaml` written; `/context` printed `Context — google/gemini-3.8-flash` and `input tokens: 0 (0% of 1.05M)`.
  - Executed `[Tool] read` on `/tmp/uatr8/g1/sentinel.txt` and replied `[Assistant] GEMINI_SENTINEL_14` (`6.15K (1%) $0.01`, `interface: tool`).
  - `/cost` printed `Cost — google/gemini-3.8-flash`, `Total: in 6.15K, out 222, $0.0054`, `Prices: LiteLLM bundled.`, `Display only — no budgets or enforcement.`.
  - `/model google/gemini-4-hydrogen` printed `Model: google/gemini-4-hydrogen — conversation continued (4 messages kept).` with zero `Dropping reasoningContent` warning.

### 3. Credential-Gated Multi-Provider `/model` Picker & Decimal-Safe Grouping (`D-04`, `D-05`)
expected: Running `/model` when Google credentials are exported discovers live `generateContent` Gemini models grouped cleanly under `google` / `gemini` (never broken decimal splits like `gemini-2` / `5` for `gemini-2.5-pro`), merged cleanly with Bedrock when AWS credentials are also present, and omitted cleanly when Google credentials are absent.
result: pass
evidence:
- Executed via `run_uat_test3.py` and `run_uat_test3d.py` (2026-11-23T16:58:24Z, exit `0`):
  - `3a` (live Google-only `discover_models()`): `offline: false`, 38 unique `google/` models, `build_model_tree` vendors `{"google": ["gemini"]}`, `_vendor_family("gemini-2.5-pro") == ("google", "gemini")` (zero decimal splits).
  - `3b` (live zero-AWS `/model` tmux picker): rendered `Select vendor` → `google (38 models)` → `Enter` auto-advanced to `Select google gemini model` (44 lines, zero decimal group splits); `Escape` returned `Model unchanged.`.
  - `3c` (live Google + AWS merged `discover_models()`): `offline: false`, 38 `google/` + 137 Bedrock models cleanly deduped across 16 vendors with `"google": ["gemini", "gemma"]`.
  - `3d` (clean `cwd="/tmp/uat14_t3d_empty"` without `.env`, Google vars stripped): `has_google_credentials() == False` and `google_count == 0` in both offline fallback (`opts: ["bedrock/us.anthropic.claude-sonnet-4-6"]`) and live Bedrock-only discovery (`137` Bedrock models, `offline: false`). Operational caveat observed: `smolagents.remote_executors:48` calls `load_dotenv()` on CWD `.env` at import time when a `.env` file exists in the launch directory.

### 4. Cross-Provider Switch (`reasoningSignature` Strip/Restore) & Gemini 2.5 Thinking Guard (`D-04`, `D-07`)
expected: Switching from a Gemini tool/reasoning turn to a non-Google model (e.g., Bedrock or OpenRouter via LiteLLM) strips `toolUse["reasoningSignature"]` cleanly without provider validation or `__thought__` ID corruption while preserving it on switch-back; launching `--model google/gemini-2.5-flash` runs a tool turn cleanly via the `thinking_budget` + empty `gemini_tools` guard.
result: pass
evidence:
- Hermetic `TestGeminiCrossProviderSafety` (`tests/model/test_model_switch.py`): `7 passed in 5.33s`.
- Live cross-provider round-trip `g4a` (`run_uat_test4.py`, 2026-11-23T17:08:56Z, exit `0`, `/tmp/uatr8/g4a.log`, session `2ad269b6-9f8c-442a-9c81-01765c308f28`):
  - Turn 1 on `google/gemini-3.8-flash` ran `[Tool] read` on `/tmp/uat14_t4/work_g4a/sentinel4a.txt` and replied `CROSS_VENDOR_SIG_14` (`6.18K (1%) $0.01`, `interface: tool`).
  - `/model bedrock/us.anthropic.claude-sonnet-4-6` kept `4` messages (logging expected `Dropping reasoningContent` warning); Turn 2 recalled `CROSS_VENDOR_SIG_14` (`10.09K (1%) $0.03`) with zero `ValidationException`.
  - `/model google/gemini-3.8-flash` printed `Model: google/gemini-3.8-flash — conversation continued (6 messages kept, thinking restored).`; Turn 3 confirmed `CROSS_VENDOR_SIG_14` (`13.38K (1%) $0.01`).
- Live Gemini 2.5 Flash guard `g4c` (`run_uat_test4.py`, `/tmp/uatr8/g4c.log`, session `3adef1f5-3530-4f0a-8061-a0e27a2c7f82`, AWS env stripped): `--model google/gemini-2.5-flash` executed `[Tool] read` on `/tmp/uat14_t4/work_g4c/sentinel4c.txt` and replied `[Assistant] GEMINI_25_GUARD_14` (`5.84K (1%) $0.00`, `interface: tool`) with zero errors.

### 5. `docs/QUICKSTART.md` & Upstream Gemini 2.5 Issue Draft Review (`D-07`, `D-08`)
expected: `docs/QUICKSTART.md` accurately covers provider-aware startup, session-scoped `--model`, `uv sync --extra gemini`, AI Studio API keys with Google AI Pro ($10/mo) / AI Ultra 5x ($40/mo) / AI Ultra 20x ($100/mo) Developer Program credits, consumer OAuth exclusion, and Vertex ADC + mutual-exclusion; `docs/upstream/harness_issue_gemini25_thinking.md` is accurate and ready.
result: pass
evidence:
- User reviewed and confirmed `docs/QUICKSTART.md` looks good and filled in `## Human Overview` in `docs/upstream/harness_issue_gemini25_thinking.md` (2026-11-23T23:35:00Z).

### 6. Hermetic Suite, Rig Contracts & CI Gates on `HEAD` (`D-01`..`D-08`, `D-24`)
expected: `pytest tests/ -q` (plus loopback test), `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check`, and `git diff ee42ea2 -- strands_code_agent/` (empty) all pass on current `HEAD`.
result: pass
evidence:
- Verified on `HEAD` (`c7233f9`, 2026-11-23T23:46:51Z):
  - `.venv/bin/pytest tests/ -q -k "not test_stub_server_systemone_decision_routes"` (sandboxed): `1644 passed, 12 deselected in 62.74s`.
  - `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` (standalone loopback bind): `1 passed, 190 deselected in 2.15s` (total **1645 passed, 0 failed**; `11` integration tests deselected by `pyproject.toml`).
  - `.venv/bin/ruff check strands_code_cli tests scripts`: `All checks passed!`.
  - `.venv/bin/ruff format --check strands_code_cli tests scripts`: `115 files already formatted`.
  - `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts`: exit `0`.
  - `.venv/bin/lint-imports`: `Contracts: 1 kept, 0 broken.` (`39 files, 82 dependencies`).
  - `/home/csaba/.local/bin/uv lock --check`: exit `0` (`Resolved 154 packages in 2ms`).
  - `git diff ee42ea2 -- strands_code_agent/`: empty (exit `0`).

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0
signed_off: 2026-11-23T23:47:30Z (`/gsd-verify-work 14`, `HEAD` `c7233f9`)

## Gaps

[none]
