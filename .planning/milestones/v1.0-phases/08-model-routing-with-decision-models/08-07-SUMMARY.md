---
phase: 08-model-routing-with-decision-models
plan: "07"
subsystem: routing
tags: [uattest, bedrock, inference-profile, fail-fast, fence, live-verification]

requires:
  - phase: 08-06
    provides: Gap-closure loader/probe fixes the rig scenarios run against
  - phase: 08-04
    provides: r1-r4 rig scenarios and Decision-API strategy docs (rig owner)
provides:
  - Invokable profile-form rig candidate id from a single shared constant
  - Fail-fast rig waits with Turn-failed diagnostics
  - Routed-pick persistence fence off the global default
  - Live R2/R3/R4 PASS as G-08-1 acceptance proof
affects: [model-routing, uattest, verify-work]

actuals:
  tokens: 5352
  tasks: 3
  commits: 6
plan_head_before: fe9a59a8dda454bd9ce288c97ddbb55acf5c7179

tech-stack:
  added: []
  patterns: [shared-rig-constant, pre-send-wait-baselines]

key-files:
  created:
    - tests/test_uattest_driver.py
  modified:
    - scripts/uattest/driver.py
    - docs/ROUTING.md
    - strands_code_cli/loop.py
    - tests/test_loop_routing.py

key-decisions:
  - "FENCE (strongest form): routed picks never persist the global default; only explicit /model choices persist — routing re-decides every ask so pre-turn persistence only poisons the boot default"
  - "COST_RE matches the (n/a) usage-line fallback: nova turns print '4.49K (n/a) $0.00' by design (no nova window in MODEL_LIMITS), which the %-only pattern never saw"
  - "All wait baselines are captured pre-send: post-send/post-wait snapshots race instant replies and fast turns"

patterns-established:
  - "Pre-send wait baselines: wait_for_new takes a caller before count; r3 cost baselines snapshot before their send"

requirements-completed:
  - MODEL-03

coverage:
  - id: D1
    description: "Rig r2/r3/r4 strategies route to the invokable profile-form id from one shared constant"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_uattest_driver.py#TestRigModelId"
        status: pass
      - kind: e2e
        ref: "scripts/uattest/driver.py r2/r3/r4 -> R2/R3/R4 PASS"
        status: pass
    human_judgment: false
  - id: D2
    description: "Rig waits abort fast with a diagnostic naming the failed turn"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_uattest_driver.py#TestFailFast"
        status: pass
    human_judgment: false
  - id: D3
    description: "Routed picks never persist the global default; explicit /model still does"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop_routing.py#TestRoutedPickNoPersist"
        status: pass
      - kind: e2e
        ref: "live r3/r4 routed turns served; config model line still haiku after runs"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live r3/r4 PASS against real engines (G-08-1 acceptance proof)"
    requirement: "MODEL-03"
    verification:
      - kind: e2e
        ref: "scripts/uattest/driver.py r3 -> R3 PASS; r4 -> R4 PASS (/tmp/uatr8/r3.log, r4.log)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Rig waits recognize (n/a) cost lines and never race instant replies"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_uattest_driver.py#TestWaitForNewBaseline+TestR3CostBaselines"
        status: pass
      - kind: e2e
        ref: "scripts/uattest/driver.py r3 -> R3 PASS (toggle round-trip exercises both)"
        status: pass
    human_judgment: false

duration: 24min
completed: 2026-10-12
status: complete
---

# Phase 08 Plan 07: UAT Gap G-08-1 Closure Summary

**Rig routes to the invokable Bedrock profile-form id, waits fail fast on failed turns, routed picks no longer poison the global default — live R2/R3/R4 PASS.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-10-12T08:35:33Z
- **Completed:** 2026-10-12T08:59:07Z
- **Tasks:** 3
- **Files modified:** 5
- **Execution mode:** SEQUENTIAL via generic-agent workaround (typed GSD dispatch unavailable in this session)

## Accomplishments

- Replaced the throughput-incompatible bare Bedrock candidate id with the ACTIVE SYSTEM_DEFINED profile form `bedrock/us.amazon.nova-micro-v1:0` behind one shared `RIG_NOVA_MICRO` constant feeding all three r2/r3/r4 strategy blocks, plus the `docs/ROUTING.md` cheap-default example — the G-08-1 root cause.
- Added fail-fast `Turn failed` detection (`FAIL_RE`) to `wait_main_end` and `wait_routed`: failed turns now raise a diagnostic naming the wait plus the failed-turn line instead of hanging to TIMEOUT.
- Fenced routed-pick persistence off the global default: removed `save_model_choice` from the routed-pick branch so only explicit `/model` choices persist; the `/model` branch is byte-identical and the sole remaining call site.
- Proved acceptance live against real engines: **R3 PASS** (routed turn with both confidences, /cost entry, off/on toggle round-trip with hold retry) and **R4 PASS** (side-headed `Routed (btw)` with both confidences, side-flagged cost entry), plus **R2 PASS** regression (local engine, zero decision spend).

## Task Commits

Each task was committed atomically:

1. **Task 1: Point the rig at the invokable Bedrock profile-form id** - `efc2874` (fix)
2. **Task 2: Fail fast in the rig waits on failed turns** - `30f58b6` (fix)
3. **Task 3: Fence routed-pick persistence off the global default** - `a275cb8` (fix)

Auto-fix commits from live verification (Rule 1 deviations, each atomic):

