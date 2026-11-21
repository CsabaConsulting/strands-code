---
phase: 11-codeact-action-interface
plan: "02"
subsystem: cli
tags: [codeact, stint, sandboxed-interpreter, both-routing, slash-command, tool-registry]

requires:
  - phase: 11-codeact-action-interface/01
    provides: CodeactState holder + fix-at-send seams + /codeact toggle + turn_interfaces
provides:
  - CodeactStint loop-owned interpreter with sync confined read/write/edit/shell
  - Per-turn python_repl swap onto the stint with boundary restore
  - Both-mode /code + /tool one-shot routing with bare-ask usage reply
affects: [11-03, codeact-executor, approval-preview, both-routing]

actuals:
  tokens: 10067
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns: [stint-lifecycle, per-turn-tool-swap, one-shot-routing-arm, fail-soft-handle-capture]

key-files:
  created: []
  modified: [strands_code_cli/codeact.py, strands_code_cli/loop.py, strands_code_cli/router.py, strands_code_cli/skills.py, tests/test_codeact.py]

key-decisions:
  - "Interior functions are module-level codeact_* with cwd-first signatures bound via functools.partial (probe-verified in smolagents additional_functions)"
  - "Swap/restore are explicit seam functions with a turn-local flag restored in the loop's existing outer turn finally (covers attempts plus revise rounds plus cancel)"
  - "stint.tool is evaluated only on code turns at the fix-at-send site, preserving stint laziness on the default tool path"
  - "New swap tests carry turn_setup in method names — the pre-existing TestTurnSetup class never matched the plan's -k turn_setup filter (no underscore)"

patterns-established:
  - "Stint lifecycle: loop owns one lazily built interpreter; reset() on every holder switch, never on turn boundaries"
  - "Fail-soft swap: absent default handle or registry skips the swap and the code turn stays prefix-shaped"
  - "One-shot routing arm: arm_one_shot(code|tool) consumed exactly once by resolve_turn, sticky value never moves"

requirements-completed: [TOOL-07]

coverage:
  - id: D1
    description: "Code turns run in a stint-scoped sandbox with file/shell parity functions"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStintLifecycle"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactInteriorFunctions"
        status: pass
    human_judgment: false
  - id: D2
    description: "Stint REPL persists within the stint, resets on switch, never bleeds into tool turns"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStintLifecycle::test_reset_clears_stint_state"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStintLifecycle::test_loop_owns_stint_and_resets_on_switch"
        status: pass
    human_judgment: true
    rationale: "Stint reset semantics execute under test, but the run_loop stint.reset() call site fires only on a live /codeact switch — confirm one live switch starts a fresh stint"
  - id: D3
    description: "Code turns execute through the stint interpreter; tool turns use the always-on interpreter unchanged"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactSwap"
        status: pass
    human_judgment: true
    rationale: "Swap/restore seams execute under test against a fake registry, but the fix-at-send swap and boundary restore lines run only in a live turn — confirm one live code turn executes in the stint and the next tool turn is unshaped"
  - id: D4
    description: "Both-mode routes each ask explicitly via /code or /tool; bare asks get the routing usage reply"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactBothRouting"
        status: pass
    human_judgment: false
  - id: D5
    description: "No approval prompt, dialog, or stdin read exists anywhere on the execution path"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStintLifecycle::test_no_prompt_dialog_stdin_on_execution_path"
        status: pass
    human_judgment: false
  - id: D6
    description: "Full suite stays green with the stint, swap, and routing changes merged"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "uv run pytest tests/ -q (1529 passed, 11 deselected)"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-10-15
status: complete
---

# Phase 11 Plan 02: Stint execution plus both-mode routing Summary

