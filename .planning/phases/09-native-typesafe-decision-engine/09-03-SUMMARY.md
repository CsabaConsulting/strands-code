---
phase: 09-native-typesafe-decision-engine
plan: "03"
subsystem: routing
tags: [typesafe, jev, probe-calibration, baseline, live-tests, uat-rig]

# Dependency graph
requires:
  - phase: 09-native-typesafe-decision-engine/09-01
    provides: native transport decide_via_typesafe, ordered chain, computed spend
  - phase: 09-native-typesafe-decision-engine/09-02
    provides: setup order proposal, validate live-ping, skip notes
provides:
  - Probe runner --run native with the native fault set over the full 20-probe set
  - Native baseline section (verdicts, pins, snapshots, distributions) with STAND verdict
  - Native live-engine integration tests (round trip, spend identity, usage folding)
  - Native rig scenarios n1-n4 plus r1 migrated to the ordered setup flow
affects: [phase-10 routing consumers, docs-routing, verify-work UAT]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 14686
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns: [rig env-prefix boots for key-present/absent/bogus, per-engine fault maps in probes.jsonl]

key-files:
  created: []
  modified:
    - scripts/route-probe.py
    - evals/routing-probe/baseline.json
    - evals/routing-probe/probes.jsonl
    - scripts/uattest/driver.py
    - tests/test_routing.py
    - tests/test_routing_calibration.py
    - tests/test_uattest_driver.py

key-decisions:
  - "Native fault keys added to the probes.jsonl fault maps (bad-key, no-key); without them the native fault arms are dead code in live runs"
  - "Fresh --run openrouter and --run local runs precede --compare: compare needs all three run files, and the fresh runs double as a drift check"
  - "N4 asks the debug ask, not the r2 trivial ask: Jev holds the trivial ask 2/2 at 50% under the rig strategy"
  - "N4 asserts the via-native spend cell, not the Prices marker: live turns fold the single-source marker into mixed"
  - "R1 branches on the native radio so it passes with and without a key"

patterns-established:
  - "Rig start_cli env_prefix: keyless (env -u) and bogus-key boots without touching the ambient environment"
  - "Native rig constants NATIVE_PIN / NATIVE_SNAPSHOT / BOGUS_TYPESAFE_KEY plus strategy_order file-shape helper"

requirements-completed: [MODEL-04]

# Coverage metadata (#1602) — one entry per shipped deliverable.
coverage:
  - id: D1
    description: "Probe runner addresses native end to end (run, faults, compare) with hermetic tests"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_routing_calibration.py#TestNativeProbeArm"
        status: pass
      - kind: other
        ref: "python3 scripts/route-probe.py --dry-run (engines line lists native)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Native 20-probe calibration recorded; shared 0.62/0.04 knobs STAND on probe evidence"
    requirement: "MODEL-04"
    verification:
      - kind: other
        ref: "python3 scripts/route-probe.py --compare (clean, 2 warnings, exit 0)"
        status: pass
      - kind: unit
        ref: "tests/test_routing_calibration.py#TestCalibrationBaseline"
        status: pass
    human_judgment: false
  - id: D3
    description: "Single native-vs-OpenRouter disagreement closed as same-engine effort jitter, not a transport bug"
    requirement: "MODEL-04"
    verification:
      - kind: other
        ref: "fresh --run openrouter reproduced the c-single-candidate flip (low 0.53/0.47 -> medium 0.52/0.48)"
        status: pass
    human_judgment: true
    rationale: "Bug-vs-jitter closeout rests on analyst judgment over two near-tie tables; evidence is recorded below for reviewer sign-off"
  - id: D4
    description: "Live native tests prove round trip, snapshot, exact spend math, usage folding, skip and fail-loud rules"
    requirement: "MODEL-04"
    verification:
      - kind: integration
        ref: "tests/test_routing.py#TestLiveEngines native tests (pass with key, skip without)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Rig scenarios n1-n4 cover native setup, hidden-until-key, validate ping, and a native-routed turn"
    requirement: "MODEL-04"
    verification:
      - kind: e2e
        ref: "python3 scripts/uattest/driver.py n1/n2/n3/n4 (all PASS)"
        status: pass
    human_judgment: false
  - id: D6
    description: "R1 migrated to the ordered setup flow and passes"
    requirement: "MODEL-04"
    verification:
      - kind: e2e
        ref: "python3 scripts/uattest/driver.py r1 (PASS)"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-10-12
status: complete
---

# Phase 09 Plan 03: Native Probe Calibration Live Tests Rig Summary

**Native engine measured like the others: `--run native` over 20 probes with a recorded STAND verdict, live spend-identity tests, and rig rows n1-n4 all green.**

**Dispatch note:** Executed by gsd-executor 09-03 via the generic-agent workaround (typed dispatch unavailable).

## Performance

