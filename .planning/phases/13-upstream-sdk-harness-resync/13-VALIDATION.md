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

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing test infrastructure covers all Phase 13 requirements; no new top-level fixtures or harness bootstrap scripts are needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
| :--- | :--- | :--- | :--- |
| Live Bedrock Opus -> Nova/Llama session resume (`#5166`) & live Llama 4 streaming=False tool call (`D-03`) *(optional smoke if AWS creds present)* | `UPSTREAM-01` | Requires live AWS Bedrock runtime access | If AWS creds are available, run a tool-using turn on Opus, exit, relaunch with `--session-id` on Llama 4 or Nova, and confirm tool call succeeds with unary note cleanly displayed |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with automated test execution
- [x] Wave 0 covers all dependencies
- [x] No watch-mode flags
- [x] Fast feedback latency (< 10s unit checks per task; full suite ~45s per wave)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-11-21 (1559 passed, 11 deselected; all 6 `.github/workflows/gates.yml` checks green)
