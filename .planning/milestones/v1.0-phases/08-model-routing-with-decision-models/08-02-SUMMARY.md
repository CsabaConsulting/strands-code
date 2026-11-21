---
phase: 08-model-routing-with-decision-models
plan: "02"
subsystem: routing
tags: [decision-api, two-call-routing, effort-choice, fast-path, side-channel, pytest]

requires:
  - phase: 08-01
    provides: Typed Decision-API transports, answer validation, threshold/tie gate, 4-tuple decide() verdict, hook wiring
provides:
  - Sequential pick_effort call over picked-model levels with merged usage and effort_confidence
  - Rewritten single-candidate fast path (model call skipped, effort call kept)
  - Side-ask parity on the two-call verdict with both-confidences lines and events
affects: [08-03, 08-05, model-routing, cost-display]

actuals:
  tokens: 15700
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns: [sequential-two-call-decision, degenerate-single-level-skip]

key-files:
  created: []
  modified:
    - strands_code_cli/routing.py
    - tests/test_routing.py
    - tests/test_loop_routing.py

key-decisions:
  - "Single-level picks skip call 2 (degenerate choice; a 1-option question violates the 2-26 floor)"
  - "Same-model picks run call 2 but skip validate_routed_effort (locked 08-01 decision preserved)"
  - "Call-2 failure or unparseable table holds; outside-levels reads hold via validate_routed_effort"
  - "Success names the model-decision engine; cost merges with None as $0 unless both sides omit"

patterns-established:
  - "Two-call route: call 1 gate passes -> call 2 over picked levels only -> top choice ungated -> switch-path validation"
  - "Effort criteria are fixed code-side prose per harness Effort level with bare-name fallback (T-08-26)"

requirements-completed:
  - MODEL-03

coverage:
  - id: D1
    description: "Sequential effort-choice call over picked-model levels with merged usage"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestRoutedEffort+TestDecisionBuilders"
        status: pass
    human_judgment: false
  - id: D2
    description: "Single-candidate fast path asks the effort question only"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestSingleCandidateFastPath"
        status: pass
    human_judgment: false
  - id: D3
    description: "Side asks route through the shared strategy flagged as side with parity lines and events"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop_routing.py#TestSideRouting"
        status: pass
    human_judgment: false
  - id: D4
    description: "Routed transcript lines carry model plus effort confidences and the ~$/ask delta"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestRoutedEffort weak-read line + tests/test_loop_routing.py#TestSideRouting line shape"
        status: pass
    human_judgment: false

duration: 11min
completed: 2026-10-12
status: complete
---

# Phase 08 Plan 02: Two-Call Routing Summary

**Sequential model-then-effort decision calls with merged usage, an effort-only single-candidate fast path, and side-ask parity on the shared two-call verdict.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-10-12T05:25:45Z
- **Completed:** 2026-10-12T05:36:46Z
- **Tasks:** 3
- **Files modified:** 3
- **Execution mode:** SEQUENTIAL via generic-agent workaround (typed GSD dispatch unavailable in this session)

## Accomplishments

- Added the second sequential decision call: `build_effort_question` scopes criteria to exactly the picked candidate's advertised levels from a fixed code-side prose map, `_decide_effort` reruns the same state and engine chain after the call-1 gate passes, the top choice routes ungated with its probability as `effort_confidence`, and usage merges both calls into one reported triple.
- Rewrote the single-candidate branch to skip call 1 while still asking call 2 through the normal chain, recording call-2-only usage with `model_confidence` None and no tie marker; no-levels lone candidates keep the no-call hold.
- Verified side-ask parity end to end: `_route_side_spawn` was already on the 4-tuple verdict, so both decision calls run side-flagged through the shared strategy with kwargs application, side-headed both-confidences lines, reported-cost events, and silent holds.
- Extended the suites to 152 routing tests green (full repo suite 1149 green): sequential-ordering, levels-scoping, weak-read-routes, and gate-reject cases, plus side line-shape, silent-hold, and fast-path-parity cases.

## Task Commits

Each task was committed atomically:

1. **Task 1: Second sequential effort-choice call over picked-model levels** - `8a781b7` (feat)
2. **Task 2: Single-candidate fast path skips model call but asks effort** - `43bbb62` (feat)
3. **Task 3: Side-ask routing parity through the same strategy** - `a26914f` (test)

## Files Created/Modified

- `strands_code_cli/routing.py` - Effort criteria map, `build_effort_question`, shared shape validator, `_decide_effort` plus cost merge, call-2 wiring in `decide()`, rewritten single-candidate branch
- `tests/test_routing.py` - Effort builder tests, extended `TestRoutedEffort`, rewritten `TestSingleCandidateFastPath`, question-aware stubs across chain/local/live tests
- `tests/test_loop_routing.py` - Dual-answer `_table_result`, merged-usage events, extended `TestSideRouting`

## Decisions Made

- Single-level picks skip call 2: a one-option choice has nothing to judge and violates the documented 2-26 floor (Ollama rejects it), so the lone level rides through with `effort_confidence` None. The fully degenerate lone-single-level route is the explicit documented exception to "no zero-call verdicts" (pinned by `test_lone_single_level_routes_with_no_call`); every route with a real choice carries a real read.
- Same-model picks run call 2 but skip `validate_routed_effort`, preserving the locked 08-01 no-op decision (the hook applies no switch and no effort, so there is nothing to judge); D-15 keeps the effort question on single-candidate same-model strategies too.
- Call-2 engine failure or an unparseable effort table holds (never guesses); an outside-levels top choice holds via `validate_routed_effort` with its unsupported-effort detail, per the plan acceptance.
- On success the verdict names the model-decision engine (call 2 is subordinate); on hold it names the last attempted engine. Reported cost merges with a cost-absent side counting as $0, staying None only when both calls omit cost.
- `format_routed_line` needed no rebuild: 08-01 already shaped both confidences inline, verified by the new line assertions. Likewise `loop.py` needed no change for task 3: `_route_side_spawn` was already on the 4-tuple verdict with side-flagged state, lines, and events, so task 3 is verification plus parity tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Loop test helper moved to the dual-answer contract in the task-1 commit**
- **Found during:** Task 1 (call-2 wiring in `decide()`)
- **Issue:** `tests/test_loop_routing.py` mocks `decide_via_openrouter` with pick_model-only answers, so every routed hook/side test held once call 2 ran (a file outside task 1's list).
- **Fix:** Extended `_table_result` with a `pick_effort` answer, updated two engine-call counts (1→2) and two merged-usage event expectations; main-turn assertions otherwise untouched.
- **Files modified:** tests/test_loop_routing.py
- **Verification:** Both routing files green (147 passed) plus full suite green (1144 passed)
- **Committed in:** 8a781b7 (part of task commit)

**2. [Rule 3 - Blocking] Unreasoned-effort side test reworked for the effort-only fast path in the task-2 commit**
- **Found during:** Task 2 (fast-path rewrite)
- **Issue:** `test_unreasoned_effort_holds_to_parent_silently` asserted a zero-call hold (`engine == "none"` via `_boom`), which the effort-only fast path legitimately breaks.
- **Fix:** Reworked it to serve a real effort answer the switch-path check rejects, preserving the test's intent (silent hold with side-flagged event, now `engine == "openrouter"`).
- **Files modified:** tests/test_loop_routing.py
- **Verification:** Both routing files green (149 passed) plus full suite green (1146 passed)
- **Committed in:** 43bbb62 (part of task commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both keep the suite green across the two-call reshape; no scope creep. The single-level degenerate skip is a documented design decision on an unspecified edge, not a deviation from specified behavior.

## Issues Encountered

None - plan executed with the two blocking test-contract updates above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 08-03 (builds on the two-call verdict, fast path, and side parity): `decide()` returns decided effort with both confidences on every non-degenerate route, and the `pick_effort` question shape is stable for setup/docs work.
- Calibration debt carries forward unchanged: provisional `0.70`/`0.05` defaults still await 08-05 probe distributions; probe runs should include single-level candidates to confirm the degenerate skip reads correctly in distribution stats.
- Live verification already done in 08-01 (Jev via OpenRouter, tev1:0.8b via local Ollama); no new live surface in this plan beyond the second call shape, which the stub-server test covers.

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-12*