- **Duration:** 25 min
- **Started:** 2026-10-12T20:41:23Z
- **Completed:** 2026-10-12T21:06:01Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- `--run native` executes the full 20-probe set through `decide_via_typesafe` with shared builders plus gate; native fault arms (bad-key, no-key, unknown-model, shared timeout) restore `TYPESAFE_API_KEY` byte-identically
- Native calibration recorded in `baseline.json`: 20 verdicts, pin `jev-1.13.0`, snapshot `jev-1.13.0`, distributions, derivation note — shared 0.62/0.04 knobs STAND
- D-11 investigation closed with same-engine proof: the lone flip reproduces on a fresh OpenRouter run, so it is D-16 effort jitter, not a transport bug; no knob touched, neither side preferred
- Live native tests assert typed tables, jev-1.13-family snapshots, and exact `input_tokens x 0.042/1e6` spend at both transport and `decide()` usage-triple level; skip without a key, fail loudly on rejection
- Rig rows n1 (native-first proposal), n2 (hidden-until-key), n3 (validate ok plus bad-key INVALID), n4 (native-routed turn with `via native` spend) all PASS live; r1 migrated to the ordered setup flow and passes

## Task Commits

Each task was committed atomically:

1. **Task 1: Probe runner gains --run native with the native fault set** - `06ad6e6` (feat)
2. **Task 2: Native 20-probe calibration run against the shared baseline** - `50a39e6` (feat)
3. **Task 3: Native live-engine tests plus rig scenarios** - `aa3c89a` (feat)

**Plan metadata:** pending (docs: complete plan)

## Files Created/Modified

- `scripts/route-probe.py` - `NATIVE_MODEL_PIN`, native `run_probe` arm (timeout kwarg only), native fault arms plus generalized restore, cloud-path `cmd_run`, `--run native`, `--native-model`, native compare path, dry-run engine list
- `evals/routing-probe/probes.jsonl` - Native keys in the two per-engine fault maps (deviation 1)
- `evals/routing-probe/baseline.json` - Native section: 20 verdicts, pins/snapshots entries, distributions, `native_note`, derivation extension with the STAND verdict
- `tests/test_routing_calibration.py` - `TestNativeProbeArm` (9 hermetic tests), 3-engine baseline sets, native record-shape parity pin
- `tests/test_routing.py` - Two native `TestLiveEngines` tests (transport table plus spend identity, `decide()` usage folding)
- `scripts/uattest/driver.py` - `start_cli` env-prefix, scenarios n1-n4, `strategy_order` helper, r1 rewritten for the ordered setup flow
- `tests/test_uattest_driver.py` - Native-helper shared-constant pin

## Calibration Record (Task 2 Evidence)

Native run (`--run native`, key present): 20 verdicts written, exit 0. Pin `jev-1.13.0` on all records; snapshot `jev-1.13.0` on all 17 answered probes; fault probes hold (bad-key `HTTP 401`, no-creds, timeout `unreachable`).

Gated-verdict agreement native-vs-baseline-OpenRouter: **19/20**. The single flip is `c-single-candidate`, a `pick_effort` (ungated by design, D-16) read:

- Baseline OpenRouter: `{low: 0.53, medium: 0.47}` margin 0.06, gated `low`
- Native: `{low: 0.49, medium: 0.51}` margin 0.02, gated `medium`
- Fresh OpenRouter re-run (same engine, same transport): `{low: 0.48, medium: 0.52}`, gated `medium`

The flip reproduces on the same engine across runs — a 0.04 near-tie wobble inside 2-decimal rounding, both sides `match: true`. The fresh OpenRouter run also moved `e-short-deep-2` top-1 0.51 to 0.56, exactly matching native's 0.56. Transport and wiring are exonerated: identical shared builders, zero schema failures, 16/16 `pick_model` gated verdicts identical. Closed as D-16 jitter; knobs untouched, neither side preferred.

**Knob verdict: STAND.** No routed-but-wrong above threshold (the one routed `match: false` row is `a-length-trap`, identical on both engines — the known confident misroute); no mass hold where OpenRouter routes (holds identical: `e-long-ask`, `e-short-deep-2`, three fault probes). Distribution means: top-1 0.855 vs 0.854, margin 0.716 vs 0.713 (OpenRouter vs native).

Compare output (all three engines run fresh this session):

```text
warn: openrouter/c-single-candidate: effort low -> medium (ungated read)
warn: openrouter/e-short-deep-2: top1_prob 0.51 -> 0.56
compare: clean (2 warning(s))
```

Exit 0. Native rows: zero drifts, zero warnings.

## Decisions Made

