---
phase: "09"
slug: "native-typesafe-decision-engine"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-12"
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x via `uv run` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `uv run pytest tests/test_routing.py tests/test_routing_strategy.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~18 seconds (full suite 1363 passed, 10 deselected) |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` command (quick routing trio or focused files)
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~18 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-T1 | 01 | 1 | MODEL-04 | T-9-01 | Header-only call-time key; stubbed native ask routes end to end | unit + stub-server | `uv run pytest tests/test_routing.py tests/test_routing_strategy.py -x -q` | ✅ | ✅ green (278 passed) |
| 09-01-T2 | 01 | 1 | MODEL-04 | T-9-01 | 4xx holds with zero retry; keyless skip; computed spend rendered | unit | `uv run pytest tests/test_routing.py tests/test_cost_context.py -x -q` | ✅ | ✅ green (232 passed) |
| 09-01-T3 | 01 | 1 | MODEL-04 | T-9-03 | Order/model judging with fix lines; secret-drop on save | unit | `uv run pytest tests/test_routing_strategy.py -x -q` | ✅ | ✅ green (91 passed) |
| 09-02-T1 | 02 | 2 | MODEL-04 | T-9-02 | Setup proposes native-first only with key; pinned Jev list; no key prompts | unit | `uv run pytest tests/test_router_setup.py -x -q` | ✅ | ✅ green (24 passed) |
| 09-02-T2 | 02 | 2 | MODEL-04 | T-9-01 | Live-ping maps failures to notes; skip note once per session | unit | `uv run pytest tests/test_router_setup.py tests/test_loop_routing.py -x -q` | ✅ | ✅ green (86 passed) |
| 09-02-T3 | 02 | 2 | MODEL-04 | — | Docs name key env var and pinned Jev string | docs-grep | `grep -c 'TYPESAFE_API_KEY' docs/ROUTING.md && grep -c 'jev-1.13.0' docs/ROUTING.md` | ✅ | ✅ green (3 + 2 matches) |
| 09-03-T1 | 03 | 2 | MODEL-04 | T-9-01 | Probe runner `--run native` with native fault set; bogus key only | script + unit | `python3 scripts/route-probe.py --dry-run && uv run pytest tests/test_routing_calibration.py -q` | ✅ | ✅ green (34 passed) |
| 09-03-T2 | 03 | 2 | MODEL-04 | T-9-03 | 20-probe native run diffs shared baseline clean | live-probe | `python3 scripts/route-probe.py --run native && python3 scripts/route-probe.py --compare` | ✅ | ✅ green (20 verdicts, compare clean) |
| 09-03-T3 | 03 | 2 | MODEL-04 | T-9-02 | Live native tests pass with key, skip without, fail loudly on rejection | integration (env-gated) | `uv run pytest tests/test_routing.py::TestLiveEngines -q -rs` | ✅ | ✅ green (stub passes by default; 2 native live pass with `-m integration`) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Audit 2026-10-12

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

State A audit: all 9 `<automated>` commands re-run green 2026-10-12 (278 + 232 + 91 + 24 + 86 + docs-grep + 34 + 20-probe compare-clean + live stub/integration). No auditor spawn required (no gaps).

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-10-12
