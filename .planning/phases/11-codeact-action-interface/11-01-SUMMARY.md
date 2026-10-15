---
phase: 11-codeact-action-interface
plan: "01"
subsystem: cli
tags: [codeact, session-toggle, slash-command, typer-flag, provider-config]

requires:
  - phase: 04-plan-act-modes-steering
    provides: ModeState holder + reply-only toggle-branch + per-turn prefix precedent
  - phase: 05-model-cost-context-commands
    provides: session_turns row shape + /cost report + ProviderConfig YAML + --session-id flag precedent
provides:
  - CodeactState session holder with tool/code/both values (default tool)
  - /codeact toggle branch + fix-at-send code-turn shaping + per-turn interface labels
  - --codeact flag + codeact/codeact_remember config keys + remember-last precedence + persist-on-switch
affects: [11-02, 11-03, codeact-executor, both-routing, approval-preview]

actuals:
  tokens: 10769
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns: [session-sticky-holder, reply-only-slash-branch, fix-at-send-turn-setup, per-turn-label-line, flag-over-remember-over-default-precedence]

key-files:
  created: [strands_code_cli/codeact.py, tests/test_codeact.py]
  modified: [strands_code_cli/router.py, strands_code_cli/skills.py, strands_code_cli/loop.py, strands_code_cli/main.py, strands_code_cli/provider_config.py]

key-decisions:
  - "Turn-setup lives in testable codeact.py seams (resolve_turn_interface, shape_turn_text, codeact_label); loop.py calls them at the mode/routing hook site"
  - "Both-holder turns resolve to tool-shaped until per-ask routing lands in 11-02"
  - "Remember-last gates the read path only; every /codeact switch persists the last choice unconditionally"
  - "Run-loop config read stays fail-loud like the model line (no tamper guard); load/save validation is the boundary"

patterns-established:
  - "Fix-at-send turn setup: resolve_turn_interface snapshots the holder value once before _invoke_agent; later flips wait for the next ask"
  - "Interface records ride a loop-owned turn_interfaces parallel list; session_turns rows and cost_report stay untouched"
  - "Startup precedence helper resolve_initial_interface(flag, saved, remember): flag first, then saved-when-remembered, else tool"

requirements-completed: [TOOL-07]

coverage:
  - id: D1
    description: "/codeact toggles the session interface with a transcript announcement; bare reports, invalid verbs show usage"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactState"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestRouterCodeact"
        status: pass
    human_judgment: false
  - id: D2
    description: "Code turns carry the code-first prefix at send; tool turns are byte-identical to today"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestTurnSetup"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactPrefix"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestTracer"
        status: pass
    human_judgment: false
  - id: D3
    description: "Every turn prints its interface label naming the interface used"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactLabel"
        status: pass
    human_judgment: true
    rationale: "Exact label strings are unit-tested, but the run_loop print_plain call site executes only in a live REPL turn — confirm one 'interface: tool/codeact' line per turn in a live session"
  - id: D4
    description: "Sessions start on tool-calling unless --codeact or remember-last config says otherwise; switches apply next-ask and persist"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStartupFlag"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStartupConfig"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStartupPrecedence"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactStartupPersist"
        status: pass
    human_judgment: true
    rationale: "Flag parse, config round-trip, precedence, and save path all execute under test, but the run_loop construction/persist lines are source-pinned only — confirm with one live --codeact start plus a /codeact switch and restart"
  - id: D5
    description: "Switching interfaces never mutates conversation history"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactHistory"
        status: pass
    human_judgment: false
  - id: D6
    description: "session_turns row shape and /cost rows unchanged by interface records"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactCostRows"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-10-15
status: complete
---

# Phase 11 Plan 01: Tracer — toggle plus shaped code turn end to end Summary

