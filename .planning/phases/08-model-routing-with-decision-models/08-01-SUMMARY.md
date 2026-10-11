---
phase: 08-model-routing-with-decision-models
plan: 01
subsystem: routing
tags: [model-routing, openrouter, decision-model, thinking-budget, session-toggle]

requires:
  - phase: 05-model-cost-context-commands
    provides: apply_model_action switch machinery, one-model-per-turn and idle-only contracts, price/window almanac
  - phase: 04-plan-act-modes-steering
    provides: ModeState session-sticky holder precedent, reply-only router actions
provides:
  - routing.py decision-call module (strategy, prompt, OpenRouter engine, strict parse, engine chain, effort validation, toggle holder)
  - Pre-turn routing hook reusing apply_model_action with one transcript line per routed ask
  - Routed thinking-level threading through apply_switch with pre-mutation validation
  - Session toggle plus /route on/off/status plus /model warn-and-cancel
affects: [08-02-local-engine, 08-03-setup, cost-visibility, btw-side-channel]

actuals:
  tokens: 20744
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns: [fail-soft-engine-chain, strict-verbatim-pick-parse, switch-first-resolve-guard, session-sticky-holder]

key-files:
  created:
    - strands_code_cli/routing.py
    - tests/test_routing.py
    - tests/test_routing_strategy.py
    - tests/test_loop_routing.py
  modified:
    - strands_code_cli/loop.py
    - strands_code_cli/model_switch.py
    - strands_code_cli/router.py
    - strands_code_cli/skills.py

key-decisions:
  - "Routed effort validates on the switch path only; same-model no-op picks skip validation and effort application"
  - "auto/off efforts pass validation without advertised levels or thinking support (effort no-ops)"
  - "Hold-note engine slot uses resolve for resolve failures and the producing engine for validation rejects"
  - "Bare /route reports status, mirroring bare /mode announce"
  - "Symlinked strategy paths raise in the loader but degrade to routing-off with a transcript note in the loop"
  - "Ctrl-C in the warn radio fails closed to keep-routing"

patterns-established:
  - "Engine registry: module-level ordered chain, one attempt per engine per ask, hold-current on total failure"
  - "Decision prompts carry ask-only truncated text; strict parse gates every switch"

requirements-completed: [MODEL-03]

coverage:
  - id: D1
    description: "Routing module: strategy load/merge, routing prompt, OpenRouter engine, strict pick parse, engine chain"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestRoutingPrompt+TestParsePick+TestEngineChain"
        status: pass
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestStrategyLoad"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pre-turn hook applying picks through apply_model_action with one transcript line; failures hold current byte-identical"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop_routing.py#TestPreTurnHook"
        status: pass
    human_judgment: false
  - id: D3
    description: "Routed thinking-level threading through apply_switch with pre-mutation levels plus reasoning validation"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestRoutedEffort"
        status: pass
      - kind: unit
        ref: "tests/test_loop_routing.py#TestPreTurnHook effort tests"
        status: pass
    human_judgment: false
  - id: D4
    description: "Session routing toggle plus /route on/off/status plus /model warn-and-cancel with manual override supreme"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop_routing.py#TestRoutingToggle"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live routed turn against OpenRouter with a real key and strategy"
    requirement: "MODEL-03"
    verification: []
    human_judgment: true
    rationale: "No live OpenRouter key in this environment; needs a real key plus network plus spend, per the plan's manual live check"

duration: 11min
completed: 2026-10-11
status: complete
---

# Phase 08 Plan 01: MODEL-03 Tracer Summary

**Pre-turn model routing through an OpenRouter decision call with strict-parse hold-current, routed thinking levels, one transcript line per ask, and a session toggle with /model warn-and-cancel.**

Executed as gsd-executor-08-01 (generic-agent workaround: typed gsd-executor dispatch is unavailable in this runtime).

## Performance

- **Duration:** 11 min
- **Started:** 2026-10-11T04:17:08Z
- **Completed:** 2026-10-11T04:28:22Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- New `routing.py`: fail-soft strategy load (repo wins whole-file), ask-only truncated routing prompt, OpenRouter chat-completions engine over stdlib urllib, verbatim strict pick parse, ordered engine registry with hold-current, routed-line and hold-note builders.
- Pre-turn hook in `run_loop` (after dispatch plus plan prefix, before the retry loop) reusing `apply_model_action`, so Phase 5 idle-only plus one-model-per-turn contracts hold; every routed ask prints one `Routed →` line and every failure holds current byte-identical with a hold note.
- Routed thinking levels threaded through `apply_switch`/`apply_model_action` effort kwargs and gated pre-mutation by advertised levels plus `supports_reasoning`; mismatches hold, never coerce.
- Session `RoutingState` toggle defaulting to on when a strategy configures, `/route on|off|status`, `/model` warn-and-cancel (radio on tty, typed confirm off-tty), and loop-side routing-off after a confirmed manual switch.
- 62 Wave 0 tests across the three mandated files; full suite green at 997 passed, 6 deselected.

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer — strategy-configured ask routes pre-turn via OpenRouter decision** - `f7141ae` (feat)
2. **Task 2: Routed thinking-level threading with pre-mutation validation** - `3861b56` (feat)
3. **Task 3: Session routing toggle plus /model warn-and-cancel plus /route** - `837a320` (feat)

