---
phase: 08-model-routing-with-decision-models
plan: 02
subsystem: routing
tags: [model-routing, ollama, local-engine, cost-visibility, btw-side-channel]

requires:
  - phase: 08-model-routing-with-decision-models
    provides: 08-01 tracer (routing.py decide/registry/OpenRouter engine, pre-turn hook, RoutingState toggle)
  - phase: 05-model-cost-context-commands
    provides: cost_report breakdown plus cost_for/price_for pricing used by the Routing section
  - phase: 07-subagents-btw-side-channel
    provides: _btw_context_for build closure plus BtwContext spawn/kwargs replay the side hook extends
provides:
  - Local Ollama decision engine second in the chain with per-primary selection and offline local-or-hold
  - EngineResult text-plus-usage seam with decide returning pick/engine/usage
  - Session routing_events plus /cost Routing section with decision spend folded into totals
  - Side-ask spawn-time routing through the shared strategy, side-flagged, one decision per spawn
affects: [08-03-setup, cost-visibility, btw-side-channel]

actuals:
  tokens: 18542
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns: [engine-result-text-plus-usage, per-primary-chain-selection, routing-event-accounting]

key-files:
  created: []
  modified:
    - strands_code_cli/routing.py
    - strands_code_cli/loop.py
    - strands_code_cli/router.py
    - strands_code_cli/cost_context.py
    - tests/test_routing.py
    - tests/test_loop_routing.py

key-decisions:
  - "Held events record the serving model with empty effort/why; zero-usage decisions print no cost part and add no provenance"
  - "Routing events carry a decision_model id (beyond the item-3 key list) so /cost prices each decision call"
  - "Side holds append held side-flagged events with no transcript note, matching the every-decided-ask rule"
  - "YAML 1.1 on/off bools map to openrouter/off at load so unquoted primary off cannot fail open"
  - "Side spawns refresh the replayed model to the live parent model only on the routing-attempted path"

patterns-established:
  - "EngineResult: every engine try returns text plus input/output token counts, zeros when absent"
  - "Routing events: plain-dict per-ask records (ask, side, model, effort, why, engine, tokens, held, decision_model) owned by the loop and rendered by cost_report"

requirements-completed: [MODEL-03]

coverage:
  - id: D1
    description: "Local Ollama engine second in the chain with per-primary selection and offline local-or-hold"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestLocalEngine"
        status: pass
    human_judgment: false
  - id: D2
    description: "/cost Routing section with decision spend folded into totals plus quiet suppression"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop_routing.py#TestCostRouting"
        status: pass
    human_judgment: false
  - id: D3
    description: "Side-ask spawn-time routing through the shared strategy, side-flagged, one decision per spawn"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop_routing.py#TestSideRouting"
        status: pass
    human_judgment: false
  - id: D4
    description: "Live routed asks against a real Ollama daemon plus a live routed /btw side ask"
    requirement: "MODEL-03"
    verification: []
    human_judgment: true
    rationale: "No live Ollama daemon in this environment; needs a daemon plus network plus spend, per the plan's manual live check"

duration: 15min
completed: 2026-10-11
status: complete
---

# Phase 08 Plan 02: Local Engine Summary

**Local Ollama engine second in the decision chain with offline local-or-hold, /cost Routing section folding decision-call spend into totals, and /btw side asks routing once per spawn through the shared strategy side-flagged.**

Executed as gsd-executor-08-02 (generic-agent workaround: typed gsd-executor dispatch is unavailable in this runtime).

## Performance

- **Duration:** 15 min
- **Started:** 2026-10-11T04:35:07Z
- **Completed:** 2026-10-11T04:50:00Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Local engine: `decide_via_ollama` posts `{base}/api/chat` non-streaming with a JSON object format over model/effort/why, 5m keep-alive, and a 30s timeout; usage comes from response eval counts and any failure yields text-None.
- Chain selection: `openrouter` tries API then daemon then hold, `local` tries daemon only then hold, `off` yields None at the load layer with zero calls and no hold note; the local link is skipped (not failed) without a configured local model.
- Usage seam: engines return `EngineResult` (text plus token counts) and `decide` returns pick/engine/usage, with OpenRouter usage parsed from `usage` fields and zeros when absent.
- Visibility: `cost_report(routing=[...])` renders a Routing section with one line per ask and folds decision tokens plus cost (priced at each decision model id) into the session totals; `routing=None` output is byte-identical to the pre-change report (golden-locked).
- Wiring: the loop owns a session `routing_events` list, records every decided ask including held ones, and `dispatch` threads it into `/cost`; `quiet` suppresses only the routine Routed line while hold and failure notes always print.
- Side routing: the `_build` closure decides once per spawn side-flagged before `build_btw_agent`, resolving picks through `resolve_model` with the routed effort into the replayed model plus effort; holds and failures keep the parent live model with no note, live runs never re-decide, and the routed line prints as `Routed (btw)`.
- 36 new tests (TestLocalEngine, TestCostRouting, TestSideRouting); full suite green at 1033 passed, 6 deselected, with no live daemon or network use.

## Task Commits

Each task was committed atomically:

1. **Task 1: Local Ollama engine second in the chain with offline local-or-hold behavior** - `9e91899` (feat)
2. **Task 2: /cost routing section plus decision-call spend plus quiet suppression flag** - `3880f6e` (feat)
3. **Task 3: Side-ask routing through the same strategy flagged as side with one decision per spawn** - `6cd3983` (feat)

## Files Created/Modified

