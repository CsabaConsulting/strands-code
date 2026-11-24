---
phase: "14"
slug: "first-class-google-gemini-provider-aware-startup"
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-21"
validated: "2026-11-23"
---

# Phase 14 — Validation Strategy

> Per-phase Nyquist validation contract for feedback sampling during Phase 14 execution (`MODEL-06`).

---

## Test Infrastructure

| Property | Value |
| :--- | :--- |
| **Framework** | `pytest` (installed in `.venv`) via `/home/csaba/.local/bin/uv run pytest` or `.venv/bin/pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `.venv/bin/pytest tests/entry/ tests/dispatch/test_cli_entry.py tests/model/test_model_switch.py tests/cost/ -q` |
| **Full suite command** | `.venv/bin/pytest tests/ -q` |
| **Static / complexity gates** | `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check` |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` verification command (`< 15s`).
- **After every plan wave:** Run `.venv/bin/pytest tests/ -q` + `ruff check` + `ruff format --check` + `xenon --max-absolute C` + `lint-imports`.
- **Before `/gsd-verify-work 14`:** All 6 CI workflow checks from `.github/workflows/gates.yml` must pass cleanly.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Decision / Anchor | Secure / Correct Behavior | Test Type | Automated Command | File Exists | Status |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `14-01-T1` | 01 | 1 | `MODEL-06` | `D-01` | `pyproject.toml` declares `gemini = ["strands-agents[gemini]"]`, `uv.lock` resolves, `_SDK_EXTRA_HINTS["google"] = "gemini"` | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/dispatch/test_cli_entry.py -q` | ✅ | ✅ green |
| `14-01-T2` | 01 | 1 | `MODEL-06` | `D-02`, `D-03` | Box-compatible presence-only preflight, STS bypass on `STRANDS_BOX=1`, Vertex mutual-exclusion fail-fast, ambient model auto-pick, `--model` CLI flag, zero `os.environ` outside `first_run.py` | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/entry/ tests/dispatch/test_cli_entry.py tests/cost/test_cost_context.py -k "first_run or session_resume or cli_entry or no_credential_persistence_sinks" -q` | ✅ | ✅ green |
| `14-02-T1` | 02 | 2 | `MODEL-06` | `D-04`, `D-07` | `supports_reasoning("google/...")`, `toolUse["reasoningSignature"]` cross-vendor strip + `RichHistory` / `canonical_prefix_hash` preserve, `_vendor_family` dot-split fix, Gemini 2.5 `thinking_budget` guard across 4 call sites | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/model/test_model_switch.py tests/loop/test_btw.py -q` | ✅ | ✅ green |
| `14-02-T2` | 02 | 2 | `MODEL-06` | `D-05` | Credential-gated `google.genai.Client().models.list()` discovery (`generateContent` `gemini-*`) merged with Bedrock, static fallback only when Google-keyed, zero AWS clutter | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/model/test_model_switch.py tests/cost/test_cost_context.py -k "discover or model_tree or no_credential_persistence" -q` | ✅ | ✅ green |
| `14-02-T3` | 02 | 2 | `MODEL-06` | `D-06` | `live_pricing.litellm_entry` `gemini/<tail>` + `<tail>`, static Gemini `MODEL_PRICING` / `MODEL_LIMITS`, skip `bedrock_live_price` for non-Bedrock direct providers | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/cost/ -q` | ✅ | ✅ green |
| `14-03-T1` | 03 | 2 | `MODEL-06` | `D-07` | Repeatable `driver.py g1` scenario in `scripts/uattest/scenarios_gemini.py` (zero-AWS `env -u AWS_*`, isolated `XDG_CONFIG_HOME`, `--model google/gemini-3.8-flash`) + rig contract tests | rig contract | `.venv/bin/pytest tests/rig/ -q` | ✅ | ✅ green |
| `14-03-T2` | 03 | 2 | `MODEL-06` | `D-07`, `D-08` + Gates | `docs/QUICKSTART.md` AI Studio Ultra credit docs, `harness_issue_gemini25_thinking.md` (`harness-sdk#6510`), and all 6 CI gates (`pytest`, `ruff`, `xenon`, `lint-imports`, `uv lock --check`, `CLEANUP-01`) green | full suite + CI gates | `.venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports && .venv/bin/pytest tests/ -q` | ✅ | ✅ green |
| `14-UAT-T1` | uat | 3 | `MODEL-06` | `D-02`..`D-08` | Full 6/6 conversational + live UAT (`14-UAT.md`): zero-AWS launch/auto-pick, Vertex conflict fail-fast, live `driver.py g1` (`G1 PASS`), live 38-model `/model` discovery/cascade, live `g4a` cross-provider switch/restore + `g4c` Gemini 2.5 Flash turn | live UAT + rig | `python3 scripts/uattest/driver.py g1` + `14-UAT.md` | ✅ | ✅ green |
| `14-SEC-T1` | sec | 3 | `MODEL-06` | `T-14-02` | `disable_cwd_dotenv()` blocks implicit CWD `.env` auto-load in `smolagents.remote_executors` / `litellm._process_defaults` while preserving explicit `dotenv_path`/`stream` loads (`14-SECURITY.md` `10/10` closed, `threats_open: 0`) | security unit | `.venv/bin/pytest tests/entry/test_first_run.py -k TestCwdDotenvGuard -q` | ✅ | ✅ green |
| `14-VAL-T1` | val | 3 | `MODEL-06` | `D-02`..`D-07` | Nyquist branch coverage for explicit Anthropic/OpenAI/`base_url`/LiteLLM/`STRANDS_BOX` preflight, blank `--model` CLI gate, `prepare_resumed_history` Gemini `toolUse["reasoningSignature"]` stash/strip, `configure_gemini_for_model` existing budget + fail-soft exceptions, `_is_google_chat_model` legacy `supported_generation_methods`/`name=None`, and non-`google/` `vertex_ai/gemini-*` LiteLLM tail fallback | unit (Nyquist) | `.venv/bin/pytest tests/entry/test_first_run.py tests/model/test_model_switch.py tests/cost/test_live_pricing.py -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing test infrastructure covers Plans `14-01` and `14-02`; `tests/rig/test_uattest_gemini.py` is created TDD-first in Plan `14-03` Task 1 (`14-03-T1`).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Live Creds Required | Test Instructions | Status |
| :--- | :--- | :--- | :--- | :--- |
| Live Google AI Studio `google/gemini-3.8-flash` zero-AWS launch, tool turn, `/context`, `/cost`, and `/model google/gemini-4-hydrogen` switch (`driver.py g1`) | `MODEL-06` | Requires `GOOGLE_API_KEY` or `GEMINI_API_KEY` (plus `--extra gemini`) | `python3 scripts/uattest/driver.py g1` | ✅ `G1 PASS` (`/tmp/uatr8/g1.log`) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with TDD / automated verification
- [x] Wave 0 gaps identified (`test_uattest_gemini.py` in `14-03-T1`)
- [x] No watch-mode flags
- [x] Fast feedback latency (< 15s per task; full suite ~65s per wave)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-11-23 (`1653 passed, 12 deselected` + loopback `1 passed` = `1654 passed, 0 failed`; `11` integration specs deselected by `pyproject.toml`; `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check` all green; `git diff ee42ea2 -- strands_code_agent/` empty; live `driver.py g1`, `/model`, `g4a`, and `g4c` UATs recorded passing in `14-UAT.md`)
