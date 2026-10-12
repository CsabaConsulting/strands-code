---
phase: 09-native-typesafe-decision-engine
plan: "02"
subsystem: routing
tags: [typesafe, jev, setup, validate, skip-notes, routing-docs]

# Dependency graph
requires:
  - phase: 09-native-typesafe-decision-engine/09-01
    provides: native transport, ordered chain, skip-note helper, extended engine schema
provides:
  - Setup order builder with availability proposal, hidden-until-key native, pinned Jev list
  - Validate live-ping with loud key/model failures
  - Once-per-session skip-note printing in the pre-turn hook
  - Native engine user docs in docs/ROUTING.md
affects: [09-03 probe-calibration, docs-routing]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 16359
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns: [availability-proposed order with typed confirm, conditional validate live-ping, once-per-session emitted set]

key-files:
  created:
    - tests/test_router_setup.py
  modified:
    - strands_code_cli/router.py
    - strands_code_cli/routing.py
    - strands_code_cli/loop.py
    - docs/ROUTING.md
    - tests/test_routing.py
    - tests/test_routing_strategy.py
    - tests/test_loop_routing.py

key-decisions:
  - "Setup stdout never prints the TYPESAFE_API_KEY literal (uses 'TypeSafe key' phrasing), keeping test_setup_never_prompts_for_keys green unweakened"
  - "Validate ping flips the report head to INVALID on key/model failures — appended lines alone would not 'fail bad keys'"
  - "Ping gate reads strategy.engine.order directly: the loader coerces primary, so native reaches the effective order only via explicit order"
  - "Off-tty order builder aborts on the second unknown engine (fail-closed, no valid-subset write, unlike candidates)"

patterns-established:
  - "Env reads stay in the engine layer: setup availability goes through native_engine_ready plus local_engine_ready, never os.environ in router.py"
  - "Yes/no setup prompts share _setup_confirm (empty takes the default, one re-prompt, then fail-closed)"

requirements-completed: [MODEL-04]

# Coverage metadata (#1602) — one entry per shipped deliverable.
coverage:
  - id: D1
    description: "Setup proposes the availability order and builds custom orders with native hidden until a key exists"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_router_setup.py#TestSetupOrderProposal"
        status: pass
      - kind: unit
        ref: "tests/test_router_setup.py#TestSetupOrderBuilder"
        status: pass
    human_judgment: false
  - id: D2
    description: "Native pick offers exactly the pin plus alias with a drift warning on the alias choice"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_router_setup.py#TestSetupNativePick"
        status: pass
    human_judgment: false
  - id: D3
    description: "Validate live-pings native: ok names the snapshot, bad keys and model strings fail with fix lines"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_router_setup.py#TestValidatePing"
        status: pass
    human_judgment: false
  - id: D4
    description: "Keyless native prints its skip note once per session unless skip_notes is false, even under quiet"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_loop_routing.py#TestChainSkipNotes"
        status: pass
    human_judgment: false
  - id: D5
    description: "ROUTING.md documents native setup, validate, cost provenance, calibration, and valid model strings"
    requirement: "MODEL-04"
    verification:
      - kind: other
        ref: "grep -c TYPESAFE_API_KEY/jev-1.13.0/order counts"
        status: pass
    human_judgment: true
    rationale: "Grep counts prove the markers exist, not that the prose is accurate — needs a human skim"

# Metrics
duration: 17min
completed: 2026-10-12
status: complete
plan_head_before: db5897291ad1a4b54b9056e846f888203580b4ae
---

# Phase 09 Plan 02: Native Setup Validate Notes Docs Summary

**Native engine goes user-operable: availability-proposed setup order with a pinned Jev pick, validate live-ping that fails bad keys and model strings, once-per-session skip notes, and full ROUTING.md coverage.**

**Dispatch note:** Executed by gsd-executor 09-02 via the generic-agent workaround (typed dispatch unavailable).

## Performance

- **Duration:** 17 min
- **Started:** 2026-10-12T20:19:37Z
- **Completed:** 2026-10-12T20:37:04Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Setup proposes native-first with a key (else OpenRouter-then-local), accepts on an empty line, and builds custom orders with native hidden until a key exists
- Pinned Jev pick offers exactly `jev-1.13.0` plus `jev-latest`; the alias prints a drift warning naming snapshot logging, the pin stays quiet
- Every setup abort path fails closed with nothing written; setup never prompts for keys and always writes `skip_notes` as an explicit bool
- Validate runs one cheap native ping when native is listed and the file is valid: ok names the snapshot, 401/403 fail the key, 400 fails the model string, transport failures warn, absent key skips
- Pre-turn hook prints each skip note once per session unless `skip_notes` is false — even under quiet; side spawns stay transcript-quiet
- ROUTING.md gains the native engine: setup/proposal, validate ping, computed-spend provenance, shared-knob calibration with disagreement-as-bug, and valid model strings

