---
phase: 10-provider-reported-turn-spend
plan: "05"
subsystem: cost
tags: [reported-actuals, promotion-repair, gap-closure, uat-fix, openrouter]

# Dependency graph
requires:
  - phase: 10-provider-reported-turn-spend
    provides: 10-04 drain helper + WR-01 through WR-04 hardening (preserved exactly)
provides:
  - single-inheritance promotion succeeding on the real slotted LiteLLMModel chain (G-10-1, G-10-3 closed)
  - real-SDK promotion regression test with dummy client_args and zero network I/O
  - keyed live proof passing plus c1 rig C1 PASS
affects: [docs-cost, verify-work]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 1985
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns: [single-inheritance-composition, real-sdk-regression-pin]

key-files:
  created: []
  modified: [strands_code_cli/reported_cost.py, tests/test_reported_cost.py, scripts/uattest/driver.py]

key-decisions:
  - "Capture methods defined directly on single-inheritance ReportedCostModel(base) with __slots__ = (); mixin removed, class name and capture semantics kept verbatim"
  - "Real-SDK test feeds a Usage-shaped double (prompt/completion/total tokens + cost) because the real format_chunk metadata branch reads token counts"
  - "Rig wait patterns fixed to lowercase turn 1/turn 2 (product rendering pinned by exact-string tests); first c1 run already showed marked actuals on both surfaces"

patterns-established:
  - "Composition shape: capture subclass inherits the SDK base only, so CPython in-place __class__ promotion stays legal on slotted chains"
  - "Real-SDK regression: construct the installed SDK class with dummy client_args, wrap, assert promotion + capture + drain, zero network"

requirements-completed: [MODEL-05]

# Coverage metadata (#1602) — one entry per shipped deliverable. Drives DETERMINISTIC UAT routing in verify-work.
coverage:
  - id: D1
    description: "Single-inheritance promotion repair: real OpenRouter turns capture inline usage.cost and render marked actuals (G-10-1, G-10-3 closed)"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestPromotion::test_composed_class_uses_single_inheritance"
        status: pass
      - kind: unit
        ref: "tests/test_reported_cost.py#TestRealSdkPromotion::test_wrap_promotes_real_litellm_model_in_place"
        status: pass
      - kind: integration
        ref: "tests/test_reported_cost.py#TestLiveReportedCost (keyed: 1 passed)"
        status: pass
      - kind: other
        ref: "python scripts/uattest/driver.py c1 -> C1 PASS"
        status: pass
    human_judgment: false
  - id: D2
    description: "Real-SDK promotion regression test pins in-place promotion on the installed SDK class with dummy client_args and zero network I/O"
    requirement: "MODEL-05"
    verification:
      - kind: unit
        ref: "tests/test_reported_cost.py#TestRealSdkPromotion::test_wrap_promotes_real_litellm_model_in_place (RED-demonstrated against pre-fix code)"
        status: pass
    human_judgment: false
  - id: D3
    description: "c1/c2 rig wait patterns match the lowercase cost-row rendering"
    requirement: "MODEL-05"
    verification:
      - kind: other
        ref: "python scripts/uattest/driver.py c1 -> C1 PASS; pytest tests/test_uattest_driver.py (21 passed)"
        status: pass
    human_judgment: false

# Metrics
duration: 7min
completed: 2026-10-13
status: complete
---

# Phase 10 Plan 05: Single-inheritance promotion repair Summary

**Real OpenRouter turns capture provider-reported cost end to end: single-inheritance promotion succeeds on the slotted SDK chain, the keyed live proof passes, and the c1 rig prints C1 PASS with marked actuals on the usage line and /cost row — G-10-1 and G-10-3 closed.**

*Dispatch: generic-agent workaround (typed gsd-executor dispatch unavailable); results labeled accordingly.*

## Performance

- **Duration:** 7 min
- **Started:** 2026-10-13T00:47:12Z
- **Completed:** 2026-10-13T00:54:26Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- `_composed_class` builds `class ReportedCostModel(base)` with `__slots__ = ()` and `format_chunk`/`take_reported_costs` defined directly; the mixin is gone, the WR-01 except, D-05 passthrough, and D-09 discard-once are byte-untouched in behavior
- `TestRealSdkPromotion` pins in-place promotion, config preservation, and verbatim capture on the installed `LiteLLMModel` with dummy `client_args` and zero network I/O (RED-demonstrated: fails on the pre-fix composition)
- Failing UAT test 1 command passes keyed (`1 passed`); full suite green (`1420 passed, 11 deselected`, zero failed/errors/skips); c1 rig prints the exact line `C1 PASS`

## Task Commits

Each task was committed atomically:

1. **Task 1: G-10-1/G-10-3 single-inheritance composed capture class** - `19f205b` (test, RED) + `b4981b5` (fix, GREEN)
2. **Task 2: Real-SDK promotion regression test (no network)** - `980e0a4` (test)
3. **Task 3: Failing-UAT-test re-run gate** - `991d326` (fix, rig wait-pattern case)

_Note: TDD task 1 has two commits (test → fix); task 2 is test-only with a stash-style RED demo against pre-fix production; task 3's commit is the rig fix from the deviation below._

## Files Created/Modified

- `strands_code_cli/reported_cost.py` - Single-inheritance `ReportedCostModel(base)` with direct capture methods; mixin removed; docstrings updated
- `tests/test_reported_cost.py` - `TestPromotion::test_composed_class_uses_single_inheritance` + `TestRealSdkPromotion` (module suite now 33 passed, 1 deselected)
- `scripts/uattest/driver.py` - c1/c2 `wait_for_new` patterns corrected to lowercase `turn 1`/`turn 2` plus comment

