---
phase: 07-subagents-btw-side-channel
plan: 04
subsystem: cli-loop
tags: [btw, approval-broker, cancel, gap-closure, uat-fix]

requires:
  - phase: 07-subagents-btw-side-channel
    provides: tracer pump, BtwContext, tagged gate, per-request cancel, queue, bounded-wait idle service from 07-01..07-03
provides:
  - Nesting-safe broker pump: turn-pump exits preserve the session pump, idle side approvals enqueue
  - Scoped side prompt: hardened ONLY framing plus context-only marking of the in-flight main turn
  - Clean cancel with an approval in flight: dead-tag skip, wrapped-cancel mapping, ack-before-join
  - Self-identifying approval dialogs: [main]/[btw] tag plus request descriptor in the title
affects: [verify-work UAT round 2, phase seal]

actuals:
  tokens: 10106
  tasks: 4
  commits: 4
plan_head_before: 637f29098ed1b7651cb83122fd831f9a017a226e

tech-stack:
  added: []
  patterns: [nesting-refcount session pump, pump-side dead-tag drain, sdk-wrap cancel mapping, tagged dialog titles]

key-files:
  created:
    - tests/test_loop_cancel.py
  modified:
    - strands_code_cli/policy_gate.py
    - strands_code_cli/loop.py
    - strands_code_cli/btw.py
    - tests/test_broker.py
    - tests/test_btw.py
    - tests/test_policy_gate.py

key-decisions:
  - "No choice.py change: radio_choice title already passes through to the Frame, so resolved item 7's 'only as needed' meant no edit"
  - "Fenced --- styling not applied to the dialog title: the prompt_toolkit Frame is already the box; --- lines would read wrong inside it"
  - "Pre-join ack reuses CANCEL_FIRST_PRESS styled yellow, matching the two-press machine (DEBUG F-3 'the two-press ack line')"
  - "request() passes the raw cancel arg (not the pump-cancel fallback) into the request, so cancel=None legacy requests always serve"
  - "Exclusion fallback C not applied: A+B only per resolved item 3; live UAT-round-2 retest gates obedience"

patterns-established:
  - "Pump-side dead-tag drain: _poll_live aborts set-cancel requests at every serve site, legacy None always serves"
  - "worker_cancelled unwrap: TurnCancelled or EventLoopException chains containing it map to the cancel path"

requirements-completed: [LOOP-03]

coverage:
  - id: D1
    description: "Turn-pump exits preserve the session pump; idle side approvals enqueue and announce after any number of turns"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_broker.py#TestPumpNesting"
        status: pass
      - kind: unit
        ref: "tests/test_btw.py#TestOutlivingMain#test_idle_approval_announced_once_then_served_next_turn"
        status: pass
    human_judgment: false
  - id: D2
    description: "Forked side prompt bounds scope: context-only marker on the in-flight main turn, ONLY framing hardened"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestForkScope"
        status: pass
    human_judgment: false
  - id: D3
    description: "Cancel with an approval in flight: dead requests skipped, wrapped cancels render cleanly, ack precedes the join"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_broker.py#TestDeadRequestSkip + TestWorkerCancelled"
        status: pass
      - kind: unit
        ref: "tests/test_btw.py#TestFinishBtwTurnCancel"
        status: pass
      - kind: unit
        ref: "tests/test_loop_cancel.py#TestAckBeforeJoin"
        status: pass
    human_judgment: false
  - id: D4
    description: "Approval dialog titles carry [main]/[btw] plus tool and detail; headers and typed fallback byte-identical"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_policy_gate.py#TestDialogAttribution"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live UAT-round-2 retest: sculpted scenarios prove the side agent obeys the scope boundary and cancels render cleanly at a real terminal"
    requirement: "LOOP-03"
    verification: []
    human_judgment: true
    rationale: "Model obedience to the scope boundary plus terminal cancel/dialog rendering need a live model and human judgment — gates UAT round 2, not this plan"

duration: 7min
completed: 2026-10-07
status: complete
---

# Phase 07 Plan 04: Gap Closure Summary

**Nesting-safe broker pump, scoped side prompt, clean cancel-with-approval-in-flight, and self-identifying approval dialogs — all four Phase 7 UAT gaps closed hermetically**

## Performance

- **Duration:** 7 min
- **Started:** 2026-10-07T06:36:51Z
- **Completed:** 2026-10-07T06:44:17Z
- **Tasks:** 4
- **Files modified:** 7

