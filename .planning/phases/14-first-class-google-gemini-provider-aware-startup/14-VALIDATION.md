---
phase: "14"
slug: "first-class-google-gemini-provider-aware-startup"
status: verified
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-21"
validated: "2026-11-22"
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
| `14-03-T1` | 03 | 2 | `MODEL-06` | `D-07` | Repeatable `driver.py g1` scenario in `scripts/uattest/scenarios_gemini.py` (zero-AWS `env -u AWS_*`, isolated `XDG_CONFIG_HOME`, `--model google/gemini-2.5-flash`) + rig contract tests | rig contract | `.venv/bin/pytest tests/rig/ -q` | ✅ | ✅ green |
| `14-03-T2` | 03 | 2 | `MODEL-06` | `D-07`, `D-08` + Gates | `docs/QUICKSTART.md` AI Studio Ultra credit docs, `harness_issue_gemini25_thinking.md`, and all 6 CI gates (`pytest`, `ruff`, `xenon`, `lint-imports`, `uv lock --check`, `CLEANUP-01`) green | full suite + CI gates | `.venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports && .venv/bin/pytest tests/ -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing test infrastructure covers Plans `14-01` and `14-02`; `tests/rig/test_uattest_gemini.py` is created TDD-first in Plan `14-03` Task 1 (`14-03-T1`).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Live Creds Required | Test Instructions |
| :--- | :--- | :--- | :--- |
| Live Google AI Studio / Vertex `google/gemini-2.5-flash` tool turn, `/context`, `/cost`, and cross-provider switch (`driver.py g1`) | `MODEL-06` | Requires `GOOGLE_API_KEY` or `GEMINI_API_KEY` (plus `--extra gemini`) | If Google key is available, run `python3 scripts/uattest/driver.py g1` and confirm `G1 PASS` with zero AWS env vars (`14-03-T1`) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with TDD / automated verification
- [x] Wave 0 gaps identified (`test_uattest_gemini.py` in `14-03-T1`)
- [x] No watch-mode flags
- [x] Fast feedback latency (< 15s per task; full suite ~65s per wave)
- [x] `nyquist_compliant: true` set in frontmatter

**Status:** Verified `2026-11-22` — all 7 automated Nyquist rows green (`1642 passed, 0 failed`, all 6 CI gates pass); live `driver.py g1` awaits a valid `GOOGLE_API_KEY` / `GEMINI_API_KEY`.
