---
phase: 08-model-routing-with-decision-models
plan: "01"
subsystem: routing
tags: [decision-api, openrouter, ollama, urllib, pytest]

requires:
  - phase: 07-subagents-btw-side-channel
    provides: Side-spawn hook attachment point (_route_side_spawn) and BtwContext build seam
  - phase: 05-model-cost-context-commands
    provides: Almanac price_for for the tie-break plus /cost report surfaces
provides:
  - Typed Decision-API transports (OpenRouter /api/alpha/decisions, Ollama /v1/systemone) with one-retry policy
  - Answer validation plus code-side gate (confidence threshold, almanac tie-margin)
  - 4-tuple decide() verdict with usage triple, reported cost, and detail string
  - Pre-turn and side-spawn hook wiring with confidence-bearing lines and hold notes
  - Strategy knob validation (26-cap, 0..1 ranges, criteria type) and compact /cost routing entry
affects: [08-02, 08-03, 08-05, model-routing, cost-display]

actuals:
  tokens: 39731
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns: [typed-decision-answers-plus-code-gate, reported-cost-accounting-verbatim]

key-files:
  created: []
  modified:
    - strands_code_cli/routing.py
    - strands_code_cli/loop.py
    - strands_code_cli/cost_context.py
    - tests/test_routing.py
    - tests/test_loop_routing.py
    - tests/test_routing_strategy.py
    - tests/test_cost_context.py

key-decisions:
  - "Threshold holds short-circuit the engine chain (ambiguous ask retries next ask)"
  - "model_confidence is the routed model's own table probability, never vendor confidence"
  - "Same-model picks skip effort validation (locked no-op fast-path decision)"
  - "Reported decision cost verbatim into /cost; None renders zero, never estimated"
  - "Provisional gate defaults 0.70/0.05 ship marked for 08-05 calibration"

patterns-established:
  - "Decision-API verdict shape: (pick, engine, (input, output, cost|None), detail)"
  - "Hold notes carry a free-text detail; engine-failure shape stays byte-identical"
  - "Live integration tests pin the re-verified catalog id and fail loudly on drift"

requirements-completed:
  - MODEL-03

coverage:
  - id: D1
    description: "Decision-API transports with one-retry policy (OpenRouter + Ollama)"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestEngineChain+TestLocalEngine"
        status: pass
      - kind: integration
        ref: "tests/test_routing.py#TestLiveEngines (live Jev + tev1 round-trips)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Typed answer validation plus threshold/tie-break code gate"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestValidateChoiceAnswer+TestGateModel"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pre-turn and side-spawn hook wiring with routed/held transcript lines"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop_routing.py#TestPreTurnHook+TestSideRouting+TestCostRouting"
        status: pass
    human_judgment: false
  - id: D4
    description: "Strategy knob load plus validation (26-cap, ranges, criteria, effective values)"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestStrategyLoad+TestRouteValidate"
        status: pass
    human_judgment: false
  - id: D5
    description: "Compact /cost routing entry with reported-spend totals"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_cost_context.py#TestRoutingEntries"
        status: pass
    human_judgment: false

duration: 26min
completed: 2026-10-12
status: complete
---

# Phase 08 Plan 01: Decision-Core Rework Summary

**Typed Decision-API routing core (OpenRouter + Ollama transports, validation, threshold/tie gate, 4-tuple verdict, hook wiring, knob validation, compact /cost entry) with both engines verified live.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-10-12T04:50:26Z
- **Completed:** 2026-10-12T05:16:46Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Rebuilt both engine transports on true Decision APIs (`/api/alpha/decisions`, `/v1/systemone`) with shared state/question builders, typed answers, usage triples carrying reported cost, serving-snapshot logging, and at most one retry on retryable codes/timeouts (never 4xx or schema misses).
- Added strict answer validation (type, probability range/sum, live-candidate membership) and the code-side gate: top-1 probability threshold holds with a both-numbers note, near-tie top-two gaps substitute the cheaper almanac candidate with a tie-break marker.
- Wired the 4-tuple verdict through the pre-turn hook and side spawn: routed lines carry choice plus both confidences plus the code-computed ~$/ask delta, holds print distinct reason notes, and every decided ask appends a confidence/cost event.
- Extended strategy load/validate with the rework keys (criteria prose, tie_margin, confidence_threshold, 26-candidate cap, effective knob reporting) while keeping the single skip-reason source, symlink refusal, off handling, and secret-drop-on-save.
- Rebuilt the /cost routing entry as the compact D-12 line (ask, side, model, both confidences, spend) with reported cost verbatim, zero for cost-absent local calls, and reported spend folded into session totals.

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer: OpenRouter model-choice routing end to end, one path only** - `429c7ff` (feat)
2. **Task 2: Strategy validation for new keys plus /cost routing entry** - `35c7017` (feat)

