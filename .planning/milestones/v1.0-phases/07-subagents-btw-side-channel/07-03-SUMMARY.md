---
phase: 07-subagents-btw-side-channel
plan: 03
subsystem: cli-loop
tags: [btw, side-channel, fifo-queue, outliving-main, bounded-wait, idle-drain]

requires:
  - phase: 07-subagents-btw-side-channel
    provides: tracer pump, BtwContext, fenced render from 07-01; tagged gate, per-request cancel, chooser from 07-02
provides:
  - Unbounded FIFO BtwQueue with visible depth echoes; one side answer at a time, pump-spawned
  - Outliving-main lifecycle: side run survives the turn boundary, lands fenced at idle
  - D-11 bounded-wait idle service: idle approvals announced once, served by the next turn's pump
  - New-turn attach of a live side future; queued questions start across the idle gap
affects: [verify-work live parallel smoke, cost display, Phase 8 routing, Phase 9 CodeAct]

actuals:
  tokens: 12776
  tasks: 2
  commits: 2
plan_head_before: bd5097970ed6081c0452a751b788efcfbfe993db

tech-stack:
  added: []
  patterns: [queue-owned submit echo, session-scoped btw context, idle drain with announce-once latch]

key-files:
  created: []
  modified:
    - strands_code_cli/btw.py
    - strands_code_cli/loop.py
    - strands_code_cli/steering.py
    - strands_code_cli/policy_gate.py
    - tests/test_btw.py

key-decisions:
  - "D-11 ships as bounded-wait, not async-multiplex: the timeboxed spike proved sync prompt_toolkit dialogs cannot run inside the multiplex loop"
  - "BtwContext is session-scoped: the tracer join is gone and a live side future is adopted by the next turn, never rebuilt"
  - "btw.running is cleared only at the idle-side spawn site, never at reap, so a submit landing mid-respawn still reads running"
  - "ApprovalBroker.has_pending is a non-consuming peek so the idle drain can announce without stealing the next pump's request"

patterns-established:
  - "Queue owns its echo: BtwContext.submit enqueues plus prints the receipt/status lines and returns depth; the reader thread ignores the return"
  - "Announce-once latch: btw.approval_announced gates the idle notice and re-arms when the broker queue clears"

requirements-completed: [LOOP-03]

coverage:
  - id: D1
    description: "Queued /btw questions run visibly FIFO with one side agent live at a time"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestBtwQueue + TestBtwFifoDrain"
        status: pass
    human_judgment: false
  - id: D2
    description: "Plain text still steers main during backlog; /btw during an open prompt waits for close"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestSteeringDuringBacklog + TestGateOpenBtw"
        status: pass
    human_judgment: false
  - id: D3
    description: "Side run outlives its main turn and lands fenced at idle with history append plus metrics row"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestOutlivingMain"
        status: pass
    human_judgment: false
  - id: D4
    description: "New turn adopts a live side future without respawn; queued questions start across the idle gap"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestOutlivingMain#test_new_turn_adopts_live_side_without_respawn"
        status: pass
    human_judgment: false
  - id: D5
    description: "Idle side approval announced once, then served by the next turn's pump"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestOutlivingMain#test_idle_approval_announced_once_then_served_next_turn"
        status: pass
    human_judgment: false
  - id: D6
    description: "Live idle landing: fenced block plus notice plus tagged prompt render cleanly at a real terminal"
    requirement: "LOOP-03"
    verification: []
    human_judgment: true
    rationale: "Needs a live model, a real tty, and terminal rendering judgment — gates verify-work, not this plan"

duration: 36min
completed: 2026-10-06
status: complete
---

# Phase 07 Plan 03: Queue + Outliving-Main Lifecycle Summary

**Unbounded FIFO side-question queue with visible depth plus a tracer-join-free outliving-main lifecycle on the D-11 bounded-wait fallback (async-multiplex spiked and rejected)**

## Performance

