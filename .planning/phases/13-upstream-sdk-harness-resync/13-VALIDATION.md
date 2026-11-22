---
phase: "13"
slug: "upstream-sdk-harness-resync"
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-21"
validated: "2026-11-21"
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
| :--- | :--- |
| **Framework** | `pytest` (installed in `.venv`) via `/home/csaba/.local/bin/uv run pytest` or `.venv/bin/pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `.venv/bin/pytest tests/cost/test_cost_context.py tests/model/test_model_switch.py tests/loop/test_btw.py tests/memory/test_memory_file.py -q` |
| **Full suite command** | `/home/csaba/.local/bin/uv run --locked --extra litellm pytest tests/ -q` |
| **Static / complexity gates** | `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports` |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` verification command.
- **After every plan wave:** Run `.venv/bin/pytest tests/ -q` + `ruff` + `xenon --max-absolute C` + `lint-imports`.
- **Before `/gsd-verify-work 13`:** All 6 CI workflow checks from `.github/workflows/gates.yml` must pass cleanly.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Decision / Anchor | Secure / Correct Behavior | Test Type | Automated Command | File Exists | Status |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `13-01-T1` | 01 | 1 | `UPSTREAM-01` | `D-01`, `D-06`, `D-07` | Bump `pyproject.toml` (`>=1.65.0`, `>=0.4.0`), lock & sync `uv.lock`, verify `create_harness` / `steering.py` / `todos` removal compatibility | tracer + regression | `.venv/bin/pytest tests/agent/ tests/memory/test_memory_file.py tests/loop/test_steering.py -q` | ✅ | ✅ green |
| `13-01-T2` | 01 | 1 | `UPSTREAM-01` | `D-05` | `estimate_messages_tokens` counts `"injected"`, `canonical_prefix_hash` & `fork_btw_history` ignore `"injected"`, callback non-echo pinned | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/cost/test_cost_context.py tests/model/test_model_switch.py tests/loop/test_btw.py -q` | ✅ | ✅ green |
| `13-02-T1` | 02 | 2 | `UPSTREAM-01` | `D-02` | Route-aware `window_for()` precedence (OpenRouter live on `litellm/openrouter/*`, SDK `model_info` first elsewhere, then LiteLLM & `MODEL_LIMITS`) | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/cost/test_cost_context.py tests/cost/test_live_pricing.py -q` | ✅ | ✅ green |
| `13-02-T2` | 02 | 2 | `UPSTREAM-01` | `D-03` | `BedrockModel` `_NO_STREAMING_TOOLS` configured `streaming=False` at build/`/model`/`/route`/`/btw`; concise unary note on launch & `/model` (quiet on `/route`) | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/model/test_model_switch.py tests/loop/test_btw.py -q` | ✅ | ✅ green |
| `13-02-T3` | 02 | 2 | `UPSTREAM-01` | `D-04` + Gates | Hybrid session restore (`prepare_resumed_history`) + `#5166` cross-family Bedrock strip pin + `PolicyHumanInTheLoop` 1.65 HITL reconciliation + all 6 CI gates green | unit + full suite + CI gates | `.venv/bin/pytest tests/ -q` | ✅ | ✅ green |
| `13-SEC-T1` | sec | 3 | `UPSTREAM-01` | `T-13-02` | `PolicyClassifier` / `PolicyHumanInTheLoop` fails closed on duplicate `toolUseId` or classifier error without leaking stale `ask` preview or `Deny.reason` | security unit | `.venv/bin/pytest tests/policy/test_policy_gate.py -k TestHitlFailClosedStaleContext -q` | ✅ | ✅ green |
| `13-UAT-T1` | uat | 3 | `UPSTREAM-01` | `D-03`, `T-13-08`, `T-13-11` | Bedrock-scoped Mistral/Writer/Meta `_NO_STREAMING_TOOLS` rows stay fail-open for streaming/non-Bedrock routes; repeatable `driver.py u1/u2/u3` rig + command-bound `u3` HITL regex | unit + rig contract | `.venv/bin/pytest tests/model/test_model_switch.py tests/rig/ -q` | ✅ | ✅ green |
| `13-VAL-T1` | val | 3 | `UPSTREAM-01` | `D-02` | Nyquist branch coverage for `_sdk_window_candidates()` ARN inference-profile tail extraction and `window_for()` OpenRouter→LiteLLM 3rd-tier fallback | unit (Nyquist) | `.venv/bin/pytest tests/cost/test_cost_context.py -k TestSdkModelInfoWindow -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing test infrastructure covers all Phase 13 requirements; no new top-level fixtures or harness bootstrap scripts are needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Live Creds Required | Test Instructions |
| :--- | :--- | :--- | :--- |
| Live Bedrock unary Converse tool turn (`u1` Mistral Large 24.02 + Pixtral 25.02 toggle), cross-family resume (`u2` Sonnet 4.6 → Nova 2 Lite), & live 1.65.0 HITL/Plan (`u3`) | `UPSTREAM-01` | Requires live AWS Bedrock runtime access (`us-west-2`); automated via `scripts/uattest/driver.py` (`u1`/`u2`/`u3`) and recorded passing in `13-UAT.md` | With AWS creds set, run `python3 scripts/uattest/driver.py u1`, `driver.py u2`, `driver.py u3` and confirm `U1 PASS`, `U2 PASS`, `U3 PASS` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with automated test execution
- [x] Wave 0 covers all dependencies
- [x] No watch-mode flags
- [x] Fast feedback latency (< 10s unit checks per task; full suite ~65s per wave)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-11-21 (`1569 passed, 11 deselected`; `u1`/`u2`/`u3` live tmux UATs recorded in `13-UAT.md`; all 6 `.github/workflows/gates.yml` checks green)
