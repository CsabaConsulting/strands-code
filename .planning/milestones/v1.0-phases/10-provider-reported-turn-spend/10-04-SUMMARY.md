---
phase: 10-provider-reported-turn-spend
plan: "04"
subsystem: cost
tags: [reported-actuals, main-drain, gap-closure, fail-soft, openrouter]

# Dependency graph
requires:
  - phase: 10-provider-reported-turn-spend
    provides: 10-01 drain helper + wrap factory, 10-03 pending 4-tuple carrier + _UNSET explicit-wins rule
provides:
  - serving-model main-turn drains with agent-shaped regression proof (G-01 closed)
  - drain-and-discard-once at the wrap choke point per D-09
  - fail-soft wrap/copy guards and finite-only cost extraction (WR-01..WR-03)
  - live proof accepting legitimate zero actuals (WR-04)
affects: [docs-cost, verify-work]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 1994
  tasks: 3
  commits: 5

# Tech tracking
tech-stack:
  added: []
  patterns: [serving-model-drain, discard-once-at-wrap, choke-point-fail-soft]

key-files:
  created: []
  modified: [strands_code_cli/loop.py, strands_code_cli/reported_cost.py, tests/test_reported_cost.py]

key-decisions:
  - "Re-wrap unconditionally resets _reported_costs to [] (absent/None/empty/non-empty converge; supersedes the 10-01 preserve-on-rewrap decision per D-09)"
  - "Nested-model fallback in _drain_reported_cost keeps agent-shaped callers draining even if a future site passes the Agent again"

patterns-established:
  - "Drain choke point: record_turn_metrics drains the serving model only; agent-shaped objects resolve via the nested fallback"
  - "Wrap choke point owns both promotion failure (return input) and pre-discipline accumulation (discard once)"

requirements-completed: [MODEL-05]

# Coverage metadata (#1602) — one entry per shipped deliverable. Drives DETERMINISTIC UAT routing in verify-work.
coverage:
  - id: D1
    description: "Main turns drain the serving model and store reported_cost with a marked usage line; pre-discipline accumulation is discarded once at wrap"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestMainDrainAgentShape (red-green proven, incl. stash demo)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Wrap, copy, and extract degrade to estimates instead of raising or poisoning totals"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#test_wrap_promotion_failure_returns_input_unchanged + test_fresh_side_model_copy_failure_returns_input + test_extract_rejects_nonfinite_costs"
        status: pass
    human_judgment: false
  - id: D3
    description: "Live OpenRouter proof accepts a legitimate present-0.0 actual"
    requirement: "MODEL-05"
    verification:
      - kind: integration
        ref: "tests/test_reported_cost.py#TestLiveReportedCost (skipped: litellm extra not installed)"
        status: unknown
    human_judgment: true
    rationale: "The live path needs OPENROUTER_API_KEY plus the litellm extra; this run has neither installed extra, so the relaxed >= 0 assertion never executed — a keyed run with the extra must confirm it."

# Metrics
duration: 4min
completed: 2026-10-13
status: complete
---

# Phase 10 Plan 04: Main-drain repair + drain-path hardening Summary

**Main OpenRouter turns drain the serving model and render marked actuals (G-01 closed), pre-discipline accumulation is discarded once at wrap, and the wrap/copy/extract path degrades to estimates instead of raising — full suite green.**

*Dispatch: generic-agent workaround (typed gsd-executor dispatch unavailable); results labeled accordingly.*

## Performance

- **Duration:** 4 min
- **Started:** 2026-10-12T23:58:25Z
- **Completed:** 2026-10-13T00:02:20Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Both main-turn `record_turn_metrics` sites now drain `getattr(agent, "model", None)`; `_drain_reported_cost` falls back to the nested serving model for agent-shaped callers (G-01 closed, SC-1 unblocked)
- `wrap_for_openrouter` resets `_reported_costs` to `[]` on every promotion, so costs accumulated without per-turn drain discipline are discarded once per D-09 instead of landing on one turn
- Promotion failure and side-model copy failure return the input unchanged (WR-01, WR-02); NaN/Inf/-Inf capture as absent via `math.isfinite` (WR-03)
- Live proof asserts `reported >= 0` so a legitimate present-`0.0` actual passes (WR-04); full suite 1413 passed, 11 deselected, live skips with a naming reason

