---
phase: "11"
slug: "codeact-action-interface"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-15"
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x via `uv run` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `uv run pytest tests/test_codeact.py tests/test_policy_gate.py tests/test_uattest_driver.py -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~50 seconds (full suite 1553 passed, 11 deselected) |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` command (codeact/policy_gate/driver trio or focused files)
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~50 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-T1 | 01 | 1 | TOOL-07 | T-11-01 / T-11-03 | /codeact toggle through shaped code turn to exact interface label; bare reports; dispatch before skills branch | unit (tracer) | `uv run pytest tests/test_codeact.py -q` | ✅ | ✅ green |
| 11-01-T2 | 01 | 1 | TOOL-07 | T-11-02 | --codeact flag + config keys + remember-last; fail-loud ValueError on bad values | unit | `uv run pytest tests/test_codeact.py -q` | ✅ | ✅ green |
| 11-02-T1 | 02 | 2 | TOOL-07 | T-11-04 / T-11-05 / T-11-06 | Stint lifecycle, {math}-only allowlist, sync interior file/shell, argv-only subprocess, reset on switch | unit | `uv run pytest tests/test_codeact.py -q` | ✅ | ✅ green |
| 11-02-T2 | 02 | 2 | TOOL-07 | T-11-07 | Per-turn python_repl swap via public replace(), restore in finally | unit | `uv run pytest tests/test_codeact.py -q` | ✅ | ✅ green |
| 11-02-T3 | 02 | 2 | TOOL-07 | — | Both-mode /code + /tool one-shot routing; bare asks get usage reply | unit | `uv run pytest tests/test_codeact.py -q` | ✅ | ✅ green |
| 11-03-T1 | 03 | 3 | TOOL-07 | T-11-08 | Whole-block Syntax preview (2000-char pin) + deny revise hint | unit | `uv run pytest tests/test_policy_gate.py tests/test_codeact.py -q` | ✅ | ✅ green |
| 11-03-T2 | 03 | 3 | TOOL-07 | T-11-09 | One rule system + switching coherence pins; phase gate | unit | `uv run pytest tests/ -q` | ✅ | ✅ green (1553 passed) |
| 11-04-T1 | 04 | 4 | TOOL-07 | T-11-11 / T-11-12 | Bare --codeact argv expansion; valued forms + sentinel untouched; pre-gate validation kept | unit (fix) | `uv run pytest tests/test_codeact.py -q` | ✅ | ✅ green |
| 11-04-T2 | 04 | 4 | TOOL-07 | — | Bare-flag startup tests + a1 live gate green | unit + rig (keyed) | `python3 scripts/uattest/driver.py a1` | ✅ | ✅ green (A1 PASS) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| UAT live turns (labels, startup, stint reset, unshaped tool turn) | TOOL-07 | Live REPL print sites + human-witnessed behavior | Boot with/without --codeact, run code/tool turns, switch mid-session — done, 20/20 UAT pass |
| G-11-1 retest confirmation after 11-04 | TOOL-07 | User-witnessed bare-flag boot | Boot bare --codeact, confirm code mode — done, A1 PASS both sides |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s (per-task quick command: 184 passed in 1.90s; full suite ~50s runs per-wave only)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-10-16
