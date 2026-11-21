---
phase: "10"
slug: "provider-reported-turn-spend"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-12"
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x via `uv run` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `uv run pytest tests/test_reported_cost.py tests/test_cost_context.py tests/test_uattest_driver.py -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~45 seconds (full suite 1420 passed, 11 deselected) |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` command (cost-module trio or focused files)
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~45 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-T1 | 01 | 1 | MODEL-05 | T-10-01 | Bool-safe extractor, fail-soft capture, drain-to-marked-usage-line | unit (TDD RED→GREEN) | `uv run pytest tests/test_reported_cost.py -q` | ✅ | ✅ green (33 passed, 1 deselected) |
| 10-01-T2 | 01 | 1 | MODEL-05 | T-10-02 | Actual-wins rows, one money lane, bare-$ estimates stay unmarked | unit (TDD RED→GREEN) | `uv run pytest tests/test_cost_context.py -q` | ✅ | ✅ green |
| 10-02-T1 | 02 | 2 | MODEL-05 | T-10-02 | Blended total + split line; routing spend in actuals lane only | unit (TDD RED→GREEN) | `uv run pytest tests/test_cost_context.py -q` | ✅ | ✅ green |
| 10-02-T2 | 02 | 2 | MODEL-05 | — | Bedrock/offline byte-parity with pre-phase output | unit (parity) | `uv run pytest tests/ -q` | ✅ | ✅ green (1420 passed) |
| 10-03-T1 | 03 | 2 | MODEL-05 | T-10-02 | Fresh wrapper per side build; per-turn drain carrier; drains stay separate | unit (TDD RED→GREEN) | `uv run pytest tests/test_reported_cost.py tests/test_model_switch.py -q` | ✅ | ✅ green |
| 10-03-T2 | 03 | 2 | MODEL-05 | T-10-02 | Initial-build wrap; effort survives promotion; non-OR ids pass through | unit | `uv run pytest tests/test_reported_cost.py tests/test_model_switch.py -q` | ✅ | ✅ green |
| 10-03-T3 | 03 | 2 | MODEL-05 | T-10-04 | Live OpenRouter proof: passes keyed, skips unkeyed, deselected by default | integration (env-gated) | `uv run pytest tests/test_reported_cost.py::TestLiveReportedCost -q -rs -m integration` | ✅ | ✅ green (1 passed keyed; skip with naming reason otherwise) |
| 10-04-T1 | 04 | 3 | MODEL-05 | T-10-01 | Serving-model drain at both sites; pre-discipline accumulation discarded once | unit (TDD RED→GREEN) | `uv run pytest tests/test_reported_cost.py -q` | ✅ | ✅ green |
| 10-04-T2 | 04 | 3 | MODEL-05 | T-10-01 | Finite-only extract; fail-soft wrap/copy degrade to estimates | unit (TDD RED→GREEN) | `uv run pytest tests/test_reported_cost.py -q` | ✅ | ✅ green |
| 10-04-T3 | 04 | 3 | MODEL-05 | — | WR-04 live assertion tolerates legitimate 0.0 actuals; suite gate | unit + integration | `uv run pytest tests/ -q` | ✅ | ✅ green (1420 passed) |
| 10-05-T1 | 05 | 4 | MODEL-05 | T-10-05 / T-10-06 | Single-inheritance promotion succeeds on the real slotted SDK chain | unit (TDD RED→GREEN) + probe | `uv run pytest tests/test_reported_cost.py -q` | ✅ | ✅ green (single-inheritance OK) |
| 10-05-T2 | 05 | 4 | MODEL-05 | T-10-07 | Real-SDK regression with dummy client_args, zero network I/O | unit (RED-demonstrated) | `uv run pytest tests/test_reported_cost.py::TestRealSdkPromotion -q` | ✅ | ✅ green |
| 10-05-T3 | 05 | 4 | MODEL-05 | — | c1 rig end-to-end: marked actuals on usage line and /cost row | rig (keyed) | `python3 scripts/uattest/driver.py c1` | ✅ | ✅ green (C1 PASS) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| UAT Test 2 prohibition review (P1/P2/P3 accepted) | MODEL-05 | Human judgment on must-NOT acceptance | Read 10-VERIFICATION.md prohibitions against cited code; accept or raise blocking finding — done, accepted |
| UAT Test 1 + Test 3 retest confirmation after 10-05 | MODEL-05 | User-witnessed live proof | Run the keyed live test and c1 rig; confirm pass — done, 18/18 UAT pass |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s (per-task quick command: 115 passed in 4.34s; full suite ~45s runs per-wave only)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-10-13