## Task Commits

Each task was committed atomically:

1. **Task 1: G-01 drain the serving model, discard pre-discipline accumulation** - `d42ca7a` (test, RED) + `f926046` (feat, GREEN)
2. **Task 2: Fail-soft wrap, guarded copy, finite-only extract** - `bbff9b1` (test, RED) + `607b71e` (feat, GREEN)
3. **Task 3: WR-04 live-assertion fix plus full-suite and live-skip gate** - `b302324` (test)

_Note: TDD tasks 1-2 have two commits each (test → feat); no refactor commits were needed._

## Files Created/Modified

- `strands_code_cli/loop.py` - Serving-model drain arguments at both main-turn sites; nested-model fallback in `_drain_reported_cost`
- `strands_code_cli/reported_cost.py` - Discard-once at wrap, promotion try/except, copy try/except, `math.isfinite` gate
- `tests/test_reported_cost.py` - `TestMainDrainAgentShape` (2 tests), 3 hardening tests, relaxed live assertion

## Decisions Made

- Re-wrap unconditionally resets `_reported_costs` to `[]`: absent, None, empty, and non-empty inputs all converge on the same outcome, which is simpler than branching and implements exactly the plan's discard-once rule. This intentionally supersedes the 10-01 "initialize only when absent" decision per D-09 (unattributable spend must never land on one turn).
- Nested-model fallback lives in `_drain_reported_cost` (not just at the two repaired sites), so any agent-shaped caller drains correctly even if a future site passes the Agent again; the fail-soft `try/except` still returns None on drain errors.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## TDD Gate Compliance

Both `tdd="true"` tasks followed the RED→GREEN sequence with RED committed before any production edit:

- Task 1 RED (`d42ca7a`): `uv run pytest tests/test_reported_cost.py -q` → 2 failed / 26 passed. Failures are the missing feature itself (`KeyError: 'reported_cost'` on the agent-shaped drain — the exact G-01 mechanism; `[0.005, None]` kept instead of discarded on re-wrap). Target `TestMainDrainAgentShape::test_agent_shaped_model_drains_reported_cost` failed as required.
- Task 1 literal red-green demo per the plan: with production edits stashed, the agent-shaped test fails (`1 failed`); after `git stash pop`, the module suite passes (`28 passed, 1 deselected`).
- Task 1 GREEN (`f926046`): module suite 28 passed, 1 deselected; structural gates hold (drain-argument token exactly 2, zero `model=agent`).
- Task 2 RED (`bbff9b1`): 3 failed / 28 passed. Failures are the missing guards (RuntimeError propagating from the unguarded promotion/copy paths; NaN sum instead of None). All three named tests failed as required.
- Task 2 GREEN (`607b71e`): `tests/test_reported_cost.py tests/test_model_switch.py` → 138 passed, 1 deselected.
- Machine gate `gsd_run check tdd-red-evidence` was not invoked: no `gsd_run` in this environment, and 10-01 established it returns `INVALID_RED/zero_tests_discovered` for pytest output (TAP-only parser). The RED evidence above is substantive and directly inspected.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- G-01 closed: production-shaped main-turn drains store `reported_cost` and render `$0.00 actual`; the 10-03 `_UNSET` explicit-wins rule and pending 4-tuple carrier are byte-untouched (all carrier tests green).
- WR-01 through WR-04 hardened with pinning tests; full suite green with no new skips (1413 passed vs 1408 pre-plan = +5 new tests, 11 deselected unchanged).
- Phase 10 ready for re-verification: truths 1 and 14 should now verify; live positive path still needs a keyed run with the litellm extra (human check 1 from 10-VERIFICATION.md).

---
*Phase: 10-provider-reported-turn-spend*
*Completed: 2026-10-13*