4. **COST_RE matches unknown-window cost lines** - `9158a70` (fix)
5. **Pre-send baselines for instant rig replies** - `e3e99b4` (fix)
6. **Pre-send cost baselines in r3 toggle section** - `2dad781` (fix)

## Files Created/Modified

- `scripts/uattest/driver.py` - `RIG_NOVA_MICRO` constant, `FAIL_RE` fail-fast checks, `(n/a)`-tolerant `COST_RE`, `wait_for_new(before=)` plus pre-send baselines at all instant-reply and toggle sites
- `docs/ROUTING.md` - Cheap-default example carries the profile-form id; tier/criteria/levels unchanged
- `strands_code_cli/loop.py` - Routed-pick branch without the `save_model_choice` call (in-memory apply, session saves untouched)
- `tests/test_uattest_driver.py` (new) - Profile-form pins, fail-fast tests, `(n/a)` + baseline tests (12 tests)
- `tests/test_loop_routing.py` - 7 routed-pick assertions migrated to the FENCE contract plus `TestRoutedPickNoPersist`; explicit `/model` assertions untouched

## Decisions Made

- FENCE resolved in the strongest form per the plan: routed picks never persist (routing re-decides every ask per D-08, so pre-turn persistence buys nothing and risks poisoning the boot default with unvalidated picks); keep/defer rejected as recurrence-unprevented. No D-XX mandates routed-pick persistence.
- `(n/a)` cost lines are a legitimate product shape (D-02 never-guess fallback; MODEL_LIMITS has no nova keys), so the rig matches them rather than changing product display or teaching the almanac a window.
- All wait baselines are captured pre-send by construction: the helper takes caller baselines (`before`, `after`) and every call site snapshots before its send — no post-send/post-wait snapshots remain in the r-scenarios.
- Global default needed no repair: `~/.config/strands-code/config.yaml` already read the invokable haiku profile id (restored during diagnosis), confirmed read-only before and after the live runs.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] COST_RE never matched the (n/a) usage-line fallback**
- **Found during:** Live r3 re-run (plan acceptance verification)
- **Issue:** With the profile-form fix the routed turn succeeded, but `wait_main_end` still timed out: nova turns print `4.49K (n/a) $0.00` (unknown window is the documented D-02 fallback) while COST_RE only matched `(NN%) $`. No live nova turn had ever succeeded before, so the mismatch was latent.
- **Fix:** Widened COST_RE to `\((?:\d+%|n/a)\) \$` (driver-internal only; 4 use sites, all baselines/success checks).
- **Files modified:** scripts/uattest/driver.py, tests/test_uattest_driver.py
- **Verification:** New `(n/a)` no-false-positive test; live r3 advanced past main-end
- **Committed in:** 9158a70 (separate atomic commit)

**2. [Rule 1 - Bug] wait_for_new baseline race on instant local replies**
- **Found during:** Live r3 re-run (`TIMEOUT waiting for on` with the reply present in the transcript)
- **Issue:** `wait_for_new` snapshots its baseline after send; instant slash replies (`/route on`, `/route off`, `/cost`, `/route status`) can print before the snapshot, so the count never exceeds it. (Plan task 2's "do not touch wait_for/wait_for_new" scoped the fail-fast change only; this race fix adds no fail-fast there.)
- **Fix:** Optional caller `before` count on `wait_for_new` (default behavior unchanged); all 7 instant-reply sites snapshot pre-send.
- **Files modified:** scripts/uattest/driver.py, tests/test_uattest_driver.py
- **Verification:** Caller-baseline + default-snapshot tests; live r3 toggle advanced
- **Committed in:** e3e99b4 (separate atomic commit)

**3. [Rule 1 - Bug] r3 cost baselines snapshotted after the routed wait**
- **Found during:** Live r3 re-run (retry-branch `wait_main_end` TIMEOUT on a completed held turn)
- **Issue:** The toggle section snapshotted cost counts after `wait_routed` returned; a fast turn prints its cost line in between, so the stale baseline could never be exceeded. Same race class as #2 at the call site.
- **Fix:** Pre-send `oncheck_cost_before`/`after_cost` snapshots; retry-path baseline derived from the held turn's returned text; structurally pinned.
- **Files modified:** scripts/uattest/driver.py, tests/test_uattest_driver.py
- **Verification:** Baseline-ordering tests; live **R3 PASS**
- **Committed in:** 2dad781 (separate atomic commit)

---

**Total deviations:** 3 auto-fixed (3 bugs, all Rule 1)
**Impact on plan:** All three unblock the plan's own acceptance proof (live r3/r4 PASS); without them the fixed product still cannot be proven green. No scope creep — all changes are rig-side and pinned by tests.

## Issues Encountered

- The oncheck ask after `/route on` held once on confidence (`56% < 62%`, a legitimate D-16 threshold hold, not a failure); the rig's existing retry branch handled it and the retry routed — R3 PASS on the retry path, which also exercised the new baseline code.
- Live runs billed minimal spend: 3 decision calls via `inception/mercury-decide:free` plus Bedrock nova-micro/haiku turns (per-turn costs `$0.0000`–`$0.0002` in transcripts).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- G-08-1 closed: r2/r3/r4 all PASS live; the rig now routes to invokable ids, diagnoses failed turns immediately, and cannot poison the global default.
- Ready for UAT re-verification of phase 08 (test 1) and then `$gsd-verify-work` on this plan.
- Note for future rig work: MODEL_LIMITS still has no nova-family window, so nova turns keep printing the `(n/a)` fallback the rig now matches. Teaching the almanac a verified nova window is a product decision, out of scope here.

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-12*

## Self-Check: PASSED
