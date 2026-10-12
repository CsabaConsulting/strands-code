---
phase: 10-provider-reported-turn-spend
plan: "03"
subsystem: cost
tags: [reported-actuals, btw-carrier, fresh-wrapper, initial-build, live-proof, openrouter]

# Dependency graph
requires:
  - phase: 10-provider-reported-turn-spend
    provides: 10-01 capture mixin + drain + marked rows, 10-02 blended totals + split
provides:
  - fresh wrapper per side build with per-side-turn drain on the pending 4-tuple
  - explicit-reported-wins record rule via _UNSET sentinel
  - initial-build wrap for sessions starting on OpenRouter models
  - env-gated live OpenRouter proof test
affects: [docs-cost]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 5358
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns: [fresh-instance-per-agent-build, tuple-carried-drain, explicit-wins-sentinel]

key-files:
  created: []
  modified: [strands_code_cli/reported_cost.py, strands_code_cli/loop.py, strands_code_cli/btw.py, strands_code_cli/main.py, tests/test_reported_cost.py, tests/test_model_switch.py]

key-decisions:
  - "Routed side wrap sits inside the resolve try so a wrap failure holds to the live model like any resolve failure"
  - "Live proof constructs LiteLLMModel directly (harness litellm builder only forwards LITELLM_* env, not OPENROUTER_API_KEY)"

patterns-established:
  - "Side builds fresh-copy cost-aware models; plain models pass through identical with zero drift"
  - "Drain-once at finish carried on the record tuple; explicit reported (incl None) never re-drains"

requirements-completed: [MODEL-05]

# Coverage metadata (#1602) — one entry per shipped deliverable. Drives DETERMINISTIC UAT routing in verify-work.
coverage:
  - id: D1
    description: "Side builds get fresh wrappers; draining one never touches parent or sibling costs"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestFreshSideModel"
        status: pass
    human_judgment: false
  - id: D2
    description: "Finished side turns carry drained cost on pending 4-tuples through to rows"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestSideDrainCarrier"
        status: pass
    human_judgment: false
  - id: D3
    description: "Explicit reported_cost (incl None) wins without consulting the model"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestExplicitReportedWins"
        status: pass
    human_judgment: false
  - id: D4
    description: "Sessions starting on OpenRouter capture from turn one; bedrock untouched; effort survives promotion"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestInitialBuildWrap + TestWrapScope + tests/test_model_switch.py#TestReportedWrapScope"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live OpenRouter turn captures a real reported cost end to end"
    requirement: "MODEL-05"
    verification:
      - kind: integration
        ref: "tests/test_reported_cost.py#TestLiveReportedCost (skipped: litellm extra not installed)"
        status: unknown
    human_judgment: true
    rationale: "The live path needs OPENROUTER_API_KEY plus the litellm extra; this run had the key but not the extra (never installed by plan tasks per T-10-SC), so the positive-float assertion never executed — a keyed run with the extra must confirm it."

# Metrics
duration: 7min
completed: 2026-10-12
status: complete
---

# Phase 10 Plan 03: Wiring completion — side/initial wrap sites plus live proof Summary

**Side turns capture independently per build with per-turn drains carried to rows, sessions starting on OpenRouter capture from turn one, and an env-gated live test proves the provider field flows through.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-10-12T23:22:04Z
- **Completed:** 2026-10-12T23:28:56Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- `fresh_side_model` per side build plus routed-spawn wrap; no shared wrapper instance between main and btw agents (D-09)
- `_finish_btw_turn` drains the serving side model; pending entries are `(question, answer, result, reported_cost)` 4-tuples with the closed consumer set updated
- `record_turn_metrics` honors an explicit `reported_cost` (including None) via the `_UNSET` sentinel; btw consumers pass the tuple-carried value
- `build_agent` promotes openrouter-resolved models in place after construction; the stashed kwargs keep the model string for replays
- `TestLiveReportedCost` (integration-marked, default-deselected) asserts a drained positive float and an actual-marked row, skipping cleanly without key or extra