**`/codeact` session toggle with fix-at-send code-turn shaping, per-turn interface labels, and `--codeact`/config/remember-last startup surfaces — tool-calling default preserved, history and cost rows untouched.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-10-15T21:56:20Z
- **Completed:** 2026-10-15T22:06:57Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- `/codeact [tool|code|both]` flips a loop-owned `CodeactState` holder with transcript announcements; bare command reports, unknown verbs show usage, reply-only (no agent turn ever leaves the branch)
- Code turns prepend `CODEACT_PREFIX` (python_repl-first, read/write/edit/shell interior functions, absolute-path + scope rules, one-interface-per-turn) resolved once at send; tool turns byte-identical
- Every turn prints an exact `interface: tool` / `interface: codeact` dim line and records into a loop-owned `turn_interfaces` parallel list; `session_turns` rows and `cost_report` untouched
- `--codeact` flag, `codeact` + `codeact_remember` config keys, and D-03 precedence (flag → remembered → tool) agree; every `/codeact` switch persists the last choice via the atomic config save

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer: /codeact toggle through shaped code turn to interface label** - `2a33d69` (feat)
2. **Task 2: Startup surfaces: --codeact flag plus config keys plus remember-last** - `0a010ce` (feat)

**Plan metadata:** `docs: complete plan` (this SUMMARY — hash below)

## Files Created/Modified

- `strands_code_cli/codeact.py` (NEW) - `CodeactState` holder, `CODEACT_PREFIX`, reply/usage constants, `resolve_turn_interface` / `shape_turn_text` / `codeact_label` / `resolve_initial_interface` seams
- `tests/test_codeact.py` (NEW) - 56 tests: holder, dispatch, turn_setup, prefix, label, history, cost-rows, tracer, startup flag/config/precedence/persist
- `strands_code_cli/router.py` - `_codeact_holder` / `_codeact_message`, `/codeact` branch before skills-dynamic, `dispatch(interface=...)` kwarg, `USAGE_HINT` entry
- `strands_code_cli/skills.py` - `"codeact"` joins `BUILTIN_SLASH_HEADS` (shadow warning automatic)
- `strands_code_cli/loop.py` - loop-owned holder + `turn_interfaces` list, fix-at-send turn setup, per-turn label print (main + revise paths), `run_loop(codeact=...)` startup, persist-on-switch
- `strands_code_cli/main.py` - `--codeact` typer flag with `BadParameter` validation before the credential gate
- `strands_code_cli/provider_config.py` - `codeact` + `codeact_remember` keys with fail-loud validation, `save_codeact_choice`

## Decisions Made

- Turn-setup lives in testable `codeact.py` seams rather than loop-inline only: the plan's turn_setup/label/tracer tests are untestable without them, so `loop.py` calls `resolve_turn_interface` / `shape_turn_text` / `codeact_label` at the mode/routing hook site.
- Both-holder turns resolve to tool-shaped until per-ask routing lands in 11-02 (plan: prefix "only on code turns"); pinned by test.
- Remember-last gates the read path only: every `/codeact` switch persists unconditionally, so enabling remember later picks up a fresh value (plan: "persist the new value" with no gating condition).
- Run-loop config read stays fail-loud like the existing model line (no tamper guard): config-file errors are already fatal at startup, and `load`/`save` validation is the boundary. Chose the model-line precedent over the memory-mode warn-and-default because a guarded read here would still crash one line later at the unguarded model read.
- `codeact_remember: null`/absent loads as `False` (established None-means-absent pattern); only non-bool non-None values raise. Defaults are omitted on save (established omit-defaults pattern).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Toggle-to-turn pipeline proven end to end; 11-02 (stint executor, both-mode routing) and 11-03 (approval preview) build on `CodeactState`, the fix-at-send seams, and `turn_interfaces`.
- Known follow-up owned by 11-02: `turn_interfaces` appends cover main + revise paths per this plan; btw drain sites stay tool-calling and record no interface entry until 11-02 task 2 extends the list.
- Verify-time manual checks (see coverage D3/D4): one live turn showing the `interface:` label, one live `--codeact` start plus `/codeact` switch and restart.

---
*Phase: 11-codeact-action-interface*
*Completed: 2026-10-15*
