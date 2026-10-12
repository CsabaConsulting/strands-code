---
phase: 09-native-typesafe-decision-engine
plan: "01"
subsystem: routing
tags: [typesafe, jev, decision-engine, native-transport, chain-order, spend-provenance]

# Dependency graph
requires:
  - phase: 08-model-routing-with-decision-models
    provides: engine chain runner, OpenRouter/Ollama transports, verdict shape, gate knobs, /cost plumbing
provides:
  - Native Jev transport (decide_via_typesafe) with code-side computed spend
  - User-ordered engine chain (_effective_order, _chain_for) with legacy primary mapping
  - Extended engine schema (order, native_model, skip_notes) plus skip-note helper
  - Native computed-spend Prices provenance marker in /cost
  - Ordered-list and native-model strategy judging with fix lines
affects: [09-02 setup-validate-loop-notes, 09-03 probe-calibration, docs-routing]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 13598
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns: [user-ordered engine chain, code-side computed spend with provenance marker, strict-judge validate vs fail-soft loader]

key-files:
  created: []
  modified:
    - strands_code_cli/routing.py
    - strands_code_cli/cost_context.py
    - tests/test_routing.py
    - tests/test_routing_strategy.py
    - tests/test_cost_context.py

key-decisions:
  - "Empty effective order (explicit [] or legacy off) yields the off-equivalent hold via _effective_order in decide and _decide_effort"
  - "decision_model_for names the native model for native (Rule 2 adjunct — otherwise production native events skip the Prices marker)"
  - "Unknown primary is not judged when engine.order is present (ignored means ignored)"
  - "Non-list engine.order fails validation with a fix line, mirroring the candidates not-a-list precedent"

patterns-established:
  - "Order-framed validate lines for explicit orders; legacy primary-framed lines stay byte-identical plus a setup nudge note"

requirements-completed: [MODEL-04]

# Coverage metadata (#1602) — one entry per shipped deliverable.
coverage:
  - id: D1
    description: "Native transport routes one ask end to end with the shared verdict shape and computed spend"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestNativeEngine::test_native_success_routes_with_computed_spend"
        status: pass
      - kind: unit
        ref: "tests/test_routing.py#TestNativeEngine::test_native_transport_reports_snapshot_and_computed_cost"
        status: pass
    human_judgment: false
  - id: D2
    description: "User-ordered engines list drives the chain; legacy primary files map to the identical chain"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestNativeEngine::test_legacy_primary_maps_to_identical_chain"
        status: pass
      - kind: unit
        ref: "tests/test_routing.py#TestNativeEngine::test_native_first_attempts_native_before_openrouter"
        status: pass
      - kind: unit
        ref: "tests/test_routing.py#TestNativeEngine::test_openrouter_first_never_touches_native"
        status: pass
      - kind: unit
        ref: "tests/test_routing.py#TestNativeEngine::test_empty_order_holds_like_primary_off"
        status: pass
    human_judgment: false
  - id: D3
    description: "Native faults hold or retry exactly like the shared classes; keyless native skips with one note"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestNativeFaults"
        status: pass
    human_judgment: false
  - id: D4
    description: "Paid native calls render computed spend with the computed-rate Prices marker, never silent $0"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#TestRoutingEntries::test_native_entry_renders_computed_spend_with_marker"
        status: pass
      - kind: unit
        ref: "tests/test_routing.py#TestNativeFaults::test_native_verdict_cost_is_exact_input_rate_math"
        status: pass
    human_judgment: false
  - id: D5
    description: "Ordered-list and native_model files load fail-soft and judge strict with fix lines; keys never persist"
    requirement: "MODEL-04"
    verification:
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestRouteValidate native/order cases"
        status: pass
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestStrategyLoad order/cases"
        status: pass
    human_judgment: false

# Metrics
duration: 15min
completed: 2026-10-12
status: complete
---

# Phase 09 Plan 01: Native Transport Tracer Summary

**Native Jev decision engine end to end: `decide_via_typesafe` transport with computed spend, user-ordered chain with legacy mapping, native fault classes, computed-spend /cost marker, and strict ordered-list strategy judging.**