## Task Commits

Each task was committed atomically:

1. **Task 1: Side path: routed wrap, fresh wrapper per build, per-turn drain carrier** - `1285c51` (test, RED) + `c939707` (feat, GREEN)
2. **Task 2: Initial build wrap plus wrap-scope and effort-survival tests** - `e232d27` (feat)
3. **Task 3: Live OpenRouter proof test plus phase suite gate** - `48d19b0` (test)

_Note: TDD task 1 has two commits (test → feat); no refactor commit was needed._

## Files Created/Modified

- `strands_code_cli/reported_cost.py` - `fresh_side_model` per-build fresh wrapper
- `strands_code_cli/loop.py` - `_UNSET` sentinel + explicit `reported_cost` kwarg, finish-time side drain, 4-tuple producer/consumers, routed side wrap
- `strands_code_cli/btw.py` - Fresh-copy on the kwargs-replay model, 4-tuple docstring shape
- `strands_code_cli/main.py` - Post-construction initial-build wrap with fail-soft
- `tests/test_reported_cost.py` - `TestFreshSideModel`, `TestSideDrainCarrier`, `TestExplicitReportedWins`, `TestInitialBuildWrap`, `TestWrapScope`, `TestLiveReportedCost` (10 tests)
- `tests/test_model_switch.py` - `TestReportedWrapScope` (3 tests: openrouter wraps, others identical, apply_switch effort forwarding)

## Decisions Made

- Routed side wrap sits inside the resolve `try` in `_route_side_spawn`: a wrap failure holds to the live model exactly like a resolve failure, keeping the side-hold contract (no new failure mode).
- Live proof constructs `LiteLLMModel` directly with the env key in `client_args`: the harness `litellm` builder only forwards `LITELLM_API_KEY`/`LITELLM_BASE_URL` env, so going through `resolve_model` would not carry `OPENROUTER_API_KEY`; direct construction follows the verified harness `client_args` shape.
- Non-openrouter wrap identity (task 1 acceptance criterion 4) was already pinned by `TestWrapGate::test_non_openrouter_ids_pass_through_identical` from 10-01 — not duplicated; the `fresh_side_model` passthrough case is the new pin.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `import strands_code_cli.main as main_module` resolves to the `main()` function (package re-export shadows the submodule); used the `importlib.import_module("strands_code_cli.main")` precedent from `test_cli_entry.py` in the test helper. Test-only, no production impact.
- `router.py:512` left untouched per the plan (validation-only call with discarded result).

## TDD Gate Compliance

Task 1 (`tdd="true"`) followed the RED→GREEN sequence with RED committed before any production edit:

- Task 1 RED (`1285c51`): `uv run pytest tests/test_reported_cost.py -q` → 5 failed / 17 passed. Failures are the missing feature itself (`ImportError: cannot import name 'fresh_side_model'`, `assert [3, 3] == [4, 4]` on the pending shape, `TypeError: record_turn_metrics() got an unexpected keyword argument 'reported_cost'`); all 17 passers are pre-existing 10-01 pins.
- GREEN (`c939707`) followed only after the failing run; file went 22/22 green, and btw/cost-context/idle suites stayed green (121 passed).
- Machine gate `gsd_run check tdd-red-evidence` was not invoked: 10-01 established it returns `INVALID_RED/zero_tests_discovered` for pytest output (TAP-only parser), and the RED evidence above is substantive and directly inspected.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Every OpenRouter turn path (switched, routed main, routed side, replayed side, initial build) now captures reported cost exactly once; main-vs-btw drains stay separate per D-09.
- Full suite green (1408 passed, 11 deselected); the live proof test skips with a naming reason here and awaits a keyed run with the litellm extra for the positive-path confirmation.
- Phase 10 plans complete (3 of 3); ready for phase verification.

---
*Phase: 10-provider-reported-turn-spend*
*Completed: 2026-10-12*