## Decisions Made

- Capture methods live directly on the composed class (not via a second base) because CPython rejects in-place `__class__` promotion from a single-base slotted instance to a multiple-inheritance subclass; `__slots__ = ()` keeps the instance layout identical so `_reported_costs` stores in the inherited `__dict__`.
- The real-SDK test feeds a Usage-shaped double (`prompt_tokens`/`completion_tokens`/`total_tokens` + `cost`) rather than the hermetic `_metadata` helper: the real `format_chunk` metadata branch reads token counts and raises `AttributeError` on a cost-only double, while capture itself records fine. The double keeps the test asserting clean capture+drain without coupling to an SDK-raising artifact.
- Rig wait patterns fixed instead of recording "rig unavailable": the rig ran fine and the first c1 log already showed the marked actuals on both surfaces — only the wait literal had the wrong case.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Rig bug] c1/c2 wait patterns used capitalized "Turn N" but the product renders lowercase "turn N"**
- **Found during:** Task 3 (c1 rig proof)
- **Issue:** `scenario_c1` timed out in `wait_for_new(sess, r"Turn 1", ...)` after the usage-line actual assertion had already passed; the saved log showed `turn 1: in 3.01K, out 2, $0.0002 actual` plus a plain total with no split — the product was correct, the rig literal was wrong (same latent bug in `scenario_c2`'s `Turn 2`)
- **Fix:** Lowercased both wait patterns plus the row-format comment in `scripts/uattest/driver.py`; re-ran c1 to the exact line `C1 PASS`
- **Files modified:** scripts/uattest/driver.py
- **Verification:** `python scripts/uattest/driver.py c1` → `C1 PASS`; `pytest tests/test_uattest_driver.py` → 21 passed; log corroborated (`$0.00 actual` usage line, `$0.0002 actual` row, plain total)
- **Committed in:** 991d326 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 rig bug blocking the verification gate)
**Impact on plan:** The fix touches the verification harness only (not production or test files, per the task's no-content-change rule for those); it unblocks the G-10-3 end-to-end proof with no scope creep.

## Issues Encountered

None in production code. The only failure observed was the rig wait-pattern timeout above, resolved as a deviation.

## Verification Evidence (verbatim)

UAT test 1 command (keyed, closes G-10-1):

```
uv run pytest tests/test_reported_cost.py::TestLiveReportedCost -q -rs -m integration
.                                                                        [100%]
1 passed in 4.74s
```

Full suite (phase gate):

```
uv run pytest tests/ -q
1420 passed, 11 deselected, 1081 warnings in 44.36s
```

(1413 pre-plan + 5 rig-driver tests from `eb51f66` + 2 new 10-05 tests; deselected 11 unchanged; a second run with `-rs` showed zero `SKIPPED` lines and zero failed/errors.)

c1 rig (closes G-10-3 end to end):

```
python scripts/uattest/driver.py c1
[cost-rows] seen
C1 PASS
[saved] /tmp/uatr8/c1.log
```

c1 log corroboration (`/tmp/uatr8/c1.log`): `3.01K (2%) $0.00 actual` on the post-turn usage line; `turn 1: in 3.01K, out 2, $0.0002 actual` on the /cost row; plain `Total:` with no split line (pure-actual session per D-11).

Single-inheritance probe (task 1 gate): prints the exact line `single-inheritance OK`; structural gate `class ReportedCostModel(base):` holds (one base only).

## TDD Gate Compliance

Both `tdd="true"` tasks followed RED→GREEN with RED evidenced before the production fix took effect:

- Task 1 RED (`19f205b`, test-only): module suite → `1 failed, 31 passed, 1 deselected`. The named target `TestPromotion::test_composed_class_uses_single_inheritance` fails on the planned behavior (MRO contains `ReportedCostMixin` between the composed class and the base). Intentional RED, directly inspected.
- Task 1 GREEN (`b4981b5`, production-only): module suite → `32 passed, 1 deselected`; probe prints `single-inheritance OK`; real-SDK wrap probe promotes in place with preserved config.
- Task 2 (test-only, `980e0a4`): `TestRealSdkPromotion` RED-demonstrated by reverting production to the pre-fix composition — `1 failed` (`assert type(model) is not LiteLLMModel`, the unpromoted instance) — then restored → `33 passed, 1 deselected`. Mirrors the 10-04 literal red-green demo protocol.
- Machine gate `gsd_run check tdd-red-evidence` was not invoked: no `gsd_run` in this environment, and 10-01 established it returns `INVALID_RED/zero_tests_discovered` for pytest output (TAP-only parser). The RED evidence above is substantive and directly inspected.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- G-10-1 closed (blocker): the keyed UAT test 1 command passes — a real `LiteLLMModel` promotes in place, captures inline `usage.cost`, and drains a float >= 0 with an actual-marked row.
- G-10-3 closed (major): a real OpenRouter main turn shows the marked actual on the usage line and the /cost row (c1 rig `C1 PASS`, log-corroborated).
- The hermetic stub can never mask a promotion failure again: `TestRealSdkPromotion` runs in the default suite wherever the litellm extra exists (skips with the naming reason otherwise) with zero network I/O.
- Phase 10 ready for re-verification: UAT tests 1 and 3 should now pass; prohibitions P1/P2/P3 were accepted in UAT test 2 and the fix changes only the composition shape (D-05 fail-soft, D-09 discard-once, display-only posture all preserved).

---
*Phase: 10-provider-reported-turn-spend*
*Completed: 2026-10-13*