**Dispatch note:** Executed by gsd-executor 09-01 via the generic-agent workaround (typed dispatch unavailable).

## Performance

- **Duration:** 15 min
- **Started:** 2026-10-12T20:01:03Z
- **Completed:** 2026-10-12T20:16:14Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Stubbed native-routed ask serves pick plus confidences plus computed spend through the shared verdict shape
- Ordered engines list drives `_chain_for`; every legacy primary maps to the identical chain; empty order holds exactly like off
- Native 400/401/403/422 hold with zero retry, 429/529/5xx/timeouts retry exactly once, keyless native skips with the one-line D-03 note
- Paid native spend renders inline with the `native computed input rate` Prices marker (prohibition 1)
- Strategy files judge strict: verified native ids only, unknown engines fail, legacy files nudge toward /route setup, TYPESAFE keys never persist

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer): stubbed native Jev ask routes end to end through the ordered chain** - `f2f55da` (feat)
2. **Task 2: native fault matrix plus keyless skip plus computed-spend rendering** - `3ad0a01` (feat)
3. **Task 3: strategy judging for the ordered list plus native model strings** - `eafa769` (feat)

**Plan metadata:** pending (docs: complete plan)

_Tracer feedback gate: verified end-to-end, expanded with no checkpoint (end-of-phase mode, automated-only verify)._

## Files Created/Modified

- `strands_code_cli/routing.py` - Native transport, ordered chain, extended schema, skip-note helper, native ids, ordered validate judging
- `strands_code_cli/cost_context.py` - Native computed-spend Prices provenance marker in `cost_report`
- `tests/test_routing.py` - `TestNativeEngine` (tracer slice) plus `TestNativeFaults` (matrix, retry, skip, interrupt, spend)
- `tests/test_routing_strategy.py` - Ordered-list load cases, native validate cases, TYPESAFE secret-drop pin
- `tests/test_cost_context.py` - Native spend cell plus Prices marker test, openrouter no-leak guard

## Decisions Made

- Empty effective order yields the off-equivalent hold: `decide` and `_decide_effort` read the order head (or `off`) instead of `primary`, so explicit `order: []` behaves exactly like legacy `primary: off` including the single-candidate fast-path guard.
- Unknown `primary` is not judged when `engine.order` is present — an ignored value judges nothing; pinned by the both-present validate test.
- Non-list `engine.order` fails validation with a fix line, mirroring the `candidates` not-a-list precedent (loader stays warn-and-default).
- The OpenRouter catalog verdict block is shared between legacy and ordered branches via `_openrouter_catalog_lines`; legacy line texts stay byte-identical.
- `test_registry_orders_local_second` now expects `["openrouter", "local", "native"]` — the registry genuinely gains a member.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `decision_model_for` names the native model for native**
- **Found during:** Task 2 (computed-spend rendering)
- **Issue:** Production native routing events recorded `decision_model: None` (`decision_model_for` returned None for unknown engines), so the `if decision_model:` guard in `cost_report` skipped provenance entirely and real /cost output never carried the computed-rate marker the plan requires.
- **Fix:** Added the `native` branch returning `strategy.engine.native_model` (3 lines plus docstring), with a test pinning it.
- **Files modified:** strands_code_cli/routing.py, tests/test_routing.py
- **Verification:** `test_decision_model_for_names_native_model` passes; native event with the recorded model renders the marker.
- **Committed in:** 3ad0a01 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Required for the plan's own must-have (computed-rate Prices marker on real native asks). No scope creep.

## Issues Encountered

None — all three task verifies and the full suite passed on first run per task.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Tracer slice proven: transport, chain, verdict, spend, and judging all hermetic-green; full suite 1321 passed / 8 deselected.
- Ready for 09-02 (setup native branch, validate live-ping, once-per-session skip-note printing): `chain_skip_notes` and the `skip_notes` knob are in place awaiting the print site.
- Live-contract drift risk stays with 09-03 (`--run native` calibration plus integration tests); stubbed payloads follow the RESEARCH live-verified shapes.

---
*Phase: 09-native-typesafe-decision-engine*
*Completed: 2026-10-12*