**Loop-owned `CodeactStint` with confined read/write/edit/shell parity, per-turn `python_repl` swap onto the stint with boundary restore, and explicit `/code` + `/tool` one-shot routing for both-mode — tool turns byte-identical.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-10-15T22:11:37Z
- **Completed:** 2026-10-15T22:17:30Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- `CodeactStint` owns one lazily built `SandboxedPythonInterpreter` (`authorized_imports` exactly `{"math"}`, 60s timeout) with sync scope-confined `read`/`write`/`edit`/`shell` bare-name functions; REPL state persists across code turns, `reset()` clears on every `/codeact` switch, and interior functions return error strings (never raise, never touch prompt/dialog/stdin)
- Fix-at-send swaps the stint `python_repl` in via public `ToolRegistry.replace` for code turns only, restoring the startup-captured default in the turn `finally` (covers the attempts loop, revise rounds, and mid-turn failure/cancel); tool turns record zero `replace` calls and side-agent btw paths never swap
- `/code <ask>` and `/tool <ask>` arm the holder for exactly one turn then fall back to sticky; bare asks in both-mode reply `Usage: /code <ask> or /tool <ask>` instead of silently defaulting; `code`/`tool` join `BUILTIN_SLASH_HEADS` and `USAGE_HINT`
- Threat mitigations T-11-04 (math-only allowlist), T-11-05 (argv-only shell, no `shell=True`), T-11-06 (reset on switch), T-11-07 (public replace, restore in finally) each pinned by a failing-closed test

## Task Commits

Each task was committed atomically:

1. **Task 1: Stint lifecycle plus sync interior file/shell functions** - `394c63e` (feat)
2. **Task 2: Per-turn python_repl swap onto the stint for code turns** - `a4a478c` (feat)
3. **Task 3: Both-mode per-ask routing via /code and /tool one-shot prefixes** - `505e162` (feat)

**Plan metadata:** `docs: complete plan` (this SUMMARY — hash below)

## Files Created/Modified

- `strands_code_cli/codeact.py` - `CodeactStint`, `codeact_read`/`codeact_write`/`codeact_edit`/`codeact_shell`, `arm_one_shot`/`resolve_turn`, `CODEACT_ROUTE_USAGE`, `default_repl_handle`/`swap_for_code_turn`/`restore_after_turn`
- `strands_code_cli/loop.py` - Loop-owned stint + startup default-handle capture, post-dispatch `stint.reset()`, fix-at-send swap, turn-finally restore, `resolve_turn` consumption
- `strands_code_cli/router.py` - `/code` + `/tool` branches with `_codeact_route_action`, both-mode bare-ask usage reply, `USAGE_HINT` entries
- `strands_code_cli/skills.py` - `"code"` + `"tool"` join `BUILTIN_SLASH_HEADS` (shadow warnings automatic)
- `tests/test_codeact.py` - 53 new tests: `TestCodeactStintLifecycle`, `TestCodeactInteriorFunctions`, `TestCodeactSwap`, `TestCodeactBothRouting` (109 total in file, all green)

## Decisions Made

- Interior functions are module-level `codeact_*` with cwd-first signatures, bound into `additional_functions` via `functools.partial` — a live probe confirmed partials and a frozenset allowlist work in smolagents, and return values surface through `print()` (the `(stdout, stderr)` tuple carries logs only).
- Swap/restore are explicit seam functions (`swap_for_code_turn` returning the turn-local flag, `restore_after_turn` in the loop's existing outer turn `finally`) rather than a context manager — matches the plan's flag wording and one `finally` covers the attempts loop, revise rounds, and the cancel path.
- `stint.tool` is evaluated only on code turns (`stint.tool if turn_interface == "code" else None`) so the default tool path never builds the stint interpreter.
- New swap tests carry `turn_setup` in method names: the pre-existing `TestTurnSetup` class never matched the plan's `-k turn_setup` filter (verified: zero collected before this plan), so the filter alone would have reported "no tests ran" without them.
- The mid-turn-exception test pins the seam contract (swap, try/finally, restore) plus a loop source-pin; the loop `finally` itself runs only in a live turn (see coverage D3).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Stint execution, per-turn swap, and both-mode routing are complete; 11-03 (whole-block approval preview plus coherence pins) builds on `CodeactStint`, the swap seams, and `resolve_turn` consumption.
- Verify-time manual checks (see coverage D2/D3): one live `/codeact` switch proving a fresh stint, one live code turn proving stint execution with an unshaped tool turn after it.
- Plan 11-03 should keep its `-k` filters literal-substring-safe (class names need the exact filter text, e.g. `TestCodeactApproval` matches `-k approval` but `TestTurnSetup` never matched `-k turn_setup`).

---
*Phase: 11-codeact-action-interface*
*Completed: 2026-10-15*
