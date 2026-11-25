---
phase: 18-skills-marketplaces-lockfile-installer
plan: "03"
subsystem: integration-docs-ci
tags: [github, integration, documentation, ci, quickstart]
requires:
  - phase: 18-02
    provides: Full marketplace CLI, SkillIndex, SlashCompleter, PolicyConfig & AgentSkills wiring
provides:
  - Opt-in live GitHub marketplace probe against public anthropics/skills
  - Documentation section in docs/QUICKSTART.md
  - Full CI gate + test suite sign-off across all 1781 verified test invocations
affects:
  - tests/memory/test_marketplace.py
  - docs/QUICKSTART.md
key-files:
  modified:
    - tests/memory/test_marketplace.py
    - docs/QUICKSTART.md
requirements-completed:
  - SKILL-03
completed: 2026-11-24
---

# Phase 18 Plan 03 Summary: Live GitHub Probe, Documentation & Full CI Gates

**Executed:** 2026-11-24
**Status:** Complete

## Changes Delivered

1. **[test_marketplace.py](file:///home/csaba/repos/AWS/strands-code/tests/memory/test_marketplace.py):**
   - Added `@pytest.mark.integration` probe `test_live_github_marketplace_browse_install_and_verify` targeting public `anthropics/skills` (`.claude-plugin/marketplace.json`) into isolated `tmp_path`.
   - Verified end-to-end against live GitHub API + `codeload.github.com` single-hop redirect: catalog discovery, single-skill tarball install, 40-char `commit_sha` + deterministic `sha256:` lockfile verification, `SkillIndex` resolution, and fail-closed hash-drift exclusion when on-disk `SKILL.md` mutates (skipping cleanly on offline or rate-limited HTTP errors).
2. **[QUICKSTART.md](file:///home/csaba/repos/AWS/strands-code/docs/QUICKSTART.md):**
   - Added `## Skills marketplaces` documenting opt-in `/skills marketplace add|list|update|remove`, `/skills browse|install|update|sync|show|remove`, `/<ns>:<skill>` tab completion, `./.agent/skills/` (`local:`) tie precedence, `./.agent/skills-lock.json` SHA-256 pinning, optional `GITHUB_TOKEN`/`GH_TOKEN` rate-limit configuration, and deny-first supply-chain safeguards.

## Verification

- **Live GitHub probe:** `.venv/bin/pytest tests/memory/test_marketplace.py -m integration -v` -> **1 skipped** inside network-isolated sandbox; **1 passed** (4.55s) with outbound HTTPS enabled against live `anthropics/skills`.
- **Rig contracts:** `.venv/bin/pytest tests/rig/ -q` -> **44 passed** (0.09s).
- **Default test suite:** `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` -> **1779 passed** (15 deselected: 14 integration + 1 loopback).
- **Loopback routing stub:** `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` -> **1 passed** (2.11s).
- **6/6 CI Gates:**
  1. `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **123 files already formatted**
  2. `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
  3. `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> **Passed**
  4. `.venv/bin/lint-imports` -> **1 kept, 0 broken** (`41 files, 91 dependencies`)
  5. `/home/csaba/.local/bin/uv lock --check` -> **Passed** (`Resolved 156 packages in 2ms`)
  6. `git diff ee42ea2 -- strands_code_agent/` -> **Empty** (`D-24`)
