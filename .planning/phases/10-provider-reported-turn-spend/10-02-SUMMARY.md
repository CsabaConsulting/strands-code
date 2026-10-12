---
phase: 10-provider-reported-turn-spend
plan: "02"
subsystem: cost
tags: [reported-actuals, cost-display, blended-total, split-line, routing-marker, bedrock-parity]

# Dependency graph
requires:
  - phase: 10-provider-reported-turn-spend
    provides: 10-01 capture mixin + drain + marked usage line + actual-wins row loop
provides:
  - blended headline Total with conditional actual/estimated split line
  - actual marker on routing lines with reported spend in the actuals lane
  - Bedrock/offline byte-parity regression pins
affects: [10-03 remaining-wrap-sites, docs-cost]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 2418
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns: [lane-accumulation-with-presence-flags, marker-iff-reported]

key-files:
  created: []
  modified: [strands_code_cli/cost_context.py, tests/test_cost_context.py]

key-decisions:
  - "Lane-opens is presence-based (has_actual/has_estimated flags), not value-based: a present 0.0 actual opens the actuals lane, a derived zero from an absent cost never does"
  - "Split line sits immediately beneath the Total line, shaped '  (actual $X + estimated $Y)' per the planner lock"

patterns-established:
  - "Actual-wins totals accumulate exactly one lane per row plus reported routing spend, with the blended sum on the Total line"
  - "Present-zero stays an actual everywhere: is-not-None checks in rows, routing fold, and lane flags alike"

requirements-completed: [MODEL-05]

# Coverage metadata (#1602) — one entry per shipped deliverable. Drives DETERMINISTIC UAT routing in verify-work.
coverage:
  - id: D1
    description: "Mixed sessions show a blended headline total plus an actual/estimated split beneath it"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#TestBlendedTotalsAndSplit::test_mixed_total_shows_blended_and_split"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pure actuals or pure estimate sessions show the plain total with no split line"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#TestBlendedTotalsAndSplit::test_estimate_only_has_no_split + test_actuals_only_has_no_split"
        status: pass
    human_judgment: false
  - id: D3
    description: "Routing lines mark reported spend and fold it into the actuals lane; absent costs stay bare and never open the lane"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#TestBlendedTotalsAndSplit::test_routing_reported_spend_marked_and_laned + test_absent_routing_cost_never_opens_lane + TestRoutingEntries"
        status: pass
    human_judgment: false
  - id: D4
    description: "Bedrock and offline turns render byte-identical to the pre-phase output"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#TestBedrockOfflineParity"
        status: pass
    human_judgment: false

# Metrics
duration: 3min
completed: 2026-10-12
status: complete
---

# Phase 10 Plan 02: Display completion — split, routing marker, Bedrock parity Summary

**Blended /cost totals with a conditional actual/estimated split, the actual marker on routing lines with reported spend in the actuals lane, and byte-identical Bedrock/offline output pinned by goldens.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-10-12T23:16:12Z
- **Completed:** 2026-10-12T23:19:21Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `cost_report` tracks `total_actual`/`total_estimated` with presence flags across the row loop and the routing fold; the Total line keeps its exact shape with the blended sum
- Split line `  (actual $X + estimated $Y)` renders beneath the Total only when both lanes are non-empty (D-11 plus symmetric restraint)
- `_routing_line` appends the `actual` marker iff `_reported_spend` returns not None; reported routing spend folds into the actuals lane (D-04, D-10)
- Bedrock full-report golden, usage-line pin, and unpriced-offline golden prove byte-identical pre-phase rendering (D-07); full suite green (1396 passed, 10 deselected)

## Task Commits

Each task was committed atomically:

1. **Task 1: Blended total, split line, routing marker and actuals lane** - `50ddddc` (test, RED) + `3ce320d` (feat, GREEN)
2. **Task 2: Bedrock and offline byte-parity plus full-suite gate** - `0d37397` (test)

_Note: TDD task 1 has two commits (test → feat); no refactor commit was needed._

## Files Created/Modified

- `strands_code_cli/cost_context.py` - Lane accumulation, conditional split, routing-line marker
- `tests/test_cost_context.py` - `TestBlendedTotalsAndSplit` (7 tests), `TestBedrockOfflineParity` (4 tests), 4 routing assertions updated to the locked format

## Decisions Made

- Lane-opens is presence-based (`has_actual`/`has_estimated` flags), not value-based: a present `0.0` actual opens the actuals lane (pinned by `test_present_zero_actual_opens_lane`), while a derived zero from an absent cost never does (pinned by `test_absent_routing_cost_never_opens_lane`). This is the direct reading of the planner's lock that "a lane opens only on a present reported value or a computed estimate".
- Split line sits immediately beneath the Total line, shaped `  (actual $X + estimated $Y)` per the planner lock; Prices provenance block and display-only footer untouched.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## TDD Gate Compliance

Task 1 (`tdd="true"`) followed the RED→GREEN sequence with RED committed before any production edit:

- Task 1 RED (`50ddddc`): `uv run pytest tests/test_cost_context.py -q` → 3 failed / 54 passed. Failures are the missing feature itself (absent split line, unmarked `$0.0006` routing spend); the 4 passing new tests are regression pins of behavior GREEN must preserve (estimate-only no split, actuals-only no split, absent-cost bare zero, absent-never-opens-lane). Target `TestBlendedTotalsAndSplit::test_mixed_total_shows_blended_and_split` failed as required.
- GREEN (`3ce320d`) followed only after the failing run; suite went 57/57 green.
- Machine gate `gsd_run check tdd-red-evidence` was not invoked: 10-01 established it returns `INVALID_RED/zero_tests_discovered` for pytest output (TAP-only parser), and the RED evidence above is substantive and directly inspected.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The `/cost` display contract is complete: mixed sessions blend with a split, routing spend is marked and laned, pure sessions and Bedrock/offline output render exactly as before.
- Byte-parity was proven against the real pre-phase module (`git show 50ddddc:cost_context.py`): Bedrock report, usage line, and offline report all diff-clean.
- Ready for 10-03 (remaining wrap sites + btw carrier).

---
*Phase: 10-provider-reported-turn-spend*
*Completed: 2026-10-12*
