---
phase: 07-subagents-btw-side-channel
plan: 01
subsystem: cli-loop
tags: [btw, side-channel, subagent, steering, concurrency, cost]

requires:
  - phase: 04-plan-act-modes-steering
    provides: steering reader + boundary redirect + two-press cancel the /btw carve-out extends
  - phase: 05-model-cost-context-commands
    provides: mid-turn slash refusal, record_turn_metrics/cost_report the btw path reuses
  - phase: 06-skills-memory-file
    provides: BUILTIN_SLASH_HEADS collision rule, print_plain markup-off transcript path
provides:
  - Mid-turn /btw spawns a parallel side agent; main turn never pauses
  - Fenced live side-block rendering under a shared render lock (errors fenced too)
  - Boundary-flush Q&A append-back plus tracer join (no orphans before 07-03 idle landing)
  - Idle /btw inline-turn dispatch with builtin-head protection
  - Btw spend melted into session /cost totals via the shared row shape
affects: [07-02 tagged approvals + queue lifecycle, 07-03 idle landing, cost display]

actuals:
  tokens: 12573
  tasks: 3
  commits: 3
plan_head_before: 0f9a066dec6affb38e8a9d4c23dfd54e69230286

tech-stack:
  added: []
  patterns: [dual-future single-pump turn, render-locked message blocks, factory-rebuild delegate spawn]

key-files:
  created:
    - strands_code_cli/btw.py
    - tests/test_btw.py
    - tests/test_router_btw.py
  modified:
    - strands_code_cli/loop.py
    - strands_code_cli/steering.py
    - strands_code_cli/main.py
    - strands_code_cli/router.py
    - strands_code_cli/skills.py
    - tests/test_cost_context.py
    - tests/test_model_switch.py

key-decisions:
  - "build_btw_agent returns (agent, prompt): the forked message list is the side invocation prompt, never pre-seeded history (avoids a double user turn)"
  - "History flush lives in _invoke_agent (test-observable); btw spend records in run_loop where current_model/session_turns live; pending consumed per attempt so empty-retries never re-record"
  - "Bare mid-turn /btw yields usage via the refusal callback instead of spawning an empty side agent (unspecified edge)"
  - "Boundary flush on success path only; failed main turns keep the live-rendered side answer in the transcript but skip append-back/metrics"

patterns-established:
  - "Side-channel construction replays stashed create_harness kwargs (agent._harness_kwargs) with the live resolved model — child built the way the parent was"
  - "Reader thread enqueues, main-thread pump builds: no agent construction or prompting off the main thread"

requirements-completed: [LOOP-03]

coverage:
  - id: D1
    description: "Mid-turn /btw spawns parallel side work; main unpaused; plain text still steers"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestParallelTurn + TestMidTurnCarveOut"
        status: pass
    human_judgment: false
  - id: D2
    description: "Side answer streams as a fenced block; side failure renders fenced error"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestFencedRender"
        status: pass
    human_judgment: false
  - id: D3
    description: "Same model/tools/gate, forked history, recall-only memory, Q&A appended at boundary"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_btw.py#TestBuildBtwAgent + TestForkBtwHistory"
        status: pass
    human_judgment: false
  - id: D4
    description: "Idle /btw runs a normal inline turn; other mid-turn slashes keep verbatim refusal"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_router_btw.py#TestBtwIdleDispatch + tests/test_btw.py#TestMidTurnCarveOut"
        status: pass
    human_judgment: false
  - id: D5
    description: "Side-channel spend melts into session /cost totals with no btw rows"
    requirement: "LOOP-03"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#test_btw_spend_melts_into_session_totals"
        status: pass
    human_judgment: false
  - id: D6
    description: "Live parallel smoke: main plus btw with one approval each, fenced and tagged"
    requirement: "LOOP-03"
    verification: []
    human_judgment: true
    rationale: "Needs a live model, interactive approvals, and terminal rendering judgment — gates verify-work, not this plan"

duration: 6min
completed: 2026-10-06
status: complete
---

# Phase 07 Plan 01: /btw Side Channel Tracer Summary

**Mid-turn /btw spawns a parallel same-model side agent with fenced live delivery and boundary append-back, plus idle inline dispatch and cost-total melt-in**

## Performance