## Accomplishments

- G-7-1a closed: `ApprovalBroker` carries a nesting depth counter so a turn-pump exit restores the session pump's entered state instead of wiping it — idle side approvals enqueue for the next turn and the announce-once path is reachable after any number of turns
- G-7-1b closed hermetically (A+B): `BTW_FRAMING`/`BTW_FORK_PREAMBLE` bound scope with ONLY/read-only/do-not-perform language, and `fork_btw_history` labels the trailing unanswered user-text turn context-only in place (toolResult/assistant tails unmarked, roles alternate, parent unmutated)
- G-7-2 closed: requests carry the waiter's cancel event and the pump drain skips dead-tag requests at all three serve sites (no phantom dialogs); `worker_cancelled` unwraps SDK `EventLoopException` chains so cancels render as fenced "Cancelled by user" notes on the KeyboardInterrupt path; the cancel ack prints before the pool-exit join with step granularity documented
- G-7-4 closed: every `Approve?` dialog title reads `[main]`/`[btw]` plus tool and a one-line detail snippet, while header lines, the typed fallback, and ESC/Ctrl-C contracts stay byte-identical

## Task Commits

Each task was committed atomically:

1. **Task 1: [P0] G-7-1a — nesting-safe broker pump** - `909f6af` (fix)
2. **Task 2: [P0] G-7-1b — scoped side prompt** - `0762eec` (fix)
3. **Task 3: [P0] G-7-2 — clean cancel with approval in flight** - `67c6694` (fix)
4. **Task 4: [P1] G-7-4 — self-identifying approval dialogs** - `a78a585` (fix)

## Files Created/Modified

- `strands_code_cli/policy_gate.py` - `_depth` nesting counter; `_ApprovalRequest` cancel tag plus `abort()`; `request` cancel passthrough; `worker_cancelled` unwrap; `_dialog_title` attribution
- `strands_code_cli/loop.py` - `_poll_live` dead-tag drain at all 3 serve sites; wrapped-cancel mapping plus defensive accepts; F-2 cancel rendering; ack-before-join plus granularity doc
- `strands_code_cli/btw.py` - hardened framing constants; `BTW_INFLIGHT_MARKER` plus in-place fork marking; `render_btw_cancelled` fenced note
- `strands_code_cli/choice.py` - unchanged (title already passes through to the Frame; see Decisions)
- `tests/test_broker.py` - `TestPumpNesting`, `TestDeadRequestSkip`, `TestWorkerCancelled`
- `tests/test_btw.py` - `TestForkScope`, `TestFinishBtwTurnCancel`, idle-announce nesting extension
- `tests/test_loop_cancel.py` (NEW) - `TestAckBeforeJoin` ordering test
- `tests/test_policy_gate.py` - `TestDialogAttribution` (titles, truncation, byte-identical fallback, ESC/Ctrl-C)

## Decisions Made

- No `choice.py` change: `radio_choice` already takes a title and passes it to the prompt_toolkit `Frame`, so resolved item 7's "extend radio_choice only as needed" meant no edit — the attribution threads entirely through `policy_gate._dialog_title`.
- Fenced `---` styling not applied to the dialog title: the Frame border is already the box, and `---` lines would read wrong inside it; the tag-plus-descriptor title carries identity on its own.
- Pre-join ack reuses `CANCEL_FIRST_PRESS` via `print_plain` styled yellow, matching the two-press machine's own line (DEBUG F-3 "the two-press ack line").
- `request()` passes the raw cancel argument (not the pump-cancel fallback) into the request, so `cancel=None` legacy/test requests always serve per resolved item 4.
- Exclusion fallback C not applied: A+B only per resolved item 3 (exclusion would weaken D-13 shared-history context); the live UAT-round-2 retest decides whether C is ever needed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All four gap truths closed hermetically; full suite 907 passed, 6 deselected (pre-existing integration/live markers).
- Ready for UAT round 2 live retests, which gate the phase seal (not this plan): idle-announce after completed turns; essay-once plus no-btw-sleep-30-approval plus D-13 context-awareness; cancel racing an approval dialog; multi-dialog attribution rendering.
- If the live retest still shows main-task adoption after A+B, resolved item 3's exclusion fallback (C) applies as a follow-up.

---
*Phase: 07-subagents-btw-side-channel*
*Completed: 2026-10-07*

## Self-Check: PASSED
