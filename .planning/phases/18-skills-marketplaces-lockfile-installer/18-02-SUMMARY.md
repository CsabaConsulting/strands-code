---
phase: 18-skills-marketplaces-lockfile-installer
plan: "02"
subsystem: cli-skills-policy-completion
tags: [skills, completer, policy, dispatch, agent-skills, provenance]
requires:
  - phase: 18-01
    provides: Marketplace registry, HTTPS tarball unpack, lockfile & hash verifier
provides:
  - Multi-namespace SkillIndex with local: tie win, hash-drift warn-and-skip, and read-only discover_plugin_sources()
  - Dynamic /<ns>: prefix completion in SlashCompleter
  - Protected-path Prompt downgrade in policy/core.py:decide() on broad [[allow]] rules
  - Full /skills CLI dispatch verbs & third-party @ <short_sha> provenance framing
  - AgentSkills startup + live reload synchronization across entry/main.py & loop/core.py
affects:
  - strands_code_cli/memory/skills.py
  - strands_code_cli/memory/marketplace.py
  - strands_code_cli/ui/completer.py
  - strands_code_cli/policy/core.py
  - strands_code_cli/dispatch/core.py
  - strands_code_cli/entry/main.py
  - strands_code_cli/loop/core.py
  - tests/memory/test_skills.py
  - tests/policy/test_policy.py
  - tests/policy/test_policy_gate.py
key-files:
  modified:
    - strands_code_cli/memory/skills.py
    - strands_code_cli/memory/marketplace.py
    - strands_code_cli/ui/completer.py
    - strands_code_cli/policy/core.py
    - strands_code_cli/dispatch/core.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/loop/core.py
    - tests/memory/test_skills.py
    - tests/policy/test_policy.py
    - tests/policy/test_policy_gate.py
requirements-completed:
  - SKILL-03
completed: 2026-11-24
---

# Phase 18 Plan 02 Summary: `SkillIndex`, `SlashCompleter`, Protected-Path Policy, `/skills` Dispatch & `AgentSkills` Sync

**Executed:** 2026-11-24
**Status:** Complete

## Changes Delivered

1. **[skills.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/skills.py) & [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py):**
   - Extended `SkillEntry` with provenance metadata (`commit_sha`, `source_url`, `has_scripts`, `script_files`).
   - Extended `SkillIndex` to index verified `./.agent/skills-marketplaces/<ns>/<skill>/` skills alongside `./.agent/skills/` (`local:`), keeping `local:` winning bare-name resolution collisions and failing closed on ambiguous bare marketplace names (`ambiguous_matches`).
   - Added non-mutating `discover_plugin_sources()` (`[*(verified_marketplace_dirs), str(skills_dir)]`) so `local:` wins ties in `AgentSkills` while drifted/tampered/symlinked marketplace entries are skipped and surfaced via `SkillIndex.warnings`.
   - Extended `SkillIndex.remove()` to remove marketplace directories & evict `./.agent/skills-lock.json` entries (including explicitly targeted drifted/symlinked entries) while keeping `./.agent/skills/` symlink refusal intact.
   - Tightened `discover_catalog_from_tarball` per-file byte limit check and `remove_installed_skill` parent symlink check.
2. **[completer.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/completer.py):**
   - Generalized `SlashCompleter.get_completions` to derive valid `/<ns>:` prefixes dynamically from live `get_words()` displays while leaving unknown namespaces empty.
3. **[core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/core.py):**
   - Added `_is_protected_skills_or_config_path()` using canonical `realpath` & normalized resolution against `.agent/skills*`, `.agent/skills-lock.json`, and `platformdirs.user_config_dir("strands-code")`.
   - Updated `decide()` (`C 15`) so `[[deny]]` stays first and broad `[[allow]]` write/edit rules targeting protected paths downgrade from `Allow()` to `Prompt(...)`.
4. **[core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), & [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py):**
   - Wired `/skills marketplace|browse|install|update|sync|show|remove|uninstall|reload|refresh` into `dispatch/core.py` via delegated helpers (`_skills_marketplace_cmd` `C 13`, `_skills_message` `C 13`, `_skills_show_cmd` `C 12`, `_skills_remove_cmd` `C 12`; `_setup_decision_entries` untouched at `C 20`).
   - Framed third-party skill invocations explicitly with `@ <short_sha>` provenance and untrusted-instructions warnings while preserving exact `local:` prompt wording and `USAGE_HINT` integration.
   - Wired `discover_plugin_sources()` into `entry/main.py:build_agent` (`C 14`) and `loop/core.py:_refresh_harness_skills` (`run_loop` unchanged at `C 18`).
5. **Tests:**
   - Expanded [test_skills.py](file:///home/csaba/repos/AWS/strands-code/tests/memory/test_skills.py), [test_policy.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_policy.py), and [test_policy_gate.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_policy_gate.py) with multi-namespace resolution, hash-drift exclusion, dynamic `/<ns>:` completion, HITL protected-path prompt enforcement, end-to-end `/skills` dispatch workflows, real `AgentSkills` sync proof, and startup warning output.

## Verification

- `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` -> **1779 passed** (`14 deselected` matching `test_stub_server_systemone_decision_routes` + `-m 'not integration'`)
- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **123 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli tests scripts` -> **Passed** (`_setup_decision_entries C 20` untouched, `_skills_message C 13`, `decide C 15`, `run_loop C 18`)
- `.venv/bin/lint-imports` -> **1 kept, 0 broken**
- `git diff ee42ea2 -- strands_code_agent/` -> **Empty** (`D-24`)
