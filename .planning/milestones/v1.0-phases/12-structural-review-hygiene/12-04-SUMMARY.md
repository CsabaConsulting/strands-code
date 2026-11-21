---
phase: 12-structural-review-hygiene
plan: "04"
subsystem: testing
tags: [uattest, tmux-rig, rig-split, contract-tests, importlib-loader]

requires:
  - phase: 12-structural-review-hygiene plan 12-03
    provides: repackaged CLI import paths the rig string literals already reference
provides:
  - scripts/uattest/uattest_lib.py shared tmux/send/wait/save plumbing (D-13)
  - Five per-area scenario files plus a 91-line thin driver.py with byte-identical command surface (D-14)
  - Mirrored tests/rig contract tests with all 26 assertions re-homed, none dropped
affects: [12-05, structural-review, uat-rig]

actuals:
  tokens: 30653
  tasks: 3
  commits: 2

tech-stack:
  added: []
  patterns: [sys.path-insert plus absolute sibling imports for loader-safe rig scripts (CF-07a)]

key-files:
  created:
    - scripts/uattest/uattest_lib.py
    - scripts/uattest/scenarios_side.py
    - scripts/uattest/scenarios_routing.py
    - scripts/uattest/scenarios_native.py
    - scripts/uattest/scenarios_cost.py
    - scripts/uattest/scenarios_codeact.py
    - tests/rig/test_uattest_side.py
    - tests/rig/test_uattest_routing.py
    - tests/rig/test_uattest_native.py
    - tests/rig/test_uattest_cost.py
    - tests/rig/test_uattest_codeact.py
  modified:
    - scripts/uattest/driver.py
    - scripts/uattest/README.md

key-decisions:
  - "wait_routed homed in uattest_lib: the plan requires the pane_text monkeypatch target to be the library module, satisfiable with verbatim bodies only when the wait lives there"
  - "ensure_workdir homed in uattest_lib: used by 4 of 5 areas; task 1 names workdir helpers in the extraction"
  - "Thin driver keeps _native_strategy + BOGUS_TYPESAFE_KEY re-exports so tests/routing/test_routing_calibration.py passes unmodified (outside plan files; minimal-diff discipline)"
  - "Constants single-homed in lib; driver imports LOGDIR/LOGDIR8 (no drift risk)"
  - "6 added dispatch/existence pins complete the identical-command-surface proof (all 14 scenario ids)"
  - "Task 3 verification-only, no commit: test-split content landed atomically in tasks 1-2 per the Rule 3 deviation"

patterns-established:
  - "Rig split files use sys.path insert + absolute sibling imports with per-line E402 noqa citing CF-07a (route-probe.py precedent)"
  - "Split contract tests load each rig module under its true import name so sibling imports reuse one module object"

requirements-completed:
  - STRUCT-01

coverage:
  - id: D1
    description: "Shared uattest_lib.py owns tmux/send/wait/save plumbing; scenarios import it"
    requirement: "STRUCT-01"
    verification:
      - kind: unit
        ref: "tests/rig/test_uattest_routing.py TestFailFast + TestWaitForNewBaseline (32 passed)"
        status: pass
      - kind: other
        ref: "grep NO-RELATIVE over scripts/uattest/*.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Five per-area scenario files behind a thin driver with identical command surface"
    requirement: "STRUCT-01"
    verification:
      - kind: other
        ref: "python3 scripts/uattest/driver.py a1 -> A1 PASS (live tmux run)"
        status: pass
      - kind: unit
        ref: "tests/rig/test_uattest_*.py per-area dispatch-id pins (all 14 ids)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Contract tests split to mirror with every assertion re-homed, none dropped"
    requirement: "STRUCT-01"
    verification:
      - kind: unit
        ref: "uv run pytest tests/rig/ -q (32 passed: 26 re-homed + 6 added)"
        status: pass
      - kind: other
        ref: "AST audit vs b33d1a8 original: 26/26 class-qualified names, 0 assert-count drift"
        status: pass
    human_judgment: false
  - id: D4
    description: "Full suite and all gates green on the split tree"
    requirement: "STRUCT-01"
    verification:
      - kind: unit
        ref: "uv run pytest tests/ -q (1538 passed, 11 deselected)"
        status: pass
      - kind: other
        ref: "ruff check + ruff format --check + xenon --max-absolute C + lint-imports (all exit 0)"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-10-16