## Files Created/Modified

- `strands_code_cli/routing.py` (NEW) - Strategy paths/load/parse, prompt build, OpenRouter engine, strict parse, engine chain plus decide, effort validation, transcript builders, RoutingState, status text, warn predicate.
- `strands_code_cli/loop.py` (MOD) - Pre-turn hook plus holder ownership, dispatch routing kwarg, effort forwarding, warn-path routing-off, hook gating.
- `strands_code_cli/model_switch.py` (MOD) - Keyword-only effort kwarg on apply_switch, forwarded only when set.
- `strands_code_cli/router.py` (MOD) - /route branch, dispatch routing kwarg, /model warn wrap, USAGE_HINT entry.
- `strands_code_cli/skills.py` (MOD) - route in BUILTIN_SLASH_HEADS.
- `tests/test_routing.py` (NEW) - TestRoutingPrompt, TestParsePick, TestEngineChain, TestRoutedEffort.
- `tests/test_routing_strategy.py` (NEW) - TestStrategyLoad.
- `tests/test_loop_routing.py` (NEW) - TestPreTurnHook, TestRoutingToggle.

## Decisions Made

- Routed effort validates on the switch path only: same-model no-op picks skip validation and effort application (effort has no sticky companion to compare, and re-resolving every ask would churn).
- `auto`/`off` efforts pass validation without advertised levels or thinking support, since they are the effort no-ops (harness default / disabled).
- Hold-note engine slot: `resolve` for switch-first resolve failures, the producing engine for validation rejects (engine output rejected, same attribution as parse failure).
- Bare `/route` reports status, mirroring bare `/mode` announce; unknown subcommands (including 08-03 `setup`/`validate`) reply with usage.
- Symlinked strategy paths raise ValueError in the loader (contract preserved and tested) but the loop degrades to routing-off with a transcript note instead of bricking the session.
- Ctrl-C in the warn radio fails closed to keep-routing (idle context has no turn cancel handler to serve a re-raise).
- The `quiet` strategy flag suppresses the routed line only; hold notes always print per the disclosure prohibition.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Rich console width wraps long transcript lines under test capture; assertions normalize whitespace before matching wrapped notes. No production impact.
- Task 2 validation correctly rejects the tracer's unresolvable-pick fixture before resolve; the fixture now uses effort `off` so the pick reaches the resolve guard it was built to test.

## Threat Flags

Threat-register mitigations verified in this plan:

- T-08-01 (decision JSON tampering): verbatim candidate-id match plus advertised-levels membership in `parse_pick`; negative tests lock malformed, unknown-id, and wrong-level inputs to hold with no fuzzy fallback.
- T-08-02 (ask disclosure): prompt carries current ask only, truncated to 2000 chars; exclusion of history/tool/file/catalog text asserted.
- T-08-03 (routed switch vs user pin): routed switches run only pre-turn at idle through `apply_model_action`; warn-and-cancel keeps manual override supreme; mid-turn MODEL_REFUSAL untouched.
- T-08-04 (malicious repo strategy): unknown candidate ids fail `resolve_model` before any history mutation; `/route status` names the winning source file.
- T-08-09 (API key handling): key read at call time inside the engine function only, header-only, never persisted or logged; key scan finds no real keys in code or tests.
- T-08-05 (slow decision DoS): 10s timeout, one attempt per engine per ask, no in-ask retry; timeouts hold current.
- T-08-SC (package installs): no new dependencies; engines use stdlib urllib.

## Known Stubs

Stub scan over the five touched source files found no new stubs (two `pass #` hits are pre-existing lines outside this plan's hunks). No `.planning/WINDOWS.md` exists and there is nothing to append.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 08-02 can register the local engine in `_ENGINE_REGISTRY` without touching the hook; effort threading deliberately stays out of the /btw rebuild path until then.
- 08-03 owns `/route setup|validate`, the single-candidate fast path, and `/cost` routing detail.
- Manual live check (gates verify-work, not this plan): configure a strategy with `OPENROUTER_API_KEY` set, ask, and confirm the routed model serves the turn with the matching transcript line.

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-11*

## Self-Check: PASSED