- `strands_code_cli/routing.py` (MOD) - `decide_via_ollama`, `EngineResult`, per-primary `_chain_for`, usage-returning `decide`, primary-off load, base-URL scheme validation, `decision_model_for`, side-headed routed line, default `side=False`.
- `strands_code_cli/loop.py` (MOD) - `_record_routing_event`, hook event capture on all four outcomes, session `routing_events` list, dispatch wiring, `_route_side_spawn` plus `_build` spawn-time decision with live-run guard.
- `strands_code_cli/router.py` (MOD) - `dispatch` `routing_events` kwarg plus `_cost_message` forwarding into `cost_report(routing=...)`.
- `strands_code_cli/cost_context.py` (MOD) - `_routing_line` plus `cost_report` optional routing section with decision totals.
- `tests/test_routing.py` (MOD) - TestLocalEngine (18 tests) plus EngineResult/decide-shape updates and an OpenRouter usage test.
- `tests/test_loop_routing.py` (MOD) - TestCostRouting (7 tests), TestSideRouting (8 tests), EngineResult mock updates.

## Decisions Made

- Held events record the serving model with empty effort/why and the `[held]` marker; zero-usage decisions (failed calls, absent usage fields) print bare token counts with no `$0.0000` and contribute no provenance, so failures cannot flip the Prices line.
- Routing events carry a `decision_model` id beyond the resolved-item-3 key list: without it `cost_report` cannot price each decision call at its own decision model id as item 4 requires.
- Side holds append held side-flagged events (transcript stays silent): a side decision call that returned usage spent real tokens, and dropping it would hide spend against the disclosure prohibition.
- YAML 1.1 `on`/`off` bools map to `openrouter`/`off` at the load layer (see deviation 1).
- Side spawns refresh the replayed kwargs model to the live parent model only on the routing-attempted path (strategy plus candidates plus toggle on); routing-off and unconfigured spawns replay exactly as before with no behavior change.
- Interruption reading for the concurrency assumption: no KeyboardInterrupt swallow in the spawn path — during turns SIGINT is captured by the turn handler rather than raised, the decision is one bounded sync call on the pump thread, and kwargs stay untouched until a parsed pick resolves.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Unquoted `primary: off` failed open to openrouter**
- **Found during:** Task 1 (primary-off load test)
- **Issue:** YAML 1.1 parses unquoted `off` as boolean False, so an explicit user `off` hit warn-and-default and routing stayed on — a silent intent violation on an explicit off switch.
- **Fix:** `_parse_engine` maps a boolean primary to `off`/`openrouter` before the string gate, honoring the written intent.
- **Files modified:** strands_code_cli/routing.py, tests/test_routing.py
- **Verification:** `test_primary_off_load_yields_none_with_zero_calls` (unquoted) plus `test_quoted_off_disables_routing` (quoted) both pass.
- **Committed in:** 9e91899 (part of task commit)

**2. [Rule 3 - Blocking] Engine usage seam landed in Task 1 with consequential test/loop updates**
- **Found during:** Task 1 (resolved item 3 requires `decide` to return the usage pair)
- **Issue:** The usage shape (`EngineResult`, 3-tuple `decide`) had to land with the local engine so both engines parse usage where they hold the payload; that forced the `loop.py` unpack plus the `test_loop_routing.py` mock updates in the same commit to keep the tree green.
- **Fix:** Implemented the seam in Task 1 exactly as resolved item 3 specifies; Task 2 consumed it without further shape changes.
- **Files modified:** strands_code_cli/routing.py, strands_code_cli/loop.py, tests/test_routing.py, tests/test_loop_routing.py
- **Verification:** Routing trio green after the commit (82 passed).
- **Committed in:** 9e91899 (part of task commit)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking)
**Impact on plan:** Both auto-fixes required for correctness and a green tree; no scope creep. All flagged edge-probe assumptions carried visibly, never auto-resolved.

## Issues Encountered

- Real `resolve_model` strips the provider prefix (`bedrock/` gone from the resolved id), so the side-routing test asserts the id tail plus a resolve-args spy instead of the verbatim candidate string.
- The execution channel redacts `Bearer <token>` literals in transit, which corrupted one expected header value on write; the test now builds the literal via concatenation (verified byte-level with hexdump).

## Threat Flags

Threat-register mitigations verified in this plan:

- T-08-06 (local base-URL spoofing): http/https scheme allowlist at strategy load with warn-and-default; call-time re-check fails soft; loopback hosts never carry key material while explicitly configured proxied hosts send the harness-style auth header. Locked by the scheme, default-host, and proxied-header tests.
- T-08-07 (prompt injection via candidate metadata): local decisions reuse the same `build_routing_prompt` (ids plus live stats plus tier plus levels only, catalog descriptions excluded) and the same strict exact-id parse; no local-only prompt path exists to drift.
- T-08-08 (hidden decision-call spend): every decided ask — main or side, routed or held — appends a routing event, and `cost_report` renders the Routing section with decision spend folded into totals; TestCostRouting locks event capture plus totals math.
- T-08-SC (package installs): no new dependencies; the local engine uses stdlib urllib against the user daemon.

## Known Stubs

Stub scan over the four touched source files found no new stubs (one `pass #` hit is a pre-existing line outside this plan's hunks). No `.planning/WINDOWS.md` exists and there is nothing to append.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 08-03 can build guided setup plus `/route setup|validate` on the finished chain: engine registry order, event accounting, and side routing are all in place with hermetic coverage.
- Manual live checks (gate verify-work, not this plan): route an ask with the local engine against `ollama serve` and confirm pick plus spend; route a `/btw` question and confirm the side-flagged decision plus parent-model fallback on daemon stop.

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-11*

## Self-Check: PASSED
