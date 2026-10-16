---
phase: 11-codeact-action-interface
plan: "04"
subsystem: cli
tags: [codeact, typer-flag, argv-normalization, gap-closure, uat-live-gate]

requires:
  - phase: 11-codeact-action-interface (11-01)
    provides: Valued --codeact flag with BadParameter pre-gate rejection before the credential gate
provides:
  - Bare --codeact boots the session into code mode (G-11-1 closed)
  - _expand_bare_codeact argv helper with startup tests and a green a1 rig re-run
affects: [11-UAT gap G-11-1, codeact-executor, startup-flags]

actuals:
  tokens: 1210
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns: [argv-pre-normalization-for-optional-flag-values]

key-files:
  created: []
  modified: [strands_code_cli/main.py, tests/test_codeact.py]

key-decisions:
  - "argv pre-normalization over typer flag_value/is_flag: the pinned typer never forwards them to click (deprecation warning only), so the helper rewrite is the mechanism"
  - "Expansion fires only when the next token is missing or dash-led; valued, equals, and post--- tokens pass through byte-identical"

patterns-established:
  - "Optional-value CLI flags via pure argv helpers: match the exact token, respect the -- sentinel, never mutate the input list"

requirements-completed: [TOOL-07]

coverage:
  - id: D1
    description: "Bare --codeact boots the session into code mode without requiring a value"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStartupFlag bare-flag helper and main() wiring cases"
        status: pass
      - kind: e2e
        ref: "python3 scripts/uattest/driver.py a1 (A1 PASS, /tmp/uatr8/a1.log carries 'Interface: code')"
        status: pass
    human_judgment: false
  - id: D2
    description: "Explicit tool/code/both still accepted; any other value still rejected pre-gate"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStartupFlag::test_invalid_flag_rejected_before_side_effects"
        status: pass
    human_judgment: false

duration: 2min
completed: 2026-10-16
status: complete
---

# Phase 11 Plan 04: Bare --codeact implies code (G-11-1) Summary

**Bare `--codeact` boots the session into code mode via argv pre-normalization, with valued forms and pre-gate rejection intact and the red a1 rig scenario green.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-10-16T03:37:06Z
- **Completed:** 2026-10-16T03:39:08Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `_expand_bare_codeact` in `main.py` inserts the implied `code` value after a value-less `--codeact`; `main()` applies it to a `sys.argv` copy before typer parses
- Startup tests pin every argv shape (bare end, bare before flag, valued/equals untouched, `--` sentinel, no input mutation) plus a `main()` wiring test asserting `run_loop` receives `codeact="code"`
- Red rig scenario a1 turns green: boots on bare `--codeact`, bare `/codeact` reports code mode, `A1 PASS` with exit 0
- BadParameter membership check kept byte-identical before the credential gate; `--codeact turbo` still rejected with zero side effects

## Task Commits

Each task was committed atomically:

1. **Task 1: Bare-flag argv expansion in main.py (bare implies code)** - `e5539ee` (fix)
2. **Task 2: Bare-flag startup tests plus a1 live gate** - `4ce5b5e` (test)

**Plan metadata:** `docs: complete plan` (this SUMMARY — hash below)

## Files Created/Modified

- `strands_code_cli/main.py` - `_expand_bare_codeact` helper, `main()` call site, `sys` import, `--codeact` help text naming the bare form
- `tests/test_codeact.py` - 6 new bare-flag tests in `TestCodeactStartupFlag` (7 cases with parametrization), `sys` import

## Decisions Made

- argv pre-normalization over `typer` `flag_value`/`is_flag`: the pinned typer never forwards them to click, so the pure helper rewrite is the mechanism (per plan).
- No new test file: bare-flag coverage extends the existing `TestCodeactStartupFlag` class shapes (per plan).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- G-11-1 closed: UAT test 3 satisfied, all 20 Phase 11 UAT tests now passing.
- Phase 11 gap closure complete; ready for verify/transition.
- Evidence (not committed): `/tmp/uatr8/a1.log` carries the green a1 transcript with `Interface: code`.

---
*Phase: 11-codeact-action-interface*
*Completed: 2026-10-16*