## Files Created/Modified

- `strands_code_cli/routing.py` - Decision-API transports, builders, validation, gate, 4-tuple decide(), reshaped pick/strategy, rebuilt format lines, knob/cap validation
- `strands_code_cli/loop.py` - Pre-turn hook, side spawn, and routing events on the new verdict shape
- `strands_code_cli/cost_context.py` - Compact routing entry plus reported-spend totals fold
- `tests/test_routing.py` - Builder, validation, gate, transport, retry, fast-path, and live-engine tests
- `tests/test_loop_routing.py` - Hook, toggle, cost-event, and side-routing tests on the new shapes
- `tests/test_routing_strategy.py` - Knob load plus cap/range/criteria validation tests
- `tests/test_cost_context.py` - Compact, held, cost-absent, and totals routing-entry tests

## Decisions Made

- Threshold holds short-circuit the engine chain: a below-threshold table means the ask itself is ambiguous, so the retry happens next ask (D-08/D-16), never on the next engine.
- `model_confidence` records the routed model's own table probability (the runner-up read when the tie-break substitutes), never the vendor `confidence` field (Pitfall 1).
- Same-model picks skip effort validation in `decide()`, honoring the locked Phase-08 decision (validates on the switch path only); the hook applies no switch and no effort on the no-op path, so there is nothing to judge.
- Engine-failure hold notes stay byte-identical (`(openrouter failed; retrying next ask)`); threshold, effort, and resolve holds carry distinct details through the new free-text `detail` parameter.
- Reported decision cost flows verbatim into the /cost line and session totals; cost-absent local calls render `$0.0000` and the old token-estimate branch is deleted.
- Provisional gate defaults (`0.70`/`0.05`) ship explicitly marked for 08-05 probe calibration; the live decisions catalog was re-verified at implementation time (19 entries, `typesafe/jev-1.13` present).
- A lone candidate without levels holds with no engine call (a one-option choice is invalid and no effort exists to pass through); 08-02 keeps this as the existing hold behavior.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Cost fixture moved to the new event contract**
- **Found during:** Task 2 (`_routing_line` rebuild)
- **Issue:** The rebuild dropped `why` and token-estimate spend, breaking the old-shape `_event` fixture and two cost-render tests in `tests/test_loop_routing.py` (a file outside task 2's list).
- **Fix:** Moved the fixture to the new producer contract (confidences, tie-break, reported `decision_cost`) and re-aimed the two tests at confidence cells plus reported-spend totals.
- **Files modified:** tests/test_loop_routing.py
- **Verification:** Full 4-file plan suite green (233 passed)
- **Committed in:** 35c7017 (part of task commit)

**2. [Rule 2 - Missing Critical] Same-model picks skip effort validation in decide()**
- **Found during:** Task 1 (passthrough validation)
- **Issue:** Unconditional `validate_routed_effort` in `decide()` would hold same-model no-op picks with unsupported passthrough levels, regressing the locked "validates on the switch path only" behavior into holds instead of no-op lines.
- **Fix:** Guarded both `validate_routed_effort` call sites with `model_id != current_model`.
- **Files modified:** strands_code_cli/routing.py, tests/test_routing.py, tests/test_loop_routing.py
- **Verification:** `test_same_model_pick_skips_effort_validation` plus hook/side no-op tests
- **Committed in:** 429c7ff (part of task commit)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical)
**Impact on plan:** Both preserve locked behavior across the reshape. No scope creep.

## Issues Encountered

- A `Bearer test-key` test literal was redacted to `Bearer [REDACTED]` on the write path, failing the auth-header assertion while output redaction made both sides look identical. Fixed by asserting `"Bearer " + "test-key"` (concatenation), matching the existing proxied-host test style. No production impact.
- Near-tie gate tests initially used top-1 probabilities below the default threshold and held instead of substituting; corrected with explicit low-threshold strategies, which also documents that the threshold gates before the tie-break.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 08-02 (effort decision call, fast-path rewrite to call-2-only, both-confidences line fill): `decide()` passthrough sites are marked, `model_confidence`/`effort_confidence`/`tie_break` ride the pick, and the "first advertised level" tests are greppable for replacement.
- Live verification already done: both integration tests pass against real engines (Jev via OpenRouter, tev1:0.8b via local Ollama 0.40.3); uattest r1-r4 updates land in 08-05.
- Calibration debt is explicit: provisional `0.70`/`0.05` defaults await 08-05 probe distributions.

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-12*
