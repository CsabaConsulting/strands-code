---
phase: 07-subagents-btw-side-channel
plan: 02
subsystem: cli-loop
tags: [btw, approval-gate, cancel, concurrency, ctrl-c, batch-coverage]

requires:
  - phase: 07-subagents-btw-side-channel
    provides: tracer pump, BtwContext, RENDER_LOCK from 07-01
  - phase: 03-permissions-gate
    provides: deny-first gate plus batch signatures the namespaced coverage extends
provides:
  - Agent-tagged approval prompts from event.agent identity with race-free per-tag ask context
  - Per-agent namespaced batch coverage with denials never covering on either side
  - Per-request broker cancel domains plus lock-guarded shared PendingStore
  - Ctrl-C chooser cancelling exactly main, btw, or both with two-press safety per target
affects: [07-03 idle landing, cost display, verify-work live parallel smoke]

actuals:
  tokens: 19250
  tasks: 3
  commits: 3
plan_head_before: 200e32638f51bd73c8c1b711c94fbc8c810a5461

tech-stack:
  added: []
  patterns: [tag-keyed ask stash plus thread-local tag, lock-guarded cancel registry, chooser-inside-pump cancel routing]

key-files:
  created: []
  modified:
    - strands_code_cli/policy_gate.py
    - strands_code_cli/loop.py
    - strands_code_cli/diff_gate.py
    - strands_code_cli/btw.py
    - tests/test_policy_gate.py
    - tests/test_broker.py
    - tests/test_plan_cancel.py

key-decisions:
  - "Chooser runs inside the dual pump on the main thread: unwinding first would park executor shutdown on uncancelled workers, and no-choice resume needs the live pump frame"
  - "Ctrl-C inside the chooser escalates to both targets: an answerless interrupt must still name targets so shutdown never parks"
  - "Main-only pick drains the side answer through the served pump (tracer join) before unwinding for the cancel UX"
  - "Tagged cancel lines route through print_plain (markup off): Rich swallowed [btw] as a style tag (WR-06 class)"

patterns-established:
  - "Cancel targets recorded on the turn context (btw.cancel_targets) by the pump, consumed per-target by the loop's KeyboardInterrupt path against one arm snapshot"
  - "both_running flag mirrors side-worker lifetime for the turn SIGINT handler: set means the handler sets nothing and the chooser decides"

requirements-completed: [LOOP-03]

coverage:
  - id: D1
    description: "Approval prompts carry [main]/[btw] from event.agent identity; interleaved classify-then-ask pipelines never swap contexts"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_policy_gate.py#TestAgentTaggedGate"
        status: pass
    human_judgment: false
  - id: D2
    description: "Batch coverage namespaced per agent; denials re-prompt on both sides; trust_delegated btw auto-trust prints a transcript note"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_policy_gate.py#TestAgentTaggedGate"
        status: pass
    human_judgment: false
  - id: D3
    description: "Per-request broker cancel domains: setting one worker's event aborts only its waiter; single-arg requests keep pump-cancel behavior"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_broker.py#TestPerRequestCancel"
        status: pass
    human_judgment: false
  - id: D4
    description: "Shared PendingStore lock-guarded; ten-thread hammer loses no writes"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_broker.py#TestPendingStoreThreads"
        status: pass
    human_judgment: false
  - id: D5
    description: "Ctrl-C chooser maps main/btw/both/None/bogus; both_running handler sets nothing and chains; per-target two-press copy"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_plan_cancel.py#TestResolveCancelTargets + TestAskCancelTarget + TestBothRunningHandler + TestHandleTurnCancelTarget"
        status: pass
    human_judgment: false
  - id: D6
    description: "Live parallel Ctrl-C with both workers running: chooser offers main/btw/both and cancels exactly the named target"
    requirement: "LOOP-03"
    verification: []
    human_judgment: true
    rationale: "Needs a live two-worker turn with a real tty plus terminal interaction judgment — gates verify-work, not this plan"

duration: 14min
completed: 2026-10-06
status: complete
---

