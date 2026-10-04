---
phase: "6"
slug: "skills-memory-file"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-04"
---

# Phase 6 — Validation Strategy

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
| 06-01-T1 tracer (SkillIndex + /skill slash) | 01 | 1 | SKILL-01 | T-06-02 | skill bodies quoted as untrusted | unit | `uv run pytest tests/test_skills.py -x -q` | ❌ Wave 0 (task creates) | ⬜ pending |
| 06-01-T2 (/skills list/show/remove) | 01 | 1 | SKILL-01 | T-06-01 | traversal-guarded remove | unit | `uv run pytest tests/test_skills.py -x -q` | ❌ Wave 0 (task creates) | ⬜ pending |
| 06-01-T3 (completer + loop wiring) | 01 | 1 | SKILL-01 | — | shadowed names never complete | unit | `uv run pytest tests/ -q` | ✅ | ⬜ pending |
| 06-02-T1 (dual loader + injector) | 02 | 2 | SKILL-02 | T-06-03, T-06-04 | untrusted markers, symlink refusal | unit | `uv run pytest tests/test_memory_file.py -x -q` | ❌ Wave 0 (task creates) | ⬜ pending |
| 06-02-T2 (reload + flush) | 02 | 2 | SKILL-02 | — | notes carry names only | unit | `uv run pytest tests/test_memory_file.py -x -q` | ❌ Wave 0 (task creates) | ⬜ pending |
| 06-02-T3 (modes + /memory mode) | 02 | 2 | SKILL-02 | — | curate default | unit | `uv run pytest tests/ -q` | ✅ | ⬜ pending |
| 06-03-T1 (curate queue + review) | 03 | 3 | SKILL-02 | T-06-06 | single-HITL spine, deny never writes | unit | `uv run pytest tests/test_memory_curate.py -x -q` | ❌ Wave 0 (task creates) | ⬜ pending |
| 06-03-T2 (revise rounds) | 03 | 3 | SKILL-02 | T-06-06 | quoted review, fail-closed default | unit | `uv run pytest tests/test_memory_curate.py -x -q` | ❌ Wave 0 (task creates) | ⬜ pending |
| 06-03-T3 (/init scan + merge) | 03 | 3 | SKILL-02 | T-06-07 | capped scan, merge-never-clobber | unit | `uv run pytest tests/ -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Existing infrastructure covers all phase requirements (`tests/` + `pyproject.toml` pytest config present, suite green at 668 passed).

*No new Wave 0 stubs required unless the planner introduces untestable seams (e.g. completer behavior without a PromptSession harness).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Slash autocomplete completes `namespace:skill` while matching on bare skill name | SKILL-01 | Interactive PromptSession completion needs a human eye | Type `/` + partial skill name, confirm matches and completed form |
| /memory curate loop (approve/deny/revise-in-words) | SKILL-02 | Conversational revise rounds need human judgment | Trigger a memory proposal, approve one, deny one, revise one in words, confirm file state |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
