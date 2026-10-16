---
phase: "12"
slug: "structural-review-hygiene"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-16"
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x via `uv run` + persistent gates (ruff, xenon, import-linter) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `[tool.ruff]`, `[tool.importlinter]`) |
| **Quick run command** | `uv run ruff check strands_code_cli tests scripts && uv run ruff format --check strands_code_cli tests scripts` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~55 seconds (full suite 1538 passed, 11 deselected) |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` command (gate subset or focused suite)
- **After every plan wave:** Run `uv run pytest tests/ -q` plus all four gates
- **Before `$gsd-verify-work`:** Full suite + all gates must be green
- **Max feedback latency:** ~55 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-T1 | 01 | 1 | STRUCT-01, CLEANUP-01 | T-12-01 / T-12-03 | Pinned dev deps, D-15 deletion, zero dangling refs | unit (tracer) | `uv run pytest tests/ -q` | ✅ | ✅ green |
| 12-01-T2 | 01 | 1 | STRUCT-01 | — | Whole-tree ruff format + autofix, upstream byte-identical | lint | `uv run ruff check ... && uv run ruff format --check ...` | ✅ | ✅ green |
| 12-01-T3 | 01 | 1 | STRUCT-01 | — | Radon measurement + committed docs/STRUCTURE.md | report | `radon cc` red-block count 0 on new code | ✅ | ✅ green |
| 12-02-T1 | 02 | 2 | STRUCT-01 | T-12-05 | Repackage-door checkpoint recorded before any move | decision | (recorded, no code) | ✅ | ✅ green |
| 12-02-T2 | 02 | 2 | STRUCT-01 | T-12-04 | Package skeleton + loop-area pure moves (0/0 purity) | unit | `uv run pytest tests/ -q` | ✅ | ✅ green |
| 12-02-T3 | 02 | 2 | STRUCT-01 | — | Loop decomposition to xenon-clean (run_loop F→C) | unit + gate | `xenon --max-absolute C` + suite | ✅ | ✅ green |
| 12-03-T1 | 03 | 3 | STRUCT-01 | T-12-06 / T-12-07 | Remaining moves + import rewrite + entry re-sync; agent-bound OK | unit + gate | sweep + `strands-code --help` + suite | ✅ | ✅ green |
| 12-03-T2 | 03 | 3 | STRUCT-01 | — | Test mirror (44 files) + path re-homing, ROOT-CLEAR | unit | `uv run pytest tests/ -q` | ✅ | ✅ green |
| 12-03-T3 | 03 | 3 | STRUCT-01 | — | Tree-wide gate-green decomposition | unit + gate | `xenon --max-absolute C` + suite | ✅ | ✅ green |
| 12-04-T1 | 04 | 4 | STRUCT-01 | T-12-08 | Shared uattest lib extraction, scenarios import it | unit | `uv run pytest tests/rig/ -q` | ✅ | ✅ green |
| 12-04-T2 | 04 | 4 | STRUCT-01 | T-12-09 | Per-area scenarios + thin dispatch, same command | unit + rig | `driver.py a1` → A1 PASS | ✅ | ✅ green |
| 12-04-T3 | 04 | 4 | STRUCT-01 | — | Contract tests split, 26/26 assertions re-homed | unit (audit) | `uv run pytest tests/rig/ -q` | ✅ | ✅ green |
| 12-05-T1 | 05 | 5 | CLEANUP-01 | — | README rewrite + AGENTS refresh, ships-only | docs | grep-absence + re-read | ✅ | ✅ green |
| 12-05-T2 | 05 | 5 | STRUCT-01 | T-12-10 / T-12-11 | Blocking CI gates + pre-commit, fork-scoped | gate | CI workflow + hooks present | ✅ | ✅ green |
| 12-05-T3 | 05 | 5 | STRUCT-01 | — | Final green proof: suite, gates, rig spots, hygiene | proof | full battery | ✅ | ✅ green |
| 12-06-T1 | 06 | 6 | STRUCT-01 | T-12-13 | CONVENTIONS.md source lines fixed | docs | grep-absence | ✅ | ✅ green |
| 12-06-T2 | 06 | 6 | STRUCT-01 | T-12-13 | AGENTS.md mirror + project re-sync, both clean | docs | grep-absence + re-read | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| UAT live checks (cold boot, STRUCTURE.md read, package shape, entry, instruction re-read) | STRUCT-01, CLEANUP-01 | Human-witnessed structure + doc coherence | Boot CLI, read reports, run shape commands — done, 16/16 UAT pass |
| G-12-1 retest confirmation after 12-06 | STRUCT-01 | User-witnessed doc fix | Re-read AGENTS.md head, confirm GitHub line gone — done, user picked drop-it wording |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s (per-task gate subset: ruff ~2s; full suite ~55s runs per-wave only)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-10-16
