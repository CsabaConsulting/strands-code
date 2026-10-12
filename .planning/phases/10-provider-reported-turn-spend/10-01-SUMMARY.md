---
phase: 10-provider-reported-turn-spend
plan: "01"
subsystem: cost
tags: [openrouter, usage-cost, litellm, reported-actuals, cost-display]

# Dependency graph
requires:
  - phase: 08-model-routing-with-decision-models
    provides: reported decision-cost verbatim precedent, routing /cost plumbing
  - phase: 09-native-typesafe-decision-engine
    provides: computed-rate marker precedent for marked spend
provides:
  - reported_cost.py capture mixin, wrap gate, drain helpers
  - Reported-cost drain in record_turn_metrics with reported_cost row key
  - Marked actuals on usage lines and /cost rows with actual-wins precedence
affects: [10-02 totals-split, 10-03 remaining-wrap-sites, docs-cost]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 5481
  tasks: 2
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns: [sdk-subclass-capture-mixin, in-place-class-promotion, per-turn-side-channel-drain]

key-files:
  created: [strands_code_cli/reported_cost.py, tests/test_reported_cost.py]
  modified: [strands_code_cli/cost_context.py, strands_code_cli/loop.py, strands_code_cli/model_switch.py, tests/test_cost_context.py]

key-decisions:
  - "reported_cost row key stored only when present (existing exact-dict row assertion stays green; row.get keeps None semantics)"
  - "Wrap initializes _reported_costs only when absent so a re-wrap cannot wipe captured costs"
  - "Marker text is the literal word actual (per planner ruling); one marker everywhere"

patterns-established:
  - "Capture-before-delegate format_chunk mixin: record on metadata chunks, return super() output unmodified"
  - "Actual-wins branches check is not None, never truthiness (present 0.0 stays an actual)"

requirements-completed: [MODEL-05]

# Coverage metadata (#1602) — one entry per shipped deliverable. Drives DETERMINISTIC UAT routing in verify-work.
coverage:
  - id: D1
    description: "Inline usage.cost capture per model cycle with verbatim chunk delegation"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestCapture + TestDelegateChunks"
        status: pass
    human_judgment: false
  - id: D2
    description: "Per-turn drain with any-rule sum (present 0.0 stays actual, all-absent drains to None)"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestDrain"
        status: pass
    human_judgment: false
  - id: D3
    description: "Wrap gate: openrouter ids promote in place, other ids pass through identical"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestWrapGate + TestPromotion"
        status: pass
    human_judgment: false
  - id: D4
    description: "Marked actual on the post-turn usage line with actual-wins precedence"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestUsageLineActual + TestTracerEndToEnd"
        status: pass
    human_judgment: false
  - id: D5
    description: "/cost rows render marked actuals, bare-$ estimates, or tokens-only with one money lane per row"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#TestReportedRows"
        status: pass
    human_judgment: false

# Metrics
duration: 7min
completed: 2026-10-12
status: complete
---

# Phase 10 Plan 01: Tracer — reported actual end to end on the switch path Summary

**Inline OpenRouter usage.cost captured at the SDK seam, drained per turn, and rendered as marked actuals on usage lines and /cost rows with actual-wins precedence.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-10-12T23:06:17Z
- **Completed:** 2026-10-12T23:13:17Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- New `reported_cost.py`: capture mixin, openrouter wrap gate, per-turn drain helpers
- `apply_switch` wraps openrouter-routed ids in place; every other id passes through identical
- `record_turn_metrics` drains the serving model per turn and stores the `reported_cost` row key
- Usage lines and `/cost` rows mark actuals (`$X actual`); bare `$` stays estimate-only; one money lane per row

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer capture through drain to a marked usage line** - `092a263` (test, RED) + `65bb79b` (feat, GREEN)
2. **Task 2: Cost rows actual-wins with marked actuals** - `f271494` (test, RED) + `66bb335` (feat, GREEN)

_Note: TDD tasks have two commits each (test → feat); no refactor commits were needed._

## Files Created/Modified

- `strands_code_cli/reported_cost.py` - Capture mixin, wrap factory, drain helpers (NEW)
- `tests/test_reported_cost.py` - Hermetic capture/drain/gate/tracer tests (NEW, 17 tests)
- `strands_code_cli/model_switch.py` - `apply_switch` wraps openrouter-routed ids
- `strands_code_cli/loop.py` - Per-turn drain, `reported_cost` row key, main-turn `model=agent` sites
- `strands_code_cli/cost_context.py` - `usage_line` actual kwarg, actual-wins row loop
- `tests/test_cost_context.py` - `_session_row` builder + `TestReportedRows` (5 tests)

## Decisions Made

- `reported_cost` row key stored only when present: keeps the existing exact-dict row assertion green without weakening it; `row.get("reported_cost")` preserves None semantics for the fallback path.
- Wrap initializes `_reported_costs` only when absent: a re-wrap of an already-promoted instance cannot wipe captured costs (fresh resolves always initialize).
- Marker text is the literal word `actual` (planner ruling; matches the D-08 split vocabulary); one marker on usage lines and rows alike.
- RED machine-gate verdicts (`INVALID_RED/zero_tests_discovered`) recorded as a TAP-only parser limitation — see TDD Gate Compliance. No TAP output was fabricated; the real pytest RED runs are the evidence.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## TDD Gate Compliance

Both `tdd="true"` tasks followed the RED→GREEN sequence with RED committed before any production edit:

- Task 1 RED (`092a263`): `uv run pytest tests/test_reported_cost.py -q` → exit 1, 16 failed / 1 passed. Failures are the missing feature itself (`ModuleNotFoundError: reported_cost`, `TypeError: usage_line() got an unexpected keyword argument 'reported_cost'`); the passer is the byte-identical no-regression pin. Target tracer test `TestTracerEndToEnd::test_fake_cost_flows_to_row_and_usage_line` failed as required.
- Task 2 RED (`f271494`): `TestReportedRows` → 3 failed / 2 passed with genuine assertion failures (bare `$0.0000` where `$0.0024 actual` was expected; `$0.0010` total where `$0.0034` was expected). Target `TestReportedRows::test_actual_row_renders_marked` failed as required.
- Machine gate: `gsd_run check tdd-red-evidence` returned `INVALID_RED/zero_tests_discovered` for both honest records because its parser only recognizes Node TAP (`# tests N`) output, which pytest never emits. The RED phases are substantive and verified by direct inspection of the pytest output above; the verdict reflects the checker's stack coverage, not the RED quality. GREEN commits followed only after the failing runs.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Tracer slice proven: 10-02 (totals split + routing-line marker) and 10-03 (remaining wrap sites + btw carrier) can build on the capture/drain/render mechanism.
- Mixed-presence multi-cycle turns follow the locked any-rule, pinned by `test_multi_cycle_sums_present_only`; no surprises on the flagged A1 edge.
- Ready for 10-02.

---
*Phase: 10-provider-reported-turn-spend*
*Completed: 2026-10-12*