# Phase 07 Plan 02: Shared-Gate Parallel Correctness Summary

**Agent-tagged approvals with race-free context, per-agent batch coverage, per-request cancel domains, a locked shared diff store, and a Ctrl-C chooser cancelling exactly the named target**

## Performance

- **Duration:** 14 min (across two executor runs — provider-side stream timeout rescue)
- **Started:** 2026-10-06T07:34:35Z
- **Completed:** 2026-10-06T07:48:11Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Every approval prompt names its agent (`[main]`/`[btw]` from event.agent identity) with a tag-keyed ask stash plus thread-local tag, so concurrent classify-then-ask pipelines never swap contexts
- Batch coverage is namespaced per agent (`tag` keyword defaulting to `"main"`, 3-tuple signature untouched): a main approval never silences an identical btw call, denials still never cover, and `/policy last` entries carry the tag prefix
- `trust_delegated` covers btw as delegated with a visible transcript note naming the tool (`Auto-trusted delegated call (<tool>) — trust_delegated is on.`)
- Per-request broker cancel domains via a lock-guarded registry (`register_cancel`/`cancel_for`); each worker waits only on its own event, and `request` keeps its single-arg shape
- Shared `PendingStore` audited NOT proven safe and guarded with a `threading.Lock` across load-mutate-save; ten-thread hammer test loses no writes
- Ctrl-C with both running opens a `Cancel which?` chooser (main/btw/both) and cancels only the named target: btw-only resumes the main turn, main-only drains the side answer through the served pump, ESC/None cancels nothing and continues, and single-task Ctrl-C is byte-identical to before

## Task Commits

Each task was committed atomically:

1. **Task 1: Agent-tagged prompts with race-free ask context and namespaced batch coverage** - `9283a38` (feat)
2. **Task 2: Per-request cancel domains plus shared diff-store audit** - `423f16e` (feat)
3. **Task 3: Ctrl-C chooser cancelling exactly main, btw, or both** - `81f419a` (feat)

## Files Created/Modified

- `strands_code_cli/policy_gate.py` - `tag_for`; `_ASK_TAG` thread-local; `_last_by_tag` keyed stash; tagged ask first line; `BatchState.is_covered`/`mark` tag keyword plus `[tag]` description prefixes; trust_delegated auto-trust note; broker `register_cancel`/`unregister_cancel`/`cancel_for`; `request` cancel keyword
- `strands_code_cli/loop.py` - main cancel registration in `_invoke_agent`; `both_running` flag maintenance; `resolve_cancel_targets`; `ask_cancel_target`; `_make_turn_sigint_handler` both_running keyword; `_handle_turn_cancel` target keyword; chooser inside the dual pump with resume/drain paths; per-target KeyboardInterrupt path
- `strands_code_cli/diff_gate.py` - `PendingStore` threading.Lock guarding `_ensure_loaded` and mutations
- `strands_code_cli/btw.py` - btw cancel registration at spawn plus unregister at completion; `BtwContext.cancel_targets` chooser-answer record
- `tests/test_policy_gate.py` - `TestAgentTaggedGate`: tag identity, interleaved-context, namespaced-batch, btw deny re-prompt, trust-note tests
- `tests/test_broker.py` - `TestPerRequestCancel` plus `TestPendingStoreThreads` hammer test
- `tests/test_plan_cancel.py` - chooser mapping, ask contract, both_running handler, per-target two-press tests

## Decisions Made