## Task Commits

Each task was committed atomically:

1. **Task 1: Setup native branch with availability order and pinned Jev list** - `70eea84` (feat)
2. **Task 2: Validate live-ping plus once-per-session skip notes** - `6516470` (feat)
3. **Task 3: Native engine user docs** - `ca3abff` (docs)

**Plan metadata:** pending (docs: complete plan)

## Files Created/Modified

- `strands_code_cli/router.py` - Order proposal plus builder, pinned Jev pick, conditional model prompts, skip-notes knob, ordered payload, validate live-ping
- `strands_code_cli/routing.py` - `native_engine_ready` plus None-base `local_engine_ready` for setup availability (engine layer owns env reads)
- `strands_code_cli/loop.py` - Once-per-session skip-note printing in the pre-turn hook
- `docs/ROUTING.md` - Native engine section plus Engines/Quick start/Manual edits/Keys updates
- `tests/test_router_setup.py` - Setup order/pin/abort tests plus validate-ping mapping tests (new file, 24 tests)
- `tests/test_routing_strategy.py` - TestRouteSetup migrated to the new setup flow
- `tests/test_loop_routing.py` - TestChainSkipNotes (once-per-session, suppression, quiet)
- `tests/test_routing.py` - Readiness-helper pins (native presence, None-base probe)

## Decisions Made

- Setup stdout never prints the `TYPESAFE_API_KEY` literal — "TypeSafe key" phrasing keeps `test_setup_never_prompts_for_keys` green unweakened while the validate fix lines (which need the exact var name) do name it.
- The validate ping flips the report head to INVALID on key/model failures: the must-have says validate "fails bad keys", which appended lines under a VALID head would not do.
- The ping gate reads `strategy.engine.order` directly instead of importing private `_effective_order`: the loader coerces `primary` to openrouter/local/off, so native reaches the effective order only via an explicit order.
- The off-tty order builder aborts on the second unknown engine rather than writing a valid subset — an order is positional, so a partial write would silently reorder the chain.
- Empty line at the proposal prompt accepts the order (nimble-default precedent); "yes" also accepts; unrecognized answers get one re-prompt, then fail closed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Availability detection moved into the engine layer**
- **Found during:** Task 1 (full-suite check after the setup implementation)
- **Issue:** The plan text said to read `os.environ` for the key inside `router.py`, but the standing `test_no_credential_persistence_sinks` contract forbids any `os.environ`/`os.getenv` in `router.py` — env reads live in the engine layer only (AGENTS.md posture).
- **Fix:** Added `native_engine_ready()` (key presence, no network — the RESEARCH pattern) to `routing.py`, extended `local_engine_ready` to resolve the default base from a None base, and setup calls both lazily. Pinned by two new tests in `test_routing.py`.
- **Files modified:** strands_code_cli/routing.py, strands_code_cli/router.py, tests/test_routing.py
- **Verification:** Full suite green (1337 passed); `grep -c 'os.environ\|os.getenv' strands_code_cli/router.py` prints 0
- **Committed in:** 70eea84 (Task 1 commit)

**2. [Plan-required] Existing TestRouteSetup tests migrated to the new setup flow**
- **Found during:** Task 1 (the plan replaces the engine radio with the proposal plus order builder)
- **Issue:** The 12 existing setup tests scripted the old radio sequence (scope, engine radio, candidates, always-decider); the mandated flow change invalidated every script.
- **Fix:** Migrated each test preserving intent: key hermeticity plus daemon-probe stubbing, proposal input line, conditional model prompts, skip-notes input, order-shaped payload assertions. The key-prompting security pins pass unweakened.
- **Files modified:** tests/test_routing_strategy.py
- **Verification:** Routing trio plus full suite green
- **Committed in:** 70eea84 (Task 1 commit)

---

**Total deviations:** 2 (1 architecture-posture fix, 1 plan-required test migration)
**Impact on plan:** Both required by the plan's own flow change plus standing repo contracts. No scope creep.

## Issues Encountered

None — all three task verifies and the full suite passed; the one mid-task failure (credential-sink contract) was a plan-text vs repo-contract conflict resolved as deviation 1 above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Setup, validate, skip notes, and docs are hermetic-green; full suite 1350 passed / 8 deselected.
- Ready for 09-03 (probe calibration): `decide_via_typesafe` is the shared transport for `--run native`, and every verdict logs the serving snapshot for `--compare` drift detection.
- Live-contract drift risk stays with 09-03 integration tests; the validate ping is the first live caller and will fail loudly on endpoint/auth/model-shape drift.

---
*Phase: 09-native-typesafe-decision-engine*
*Completed: 2026-10-12*

## Self-Check: PASSED
