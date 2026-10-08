---
phase: 07-subagents-btw-side-channel
plan: 05
subsystem: cli-loop
tags: [btw, idle-multiplex, prompt_async, stdin-guard, typeahead, gap-closure, uat-fix]

requires:
  - phase: 07-subagents-btw-side-channel
    provides: tracer pump, BtwContext, tagged gate, per-request cancel, queue, bounded-wait idle service from 07-01..07-03; nesting-safe pump, scoped fork, clean cancel, dialog attribution from 07-04
provides:
  - Multiplexed idle prompt (E): prompt_async FIRST_COMPLETED vs broker poll, suspend-serve-sync-re-issue with preserved buffer
  - Exit-path fenced drop note naming the live side question plus waiting/running state, next-turn promise suppressed
  - Reentrant StdinGuard shared by ask/chooser/radio_choice choke point plus typeahead hygiene on dialog entry
affects: [verify-work UAT round 3, phase seal, Phase 8 routing]

actuals:
  tokens: 13581
  tasks: 4
  commits: 5
plan_head_before: 8a2b7bf57a18b1184f6ade866494a907ef394eff

tech-stack:
  added: []
  patterns: [fresh-loop-per-episode idle race, error-channel prompt arm, refcounted Event guard, dialog-entry typeahead clear]

key-files:
  created:
    - tests/test_idle_multiplex.py
  modified:
    - strands_code_cli/loop.py
    - strands_code_cli/btw.py
    - strands_code_cli/steering.py
    - strands_code_cli/policy_gate.py
    - strands_code_cli/choice.py
    - tests/test_btw.py
    - tests/test_steering.py
    - tests/test_plan_cancel.py
    - tests/test_choice.py

key-decisions:
  - "E ships per live-pty GO verdict (buffer/termios/Ctrl-C proven); A+C1/D/C2 stay out — exactly one branch"
  - "Dialog Ctrl-C at idle cancels the side run (turn-semantic analogue) and re-issues with the buffer; prompt Ctrl-C/EOF propagate"
  - "Prompt arm channels errors as values so a task-level KeyboardInterrupt can't strand the poll task"
  - "prompt()-only session doubles keep the legacy blocking prompt (duck-type fallback)"
  - "StdinGuard subclasses Event (set/clear/held) so the reader, ask(), and all call sites compose without rewrites"
  - "Exit-note renderer lives in btw.py next to its fence siblings; typeahead clear uses public prompt_toolkit API"

patterns-established:
  - "Fresh loop per idle episode: the sync serve always runs with no loop on the thread, so .run() can never nest"
  - "Guard hold for every mid-turn dialog lifetime; gated bytes buffer for after, never dropped, reader never restarted"

requirements-completed: [LOOP-03]

coverage:
  - id: D1
    description: "Idle side approvals served at idle via multiplex E (suspend-serve-re-issue, buffer preserved)"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_idle_multiplex.py#TestIdleMultiplexBranch"
        status: pass
      - kind: integration
        ref: "tests/test_idle_multiplex.py#TestLiveIdleMultiplex (live pty)"
        status: pass
    human_judgment: true
    rationale: "Live side-agent streaming interplay plus real-model timing need the UAT-round-3 live retest"
  - id: D2
    description: "Exit with a live side run leaves a fenced note naming the question plus waiting/running state, never a next-turn promise"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestExitDropNote"
        status: pass
    human_judgment: false
  - id: D3
    description: "Mid-turn dialogs take input cleanly under streaming (single-reader guard, no phantom confirms)"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_steering.py#TestStdinGuard + TestGuardOverlap"
        status: pass
      - kind: unit
        ref: "tests/test_plan_cancel.py#TestAskCancelTarget#test_chooser_holds_guard_during_dialog"
        status: pass
      - kind: unit
        ref: "tests/test_choice.py#TestDialogGuard"
        status: pass
    human_judgment: true
    rationale: "Lag/phantom absence under live streaming needs the UAT-round-3 live retest (plan-flagged assumption)"
  - id: D4
    description: "Full suite green with exactly one idle-serve branch shipped (no A+C1/D/C2 residue)"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "uv run pytest -q → 935 passed, 6 deselected"
        status: pass
    human_judgment: false

duration: 24min
completed: 2026-10-08
status: complete
---

# Phase 07 Plan 05: Round-2 Gap Closure Summary

**Multiplexed idle prompt serving side approvals at idle (E, live-pty GO verdict), fenced exit-drop notes, and a reentrant stdin guard with typeahead hygiene — both UAT round-2 gaps closed**

generic-agent workaround: produced without typed GSD dispatch (no agent_type in spawn schema); full typed-agent guarantees were not in effect.

## Performance

- **Duration:** 24 min
- **Started:** 2026-10-08T04:07:17Z
- **Completed:** 2026-10-08T04:31:16Z
- **Tasks:** 4
- **Files modified:** 10

## Accomplishments

- Task 1 spike verdict **GO** on a real pty (stdlib `pty.openpty`, not headless): buffer preserved across re-issue, termios iflag/oflag/lflag identical before/after, Ctrl-C in dialog cancels the dialog with the line alive, Ctrl-C at prompt cancels the line — so **E ships, A+C1/D/C2 stay out**
- `_idle_prompt_multiplexed` in loop.py races `prompt_async` against the broker poll per episode on a fresh loop; approval arrival suspends, serves one request sync after quiesce, re-issues with the preserved buffer; announce latch bypassed because service is immediate
- Exit path reaps done sides quietly and names live ones via fenced `render_btw_dropped` ("was waiting on approval" / "was still running"); the exit drain takes `from_exit` so it never promises a next turn
- `StdinGuard` (refcounted `threading.Event` subclass in steering.py) is the single shared guard held by `ask()`, the cancel chooser, and the `radio_choice` choke point; the reader polls `held()`; dialog entry clears prompt_toolkit typeahead (public API, kernel bytes untouched)
- Full suite green: 935 passed, 6 deselected (pre-existing markers), no live model or network in the new tests