- Native fault keys (`bad-key`, `no-key`) added to the `probes.jsonl` fault maps: `_fault_for` returns None for unlisted engines, so without them the native arms never fire live and fault probes would record routed verdicts, corrupting the D-11 analysis. Mirrors the local-keys precedent; openrouter/local runs byte-identical.
- Fresh `--run openrouter` and `--run local` runs precede `--compare`: compare diffs all three run files and reports missing ones as drift, so a native-only run can never exit 0; the fresh runs also re-verified zero drift on the other engines (2 warnings only).
- N4 asks the debug ask instead of the r2 trivial ask: Jev holds the trivial ask 2/2 at 50% under the rig strategy (trivial-to-tiny vs directives-to-current deadlock), while the debug ask routes current at 0.92-0.95. Genuine model judgment, reproduced — not a bug.
- N4 asserts the `via native` spend cell rather than the `Prices: native computed input rate.` marker: live turns carry their own provenance, folding the single-source marker into `Prices: mixed (per-turn model).` (shipped 09-01 unit-pinned behavior, out of scope to change).
- R1 branches on the native radio (alternation wait) so it passes key-present and key-absent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Native fault keys added to probes.jsonl**
- **Found during:** Task 1 (wiring the native fault set)
- **Issue:** Plan lists `route-probe.py` plus tests only, but per-engine fault maps without a `native` key make `_fault_for` return None — the new fault arms would be unreachable in live runs and fault probes would record routed verdicts.
- **Fix:** Added `"native": "bad-key"` to `f-bad-key-401` and `"native": "no-key"` to `f-no-creds`. OpenRouter/local runs unaffected (per-engine lookup).
- **Files modified:** evals/routing-probe/probes.jsonl
- **Verification:** Task-2 live run holds all three fault probes (`HTTP 401`, no-creds, `unreachable`); composition tests green
- **Committed in:** 06ad6e6 (Task 1 commit)

**2. [Plan-required] Calibration baseline tests migrated to three engines**
- **Found during:** Task 2 (recording the native section the plan mandates)
- **Issue:** Three tests pinned engine sets to `{"local", "openrouter"}`; the plan's acceptance criteria require `native` keys in verdicts, pins, and snapshots — a direct contradiction.
- **Fix:** Sets extended to three engines, coverage test renamed to `..._on_every_engine`, native record-shape parity plus pin assertions added.
- **Files modified:** tests/test_routing_calibration.py
- **Verification:** 31/31 calibration tests pass; `python3 -c` criterion passes
- **Committed in:** 50a39e6 (Task 2 commit)

**3. [Plan-required] Scenario r1 rewritten for the 09-02 ordered setup flow**
- **Found during:** Task 3 (acceptance requires r1 passing)
- **Issue:** 09-02 replaced the engine radio with the order proposal plus builder and added local-tag, native-pick, and skip-notes steps; the old r1 scripted dead prompts (`Decision engine` radio, `1 candidate, engine openrouter` summary) and could not pass.
- **Fix:** Rewrote r1's middle for the new sequence (proposal accept, candidate Done loop, decision, local tag, conditional native pick, skip notes, directives, ordered summary); coverage unchanged (live split catalogs, round-trip, no key material, VALID against the cached catalog).
- **Files modified:** scripts/uattest/driver.py
- **Verification:** `python3 scripts/uattest/driver.py r1` → R1 PASS (live tmux)
- **Committed in:** aa3c89a (Task 3 commit)

**4. [Rule 2 - Missing Critical] Static guards for the new native scenarios**
- **Found during:** Task 3 (repo convention: every live-only scenario family carries static pins)
- **Issue:** The 08 gap-closure guards pin r-scenario shape (levels, shared constant, no key material); n-scenarios without equivalents reopen the audit gap.
- **Fix:** Added n1-n4 exposure, native-helper levels plus shared-constant, and bogus-key-only pins.
- **Files modified:** tests/test_routing_calibration.py, tests/test_uattest_driver.py
- **Verification:** 50/50 calibration plus uattest tests pass
- **Committed in:** aa3c89a (Task 3 commit)

---

**Total deviations:** 4 (2 missing-critical, 2 plan-required migrations)
**Impact on plan:** All required by the plan's own acceptance criteria plus standing repo contracts. No scope creep.

## Issues Encountered

- N4 first failed on a hold: the r2 trivial ask routes via the local daemon but Jev holds it at 50% under the rig strategy. Reproduced 2/2 via direct `decide()` calls (50% hold vs 0.95 route on the debug ask), confirming genuine model judgment rather than flake or wiring fault. Resolved by asking the debug ask with a `debugdone` marker contract.
- N4 then failed on the Prices marker: live `/cost` with turns plus routing folds provenances into `Prices: mixed (per-turn model).`, so the unit-pinned single-source marker never renders live. Resolved by asserting the `via native $N.NNNN` spend cell (the r3 precedent) instead of changing shipped 09-01 cost logic.
- The `e-long-ask`, `e-short-deep-2`, `f-ambiguous-hold`, and `a-length-trap` native rows show `match: false` — all four identically on the baseline OpenRouter run (threshold-caught wrong-tier reads and known misroutes), so none is divergence.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Engine parity loop closed: native is transported, set-up-able, validatable, probed, baseline-recorded, live-tested, and rig-covered; full suite 1363 passed / 10 deselected.
- Phase 9 complete after this plan (3 of 3): ready for phase transition / verify-work UAT (D3 invites one human skim of two near-tie tables).
- Live-contract drift coverage is in place: validate ping, integration tests, `--compare` regression, and the n3 bad-key row all fail loudly on endpoint/auth/model-shape drift.

---
*Phase: 09-native-typesafe-decision-engine*
*Completed: 2026-10-12*

## Self-Check: PASSED