- **Duration:** 6 min
- **Started:** 2026-10-06T07:18:32Z
- **Completed:** 2026-10-06T07:24:22Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Mid-turn `/btw <q>` carves out of steering and spawns a parallel side agent (same model/tools/gate, forked history, recall-only memory) while the main turn runs unpaused
- Side answers stream live inside `--- btw: ---` fenced blocks under a shared render lock; side failures render fenced errors and never fail the main turn
- Completed Q&A appends to main history at the turn boundary; the tracer join holds the boundary until side work finishes (no orphans before the 07-03 idle landing)
- Idle `/btw` routes as a normal inline turn with usage on empty input, and `btw` joins the builtin slash heads so no skill can shadow it
- Btw turn spend records through the shared `record_turn_metrics` row shape — melts into `/cost` totals with zero report changes

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer — mid-turn /btw parallel side answer** - `9190939` (feat)
2. **Task 2: Idle /btw dispatch plus builtin-head protection** - `0e27498` (feat)
3. **Task 3: Side-channel spend melts into /cost total** - `7882cd7` (feat)

## Files Created/Modified

- `strands_code_cli/btw.py` (NEW) - RENDER_LOCK, LockedHandler, FencedBtwHandler, render_btw_error, fork_btw_history, append_btw_turn, BtwContext, build_btw_agent
- `strands_code_cli/steering.py` - is_btw_line plus on_btw spawn seam on start_steering_reader
- `strands_code_cli/loop.py` - dual-future pump (_invoke_parallel, _finish_btw_turn, _btw_context_for), btw kwarg on _invoke_agent, run_loop wiring, boundary spend recording
- `strands_code_cli/main.py` - callback_handler wrapped in LockedHandler; factory kwargs stashed as agent._harness_kwargs for rebuilds
- `strands_code_cli/router.py` - /btw idle branch before skills-dynamic plus USAGE_HINT entry
- `strands_code_cli/skills.py` - btw in BUILTIN_SLASH_HEADS
- `tests/test_btw.py` (NEW) - TestForkBtwHistory, TestFencedRender, TestMidTurnCarveOut, TestParallelTurn, TestBuildBtwAgent (+ absorb/usage/failure/memory-shape extras)
- `tests/test_router_btw.py` (NEW) - TestBtwIdleDispatch
- `tests/test_cost_context.py` - btw spend-melts-in test
- `tests/test_model_switch.py` - _invoke_agent doubles accept the new btw kwarg (signature maintenance only; assertions untouched)

## Decisions Made

- `build_btw_agent` returns `(agent, prompt)`: the forked message list (framed question as trailing user turn) is passed as the side invocation prompt, matching the harness `_with_history` + `stream_async` shape — pre-seeding history plus calling with the question text would stack two user turns.
- History flush lives in `_invoke_agent` (directly test-observable via TestParallelTurn); btw spend records in `run_loop` where `current_model`/`session_turns` live; `pending` is consumed per attempt so the empty-retry path never re-records.
- Bare mid-turn `/btw` yields `Usage: /btw <side question>` via the refusal callback instead of spawning an empty side agent (plan-unspecified edge; mirrors the idle branch).
- Boundary flush runs on the success path only: a failed main turn keeps the live-rendered side answer in the transcript but skips append-back and metrics (avoids writing side Q&A into a suspect history).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Existing `TestTurnGuard` doubles stub `_invoke_agent` with a strict 3-arg signature, so the new `btw=` kwarg failed 4 tests with TypeError. Fixed by adding `**kwargs` to the four doubles (signature maintenance; all assertions byte-identical). Full suite green after.

## Known Edges (for 07-02/07-03, not blockers)

- Empty-main-retry (`del history[before:]`) can wipe an already-flushed btw Q&A from model history in the rare empty-response-plus-completed-btw turn; transcript and metrics keep it. Retry-aware flush ordering belongs to the lifecycle plan.
- Failed-main-turn side Q&A is transcript-visible only (no append-back/metrics) per the success-path-only decision above.
- Side-agent tool calls share the parent's `PendingStore` objects today; the thread-safety audit plus any lock lands in 07-02 per the plan's flagged assumption.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Tracer architecture proven hermetically: dual workers, one pump, fenced rendering, boundary flush, idle dispatch, cost merge — all green.
- Ready for 07-02 (tagged `[main]`/`[btw]` approvals, agent-aware gate state, PendingStore audit, D-08 cancel chooser) and 07-03 (D-11 idle landing replacing the tracer join, queue depthdowns).
- Live parallel smoke (main + btw with one approval each) gates verify-work, not this plan.

---
*Phase: 07-subagents-btw-side-channel*
*Completed: 2026-10-06*

## Self-Check: PASSED
