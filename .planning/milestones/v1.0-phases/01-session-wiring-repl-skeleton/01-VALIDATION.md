---
phase: "1"
slug: "session-wiring-repl-skeleton"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-23"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `integration` marker deselected by default) |
| **Quick run command** | `uv run pytest tests/ -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (seeded — planner fills per plan) | 01 | 1 | LOOP-01, SES-01, SES-03 | — | N/A | unit/integration | `uv run pytest tests/ -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Existing infrastructure covers all phase requirements (`tests/` + `pyproject.toml` pytest config present, suite green at 177 passed).

*No new Wave 0 stubs required unless the planner introduces untestable seams (e.g. REPL I/O without a harness).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SIGKILL then resume restores full state | SES-03 | Killing the dev's own shell process cannot be automated safely in CI | Start CLI, begin a task, `kill -9` the process, resume by UUID, confirm transcript + pending state intact |
| Resume picker lists recent sessions | SES-01 | Interactive terminal picker needs a human eye | Launch with prior sessions present, confirm picker lists them with titles |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