status: complete
---

# Phase 12 Plan 04: Rig Split Summary

**1135-line uattest driver split into a shared plumbing lib, five per-area scenario files, and a 91-line thin driver with byte-identical command surface, proven by a live A1 PASS and mirrored contract tests carrying all 26 assertions.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-10-16T08:23:50Z
- **Completed:** 2026-10-16T08:32:27Z
- **Tasks:** 3 (2 content commits + 1 verification-only)
- **Files modified:** 14

## Accomplishments

- `scripts/uattest/uattest_lib.py` owns tmux/send/wait/save/lifecycle plumbing, workdir helpers, and all shared constants (D-13); every moved function verified byte-identical to the driver source
- Five `scenarios_<area>.py` files hold all twelve scenarios verbatim (docstrings, session naming, try/finally save+stop, PASS prints); native borrows routing helpers via absolute sibling imports (no cycle)
- `driver.py` reduced 1135 -> 91 lines with byte-identical module docstring, if/elif dispatch chain, and usage string; live `driver.py a1` prints A1 PASS
- Rig contract tests split into five mirrored files: 26/26 original tests re-homed under identical class-qualified names with zero assert-count drift, plus 6 added dispatch/existence pins covering all 14 scenario ids
- Full suite green (1538 passed = 1532 baseline + 6 added, 11 deselected); ruff check/format, xenon C, import-linter KEPT; calibration suite passes unmodified (34 passed)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extract the shared uattest library** - `4f83281` (refactor)
2. **Task 2: Per-area scenario files plus thin driver dispatch** - `b189f94` (refactor)
3. **Task 3: Split contract tests to mirror, re-homing every assertion** - verification-only, no commit (test-split content landed atomically in tasks 1-2 per the Rule 3 deviation below; task 3 ran the 26/26 re-home audit plus the full gate battery, all green)

**Plan metadata:** `(this file)` docs: complete plan

## Files Created/Modified

- `scripts/uattest/uattest_lib.py` - Shared plumbing: tmux, pane_text, wait_for, wait_for_new, send, start_cli, stop_cli, save, wait_main_end, wait_routed, ensure_workdir + constants/regexes
- `scripts/uattest/scenarios_side.py` - scenario_s1/s2 (Phase 7 /btw)
- `scripts/uattest/scenarios_routing.py` - scenario_r1..r4 + strategy/catalog/routed-line helpers (Phase 8)
- `scripts/uattest/scenarios_native.py` - scenario_n1..n4 + native pin/snapshot/setup helpers (Phase 9)
- `scripts/uattest/scenarios_cost.py` - scenario_c1/c2 + shared id/marker regexes/switch helper (Phase 10)
- `scripts/uattest/scenarios_codeact.py` - scenario_a1/a2 (Phase 11)
- `scripts/uattest/driver.py` - Thin dispatch: docstring, sys.path insert, scenario imports, dispatch chain (91 lines)
- `scripts/uattest/README.md` - One-line fix: timing-knob constants now live at the top of uattest_lib.py
- `tests/rig/test_uattest_<area>.py` x5 - Mirrored contract tests (2/16/3/6/5 tests)
- Deleted: `tests/rig/test_uattest_driver.py` - Replaced by the split files (26 assertions re-homed, 0 dropped)

## Decisions Made