## Task Commits

Each task was committed atomically:

1. **Task 1: [P0] G-7-1-R2 spike** - `ee00176` (test)
2. **Task 2: [P0] G-7-1-R2 build (E)** - `736411e` (feat)
3. **Task 3: [P0] G-7-1-R2 exit note** - `9169fb4` (fix)
4. **Task 4: [P1] G-7-1-R2b stdin guard** - `545b7ed` (fix)
5. **Plan verification fixup: prompt-only fallback** - `c27c762` (fix)

## Files Created/Modified

- `strands_code_cli/loop.py` - `_idle_prompt_multiplexed` + episode/race/poll helpers, idle wiring, `_drain_idle_btw(from_exit)`, `_note_dropped_side`, exit-path calls, chooser guard hold
- `strands_code_cli/btw.py` - `render_btw_dropped` fenced exit note (no notice-text change: E shipped)
- `strands_code_cli/steering.py` - `StdinGuard` + `stdin_guard` singleton; reader polls `held()` (param renamed `gate_open` → `guard`)
- `strands_code_cli/policy_gate.py` - `gate_open` is now the shared-guard alias (definition lives in steering; `ask()` body unchanged)
- `strands_code_cli/choice.py` - `radio_choice` choke point: guard hold for the whole call + `clear_typeahead` on entry
- `tests/test_idle_multiplex.py` (NEW) - GO-verdict header, headless FIRST_COMPLETED plumbing, pty-marked GO-1/GO-2/GO-3 tests, hermetic E-branch tests
- `tests/test_btw.py` - `TestExitDropNote` (parked, running, done-unreaped)
- `tests/test_steering.py` - `TestStdinGuard`, `TestGuardOverlap`; existing gates converted to `StdinGuard`
- `tests/test_plan_cancel.py` - chooser-gating test (fake asserting held during the call)
- `tests/test_choice.py` - `TestDialogGuard` (choke-point hold + entry typeahead clear)

## Decisions Made

- E ships exactly as spiked (fresh loop per episode, `run_until_complete` quiesce, sync serve, re-issue with `default=buffer`); the production round-trip was additionally probed under pty with a real broker + worker (`/tmp/spike_e_prod.py`, uncommitted): worker-got=n, buffer kept, termios sane
- Dialog Ctrl-C at idle cancels the side run (`req.abort()` + `btw.cancel_event.set()`) and re-issues with the buffer — the turn-semantic analogue, and the waiter can never wedge
- Exit-note renderer placed in `btw.py` next to its fence siblings (`render_btw_cancelled`/`render_btw_error` shape)
- Guard subclasses `threading.Event` so `ask()`'s set/finally/clear and every existing call site compose unchanged; `hold()` context manager for new sites
- Live pty falsification of R2b (keystroke reflection + zero reader consumption) stays a UAT-round-3 note, not a task gate, per the plan

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Prompt arm channels Ctrl-C/EOF as values instead of raising in-task**
- **Found during:** Task 2 (warning hunt: `Task was destroyed but it is pending`)
- **Issue:** `KeyboardInterrupt` raised inside `prompt_task` tears down `run_until_complete` itself, stranding the poll task pending with an un-awaited-coroutine warning
- **Fix:** `_prompt_arm` wrapper returns `("error", exc)`; the main coroutine re-raises after the quiesce, so no task is ever left over
- **Files modified:** strands_code_cli/loop.py
- **Verification:** tracemalloc-clean branch suite; production pty probe asserts no "Task was destroyed"
- **Committed in:** 736411e (Task 2 commit)

**2. [Rule 1 - Bug] Multiplex falls back for `prompt()`-only session doubles**
- **Found during:** Plan-level verification (19 order-dependent full-suite failures)
- **Issue:** A pre-existing `_ACTIVE["broker"]` leak (`test_mode.py::TestWiring` via `build_agent`, never cleaned) makes the broker non-None in later `run_loop` tests, routing `prompt()`-only doubles into the multiplex path where `prompt_async` doesn't exist
- **Fix:** `hasattr(session, "prompt_async")` gate keeps the legacy blocking prompt for doubles; production `PromptSession` always multiplexes. The leak itself is pre-existing/out-of-scope, logged to deferred-items.md
- **Files modified:** strands_code_cli/loop.py, tests/test_idle_multiplex.py
- **Verification:** full suite 935 passed, 6 deselected
- **Committed in:** c27c762 (plan-verification fixup commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes keep the shipped E shape intact (spike-faithful) while preserving the existing test-double contract. No scope creep; all exclusions honored (no nested apps, no reader stop/restart, no streaming mute, no CPR workarounds, no tcflush, guard never defined in policy_gate).

## Issues Encountered

- The 21 `patch_stdout` flush-thread warnings in combined runs are pre-existing (identical count at base commit via stash comparison) — out of scope, untouched.
- No live TTY sandbox lack: the pty-backed spike/probes run a real terminal (kernel line discipline, termios, isatty), satisfying the plan's "pty/pexpect or equivalent" bar.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Both round-2 gap truths closed hermetically plus live-pty proof; phase is ready for UAT round 3 (live retests: idle multiplex under real streaming, dialog lag/phantoms under load) and seal.
- Residual, by design: multiplex-vs-idle-streaming interplay and R2b live feel gate UAT round 3, not this plan (flagged assumptions).

---
*Phase: 07-subagents-btw-side-channel*
*Completed: 2026-10-08*

## Self-Check: PASSED
