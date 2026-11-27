---
phase: 21-cli-ergonomics-help-file-review
plan: "01"
subsystem: cli-help-guard-media
tags: [help, cve-2026-18830, tool-use-guard, document-block, model-switch]
requires:
  - phase: 16-meta-model-api
    provides: supports_media provider/model scoping and RichHistory stashes
  - phase: 20-monty-python-vm-for-python-repl-codeact
    provides: 3-site CLI agent symmetry across main, btw, and subagent
provides:
  - Single declarative slash command registry in strands_code_cli/dispatch/help.py driving both /help [name] and USAGE_HINT
  - BUILTIN_SLASH_HEADS extended with help, file, review (25 built-in heads)
  - 3-site fail-closed RejectCallerToolUseHook (BeforeInvocationEvent.cancel) and validate_content_blocks allowlist in strands_code_cli/policy/tool_use_guard.py
  - Full "document" block conversion, RichHistory stash preservation, canonical_prefix_hash stripping, and _block_chars accounting
affects:
  - 21-02-PLAN.md (uses validate_content_blocks and document conversion)
  - 21-03-PLAN.md (builds on /help registry and dispatch/core.py wiring)
tech-stack:
  added: []
  patterns:
    - Single declarative CommandSpec tuple powering USAGE_HINT and grouped /help output
    - Idempotent BeforeInvocationEvent hook at HookOrder.SDK_FIRST across main, /btw, and subagent
key-files:
  created:
    - strands_code_cli/dispatch/help.py
    - strands_code_cli/policy/tool_use_guard.py
    - tests/dispatch/test_help.py
    - tests/policy/test_tool_use_guard.py
  modified:
    - strands_code_cli/memory/skills.py
    - strands_code_cli/dispatch/core.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/loop/btw.py
    - strands_code_cli/entry/subagent.py
    - strands_code_cli/model/model_switch.py
    - strands_code_cli/cost/cost_context.py
    - tests/model/test_model_switch.py
    - tests/cost/test_cost_context.py
key-decisions:
  - "D-01/D-02: Declarative dispatch/help.py registry drives USAGE_HINT and resolves both built-in commands and loaded skills."
  - "D-07: model_switch.py converts 'document' blocks to '[document: <name>/<format>, <N> bytes]' on media-less targets and keeps canonical_prefix_hash stable."
  - "D-08: RejectCallerToolUseHook attaches fail-closed at all 3 CLI agent factories via BeforeInvocationEvent.cancel."
patterns-established:
  - "validate_content_blocks strictly allowlists text/image/document ContentBlock dicts."
requirements-completed:
  - LOOP-06
  - TOOL-05
duration: 8min
completed: 2026-11-27
---

# Phase 21 Plan 01: Tracer Summary

**Declarative `/help` registry (`dispatch/help.py`), 3-site CVE-2026-18830 `RejectCallerToolUseHook`, and `"document"` model-switch parity shipped.**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-11-27
- **Tasks:** 2 / 2
- **Files modified:** 13

## Accomplishments
- Added [help.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/help.py) with `CommandSpec`, grouped `COMMANDS` (25 built-in heads matching `BUILTIN_SLASH_HEADS` 1:1), `build_usage_hint()`, and `/help [name]` lookup across built-ins and `SkillIndex` entries/warnings sanitized via `sanitize_display()`.
- Added [tool_use_guard.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/tool_use_guard.py) (`validate_content_blocks`, `contains_caller_tool_use`, `RejectCallerToolUseHook`, `register_reject_caller_tool_use_hook`) wired idempotently across `build_agent`, `build_btw_agent`, and `build_cli_subagent`.
- Extended `model_switch.py` (`_MEDIA_PLACEHOLDER_RE`, `_canonical_block`, `_media_placeholder_block`, `_convert_block`) and `cost_context.py` (`_block_chars`) to convert and hash `"document"` blocks cleanly across switches and stashes.

## Deviations from Plan
- Added two-arg `add_hook(cb, event_type)` fallback inside `register_reject_caller_tool_use_hook()` and registered the child hook prior to `_strip_foreign_signatures_hook` in `entry/subagent.py` so existing two-arg subagent test doubles in `tests/entry/test_subagent.py` remain green.

## Verification
- Targeted Wave 1 suites (`351 passed`), `ruff format --check`, `ruff check`, `xenon --max-absolute C`, `lint-imports` (`1 kept, 0 broken`), and `git diff ee42ea2 -- strands_code_agent/` (empty) all passed after the final edit.
