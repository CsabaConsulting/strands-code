---
phase: 02-file-edit-shell-surface-diff
plan: 02
subsystem: tool-surface-diff-grep
tags: [harness-builtins, diff-gate, rg-wrapper, scope-guard, slash-commands, tracer]
requires: [TOOL-01, TOOL-02, TOOL-04]
provides: [builtin-tools-mapping, scope-guard, diff-gate-modes, search-tool, diff-search-commands]
affects: [03-permissions-gate, 04-plan-act-modes]
tech-stack:
  added: []
  patterns: [builtin_tools-mapping, ProviderConfig-persistence-analog, sidecar-pending-state, argv-list-subprocess]
key-files:
  created:
    - strands_code_cli/scope.py
    - strands_code_cli/diff_config.py
    - strands_code_cli/diff_gate.py
    - strands_code_agent/search_tool.py
    - tests/test_tool_surface.py
    - tests/test_diff_gate.py
    - tests/test_search.py
  modified:
    - strands_code_cli/main.py
    - strands_code_cli/router.py
    - strands_code_agent/code_agent.py
    - strands_code_agent/callback_handler.py
key-decisions:
  - No strands-agents-tools: harness 0.1.2 builtins (shell/read/write/edit) via builtin_tools mapping
  - Diff gate as wrapper tools (not harness interventions) to keep Phase 3 TOOL-03 machinery out of scope
  - python_repl stays compute-first; prompt steers mutation to dedicated tools
  - Shell/python_repl diff bypass documented as advisory; airtight mediation is Phase 3
requirements-completed: [TOOL-01, TOOL-02, TOOL-04]
duration: unexecuted (plan only)
completed: 2026-09-25
---

# Phase 02 Plan 02: Tool Surface + /diff + Grep Summary

Single plan covering Phase 2: wire harness builtin file/shell tools with a
cwd+/tmp scope guard, gate mutations behind a mode-persisted /diff wrapper
gate, add a local rg-wrapper search tool with /search, and render both
through the callback handler — tracer slice first, then parallel waves.

## Accomplishments (planned)

- Tracer proves harness default builtins live, then pins an explicit
  `builtin_tools` mapping in `build_agent` (no `strands_tools` import).
- `scope.py` confines file paths to cwd+subdirs and `/tmp`, resolving
  relative input before the harness absolute-path check.
- `diff_gate.py` wrappers (same names, builtins pinned off) implement
  approve-each / on-demand / auto with sidecar pending state and loud
  TOCTOU failure; `diff_config.py` persists the mode ProviderConfig-style.
- `search_tool.py` gives the agent lexical grep (rg + stdlib fallback);
  `/diff` and `/search` route as reply-only commands.
- Callback handler renders unified diffs via `Syntax("diff")` in-turn.

## Key decisions

- Wrapper-gate over `interventions="ask"`: least Phase 3 bleed; policy file
  and all-tool approval stay in Phase 3, general yolo stays in Phase 4.
- `python_repl` role (D-03): unrestricted compute, prompt-steered to
  dedicated tools; `open()` bypass recorded as known hole.
- Per-hunk granularity only in approve-each; whole-change in on-demand;
  none in auto (D-04).

## Risks carried forward

- Shell redirection and `python_repl` writes bypass `/diff` (advisory).
- Approve-each prompts inside subagent turns may be noisy (inherited gate).
- Diff `auto` vocabulary must not collide with the Phase 4 mode system.

## Scope fenced out

TOOL-03 policy file, network gating, mode system, persistent index,
strands-agents-tools — verification ends with a grep for
`strands_tools`, `interventions`, `policy` in the diff.