- **Duration:** 36 min
- **Started:** 2026-10-06T07:51:00Z
- **Completed:** 2026-10-06T08:26:57Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `BtwQueue` holds side questions as an unbounded FIFO with visible depth: idle-side submits echo "Side question noted — answering in parallel.", running-side submits echo "Side question queued (#N in line) — answering in parallel.", and the pump spawns only when no side run is live
- Queued questions drain strictly in order with at most one side agent ever running, starting the next question immediately on each completion — including across the idle gap between main turns
- The unconditional tracer join is gone: a side run that outlives its main task stays attached to the session-scoped `BtwContext`, streams fenced, and lands at the idle prompt via `_drain_idle_btw` (fenced block + history Q&A append + `session_turns` metrics row)
- New main turns re-enter the dual pump with a still-running btw future adopted (no rebuild, no restart); the btw lifecycle no longer depends on main-turn boundaries
- D-11 ships as **bounded-wait**: a side approval requested while main-idle is announced once in the transcript ("btw approval needed — will prompt when the next turn starts."), waits under the session broker pump, and is served tagged `[btw]` by the next turn's pump
- The async-multiplex primary was spiked timeboxed and rejected: sync prompt_toolkit dialogs cannot run inside the multiplex loop, and no live TTY could validate the suspend/re-issue dance (spike scripts `/tmp/spike1_nesting.py`, `/tmp/spike2_plumbing.py`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Visible FIFO queue with one side answer at a time** - `91ebac9` (feat)
2. **Task 2: Outliving-main lifecycle with spike-then-build idle service** - `18fafa6` (feat)

## Files Created/Modified

- `strands_code_cli/btw.py` - `BtwQueue` (put/get_nowait/empty/qsize/depth, blank rejection); `BtwContext.submit` queue-owned echo returning depth; `btw.running` flag; `attach_live`/`take_done_live` live-handle slots; `BTW_IDLE_APPROVAL` notice text; `approval_announced` latch
- `strands_code_cli/loop.py` - pump spawns from the queue only when no side run is live; FIFO drain on completion; tracer-join removal; session-scoped `BtwContext`; `_drain_idle_btw` idle service (fenced land + append + metrics + announce-once); new-turn adoption of a live side future; queued-start across the idle gap
- `strands_code_cli/steering.py` - `on_btw` seam now routes through `btw.submit` so the receipt/status echo prints at the enqueue site
- `strands_code_cli/policy_gate.py` - `ApprovalBroker.has_pending` non-consuming peek for the idle-drain notice entry
- `tests/test_btw.py` - `TestBtwQueue`, `TestBtwFifoDrain`, `TestSteeringDuringBacklog`, `TestGateOpenBtw`, `TestLiveHandle`, `TestOutlivingMain`, integration-marked `TestLiveIdleScenario`

## Decisions Made

- **Bounded-wait ships; async-multiplex rejected.** The plan's timeboxed spike drove a sync prompt_toolkit prompt against a running asyncio loop (probe 1: nesting) and the FIRST_COMPLETED broker plumbing with stand-ins (probe 2). Probe 1 showed the serve path — `req.run_prompt()` is sync via `radio_choice` — cannot run inside the multiplex loop thread, and with no live TTY available the prompt suspend/re-issue dance could not be validated at all. Per resolved item 4, the fallback shipped: idle approvals wait for the next turn's pump with a one-time transcript announcement. D-11's letter holds for the non-approval path (fenced idle landing) and the approval path degrades to next-turn service, never a lost prompt.
- `BtwContext` went session-scoped: the same context (live future, queue, pending, latches) rides across turns, so new turns adopt rather than rebuild. The turn boundary is now a no-op for side work.
- `btw.running` clears only at the idle-side spawn site, never at reap: a submit landing in the respawn window still reads running and gets the queued echo with the right depth instead of a stale idle-side note.
- `has_pending` peeks without consuming: the idle drain detects a waiting side approval for the notice while leaving the request queued for the next turn's pump to serve.
- The announce-once latch (`approval_announced`) re-arms when the broker queue clears, so each new idle-approval episode announces exactly once.

## Deviations from Plan

None - plan executed exactly as written. Both anticipated branches (primary vs fallback) were specified in the plan; the fallback branch shipped per its own resolved item 4, and `policy_gate.py` (the `has_pending` peek) is the minimal seam the fallback's notice entry requires.

## Issues Encountered

- No live TTY in the execution environment meant the multiplex suspend/re-issue dance could never get past headless probes — this is what forced the spike's negative conclusion rather than a validated primary. The hermetic doubles prove the bounded-wait mechanism; only rendering judgment remains for verify-work (coverage D6).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- LOOP-03 is fully closed: tracer (07-01), gate parity (07-02), queue + outliving-main lifecycle (07-03) — all green, full suite 879 passed.
- Live parallel smoke (main + btw with approvals, Ctrl-C chooser, idle landing render) gates verify-work, not this plan (coverage D6 plus the carried D6s from 07-01/07-02).
- Phase 7 has no remaining plans; ready for phase close (verify-work) and Phase 8 (model routing).
- Carried edge from 07-01, still open by design: empty-main-retry (`del history[before:]`) can wipe an already-flushed btw Q&A from model history; transcript and metrics keep it.

---
*Phase: 07-subagents-btw-side-channel*
*Completed: 2026-10-06*

## Self-Check: PASSED