- wait_routed homed in uattest_lib (not scenarios_routing as PATTERNS sketched): task 3 normatively requires the pane_text monkeypatch target to be the library module, and verbatim moved bodies resolve pane_text via their defining module's globals — satisfiable only with the wait in the lib. Also shared across areas (r2/r3/r4 + n4), so the shared lib is its natural home.
- ensure_workdir homed in lib: used by routing/native/cost/codeact scenarios; task 1 explicitly lists "workdir helpers" in the extraction set.
- Thin driver keeps `_native_strategy` + `BOGUS_TYPESAFE_KEY` re-exports (one combined E402+F401 noqa with reason): `tests/routing/test_routing_calibration.py` reads both off the loaded driver and is outside the plan's file list, so it passes unmodified (34 passed) under minimal-diff discipline.
- Constants single-homed in lib; driver imports LOGDIR/LOGDIR8 for boot (the RIG_NOVA_MICRO drift lesson rules out dual definitions).
- 6 added tests (side/native existence + per-area dispatch-id pins): the original file pinned only a1/a2; pinning all 14 ids is the "identical command surface" proof the must-haves demand.
- Task 3 verification-only with no commit: an empty marker commit would pollute history; the task's acceptance criteria (split files present, original absent, both suites green) are verified and recorded here.
- Plan's "update the two driver string literals" was a no-op: 12-03 already repointed them at `cost.live_pricing` / `dispatch.core`, and both symbols verified present.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test split executed atomically with the code moves (tasks 1-2), not in task 3**
- **Found during:** Task 1 (Extract the shared uattest library)
- **Issue:** The plan's transition scheme — tasks 1-2 verify the ORIGINAL tests/rig/test_uattest_driver.py unmodified against split code — is unsatisfiable: 8 tests do `monkeypatch.setattr(driver, "pane_text", ...)` then call `driver.wait_*`, but from-imported wait functions resolve `pane_text` via the lib module's globals, so the patch can never take effect (would fail with TIMEOUT, not fail-fast). No import arrangement fixes this with verbatim bodies.
- **Fix:** Split the contract tests to mirror in the same tasks as the code moves (task 1: plumbing homes; task 2: scenario homes), keeping every task-end state green. Task 3 then ran the 26/26 re-home audit plus the full gate battery instead of doing the split.
- **Files modified:** tests/rig/test_uattest_<area>.py x5 (created tasks 1-2 instead of 3), tests/rig/test_uattest_driver.py (removed task 1 instead of 3)
- **Verification:** tests/rig 32 passed at every task end; AST audit vs b33d1a8 original: 26/26 class-qualified test names, 0 assert-count drift (49 -> 59, +10 from the 6 added tests)
- **Committed in:** 4f83281 (Task 1 commit), b189f94 (Task 2 commit)

**2. [Rule 2 - Correctness] One-line uattest README fix for the relocated constants**
- **Found during:** Task 1 (constant extraction broke the documented location)
- **Issue:** README said timing-knob constants live "at the top of driver.py" — false once the lib owns them
- **Fix:** Repointed the sentence at uattest_lib.py (pre-existing scenario-list staleness left untouched as out of scope)
- **Files modified:** scripts/uattest/README.md
- **Verification:** Visual; command-surface docs unchanged and still accurate
- **Committed in:** 4f83281 (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 correctness)
**Impact on plan:** End state matches the plan exactly (same 12 artifacts, same layout, all must-haves); only the task-1/2-vs-3 sequencing changed, forced by module-namespace mechanics. No scope creep.

## Issues Encountered

- The plan-bug above (unmodified-tests-vs-split-code) was the only significant issue; see Deviations for the proof and repair. Two missed imports during drafting (`wait_for_new` in native/cost, `write_strategy` in native) were caught by the pre-commit name-resolution audit before any test run — no red run resulted.
- One `git commit` invocation failed on a stale pathspec (already-staged `git rm`); retried without it. No history impact.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for 12-05 (README refresh + CI gates + AGENTS.md refresh): rig split complete with identical behavior, suite 1538 green, all gates exit 0.
Notes for 12-05: the uattest README scenario list still covers s/r rows only (pre-existing gap, n/c/a never listed); docs/STRUCTURE.md driver line-count prose is now a historical pre-breakup measurement (consistent with 12-02/12-03 treatment — do not "update" the record); CI absence step for CLEANUP-01 still pending there. No blockers.

---
*Phase: 12-structural-review-hygiene*
*Completed: 2026-10-16*