- Chooser runs inside the dual pump (`_invoke_parallel` inner `except KeyboardInterrupt`) on the main thread rather than literally in `run_loop`'s except block: `ThreadPoolExecutor` shutdown with `wait=True` would park on still-uncancelled workers, and a no-choice answer can only resume the pump before unwinding. The choice is recorded on `btw.cancel_targets` and `run_loop` runs `_handle_turn_cancel` per named target.
- Ctrl-C inside the chooser escalates to `("main", "btw")`: an interrupt that carries no answer must still name targets so executor shutdown never parks. ESC/None still fails closed to cancel-nothing-and-continue.
- Main-only pick holds the served pump until the side answer lands (tracer join) before unwinding: the pump must keep serving approvals so shutdown never parks on a gated side worker. Btw-only pick resumes the pump with no unwind so the main turn continues undisturbed.
- Tagged cancel lines print via `print_plain` (markup off, style kwarg): the `[btw]` prefix was swallowed as a Rich style tag (WR-06 class), caught by the new test. Main-target copy renders byte-identically to before.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Chooser decision point moved inside the pump**
- **Found during:** Task 3 (Ctrl-C chooser)
- **Issue:** The plan places `ask_cancel_target` in `run_loop`'s `except KeyboardInterrupt`, but by then `_invoke_parallel` has unwound and executor shutdown (`wait=True`) blocks until both workers finish — with no events set (the gated handler sets nothing while both run), shutdown parks until natural completion, and a parked btw approval deadlocks outright since the pump has exited. No-choice resume is likewise impossible after unwinding.
- **Fix:** Chooser runs in the pump's inner `except KeyboardInterrupt` on the main thread with resume (`continue`), btw-only resume, main-only drain, and both-unwind paths; the answer is recorded on `btw.cancel_targets` for the loop's per-target UX.
- **Files modified:** strands_code_cli/loop.py, strands_code_cli/btw.py (record field)
- **Verification:** 28/28 tests/test_plan_cancel.py pass; full suite 864 green
- **Committed in:** 81f419a (Task 3 commit)

**2. [Rule 3 - Blocking] One-field btw.py addition outside the task file list**
- **Found during:** Task 3 (Ctrl-C chooser)
- **Issue:** The task `<files>` lists only loop.py plus tests, but the pump-to-loop answer channel needs a home; the loop-owned `BtwContext` is the only object both sides share.
- **Fix:** Added `cancel_targets: tuple = ()` to `BtwContext` (record-only; no behavior change to btw spawn/reap paths).
- **Files modified:** strands_code_cli/btw.py
- **Verification:** Full suite green; no existing btw test touched
- **Committed in:** 81f419a (Task 3 commit)

**3. [Rule 2 - Missing Critical] Tagged cancel line through print_plain**
- **Found during:** Task 3 (Ctrl-C chooser)
- **Issue:** `[btw]`-prefixed copy printed via `console.print(f"[yellow]{line}[/yellow]")` lost the tag — Rich parsed `[btw]` as a style tag (WR-06 class the project closed in Phase 6 UAT).
- **Fix:** Single print site now uses `print_plain(console, line, style="yellow")` per AGENTS.md; main-target output renders identically.
- **Files modified:** strands_code_cli/loop.py
- **Verification:** New `TestHandleTurnCancelTarget` asserts the literal `[btw]` in output
- **Committed in:** 81f419a (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 missing critical)
**Impact on plan:** All three required for correctness or project-convention compliance; no scope creep. Tasks 1–2 executed exactly as written (no deviations).

## Issues Encountered

- A prior executor for this plan died from a provider-side stream idle timeout after committing tasks 1–2 cleanly (`9283a38`, `423f16e`, both verified green). This completion run executed only the remaining task 3 plus verification and SUMMARY — no rework of the committed tasks.
- `radio_choice` raises `KeyboardInterrupt` on Ctrl-C and `RuntimeError` off-tty: `ask_cancel_target` maps only the latter to None (fail closed); the former propagates to the pump's both-escalation. Pinned by tests.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- LOOP-03 gate parity holds: prompts tagged, coverage namespaced, cancels independent, chooser exact. Ready for 07-03 (D-11 idle landing replacing the tracer join, queue lifecycle).
- Live parallel smoke (main + btw with one approval each, then Ctrl-C chooser) gates verify-work, not this plan (coverage D6).
- Known edge carried from 07-01 (unchanged by this plan): empty-main-retry can wipe an already-flushed btw Q&A from model history; retry-aware flush ordering belongs to the lifecycle plan.

---
*Phase: 07-subagents-btw-side-channel*
*Completed: 2026-10-06*

## Self-Check: PASSED
