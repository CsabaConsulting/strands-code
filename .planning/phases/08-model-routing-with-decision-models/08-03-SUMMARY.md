---
phase: 08-model-routing-with-decision-models
plan: "03"
subsystem: routing
tags: [decision-api, preflight, ollama, fault-matrix, pause, truncation, pytest]

requires:
  - phase: 08-02
    provides: Sequential two-call verdict, effort-only fast path, side-ask parity
provides:
  - Local preflight gating (local_engine_ready) with inert-link skip and unready detail
  - Pinned per-code retry matrix with engine-plus-cause details and validation holds
  - Offline pause verdict with turn-scoped same-turn skip and pause notes
  - Serialized-body 64 KiB bound with truncation markers and directives warning
affects: [08-04, 08-05, model-routing, cost-display]

actuals:
  tokens: 19735
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns: [failure-class-error-channel, inert-unready-link, turn-scoped-pause-flag]

key-files:
  created: []
  modified:
    - strands_code_cli/routing.py
    - strands_code_cli/loop.py
    - tests/test_routing.py
    - tests/test_loop_routing.py
    - tests/test_routing_strategy.py

key-decisions:
  - "Unready daemons yield an inert zero-POST link (not a dropped link) so the distinct detail flows through the error channel"
  - "4xx and schema-invalid answers keep falling through; the plan pins retry counts plus details, not chain short-circuit"
  - "Pause fires only when every attempted link fails at connection level; skipped, unready, and errorless links are neutral"
  - "Pause is turn-scoped on RoutingState: pre-turn resumes, both hooks pause and skip with zero POSTs"
  - "Only the ask tightens under the body cap; criteria overshoot still ships and the server judges (413 holds)"

patterns-established:
  - "EngineResult.error failure classes: unready, HTTP <code>, timeout, refused, unreachable, invalid body, invalid table"
  - "Verdict details name engine plus cause; pause details start with 'paused:' and the hooks detect them via is_pause_detail"
  - "TRUNCATION_MARKER rides the verdict detail; hooks render it on routed lines, holds carry it inline"

requirements-completed:
  - MODEL-03

coverage:
  - id: D1
    description: "Local preflight gating with floor/tag checks and unready skip"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestLocalEngine"
        status: pass
    human_judgment: false
  - id: D2
    description: "Per-code retry matrix with engine-plus-cause and validation details"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestEngineChain"
        status: pass
    human_judgment: false
  - id: D3
    description: "Offline pause verdict with turn-scoped same-turn skip"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestEngineChain pause cases + tests/test_loop_routing.py#TestSideRouting pause cases"
        status: pass
    human_judgment: false
  - id: D4
    description: "Hold/pause/failure notes print under quiet while routed lines suppress"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_loop_routing.py#TestPreTurnHook quiet cases"
        status: pass
    human_judgment: false
  - id: D5
    description: "64 KiB body bound with truncation markers plus directives warning"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestBodyBound + tests/test_routing_strategy.py#TestRouteValidate warning cases"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-12
status: complete
---

# Phase 08 Plan 03: Chain-Hardening Summary

**Local preflight gating, pinned per-code retry matrix with engine-plus-cause details, offline pause with turn-scoped skip, 64 KiB body bound with truncation markers, and quiet-proof hold/pause/failure notes.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-10-12T05:39:52Z
- **Completed:** 2026-10-12T06:05:09Z
- **Tasks:** 3
- **Files modified:** 5
- **Execution mode:** SEQUENTIAL via generic-agent workaround (typed GSD dispatch unavailable in this session)

## Accomplishments

- Added `local_engine_ready(base, tag)` probing `GET /api/version` for the 0.35 floor (0.35.1 for `clef*` tags) and `GET /api/tags` for the tag (exact or `:latest`-suffixed), failing closed to False on any transport or parse failure; `_chain_for` consults it and offers an inert zero-POST link with the distinct `local unready (daemon version or tag not ready)` detail when the daemon is not ready.
- Pinned the fault matrix across both transports: 400/401/402/403/404/413 hold with zero retries and `engine code` details; 429/500/502/503/524/529 plus timeouts retry once then fall through, holding with the last engine plus code only when the chain exhausts; schema-invalid and non-JSON bodies hold with zero retries and `engine invalid table/body` validation details.
- Added the offline pause verdict: connection-level failure (`refused`/`unreachable`) on every attempted link pauses with `paused: all engines unreachable (...)` while the current model serves; skipped, unready, and errorless links stay neutral so mixed failures still hold with the informative detail.
- Added the turn-scoped pause flag on `RoutingState`: the pre-turn hook resumes each ask and pauses on a pause verdict, and both hooks skip same-turn decisions with zero POSTs once paused (side spawns record a held `paused` event silently).
- Added the serialized-body bound (`DECISION_BODY_MAX_BYTES = 64 * 1024`) in both transports: over-cap payloads tighten only the ask and flag `TRUNCATION_MARKER` on the verdict detail, rendered on routed lines in both hooks and inline on hold lines; `validate_strategy` warns (never fails) when directives exceed ~4K chars.
- Extended the suites to 268 routing tests green (full repo suite 1211 green): preflight floor/tag/refused cases, per-code POST-count matrices on both transports, pause and quiet-override hook cases, body-bound unit cases, and the directives-warning boundary.

## Task Commits

Each task was committed atomically:

1. **Task 1: Local-engine preflight gating the chain link** - `1f3d9ca` (feat)
2. **Task 2: Retry matrix plus offline pause plus note discipline** - `b574b25` (feat)
3. **Task 3: Serialized-body bound with truncation notes** - `10585ff` (feat)

## Files Created/Modified

- `strands_code_cli/routing.py` - Preflight helper plus chain consult and inert link, failure-class error channel, pause classification, body-fit guard plus marker plumbing, directives warning, pause flag on RoutingState
- `strands_code_cli/loop.py` - Pause resume/set/skip in both hooks, truncation marker on both routed lines
- `tests/test_routing.py` - Preflight-aware URL-seam wrapper, extended TestLocalEngine, fault-matrix TestEngineChain cases, TestBodyBound
- `tests/test_loop_routing.py` - Pause, transport-hold, quiet-override, truncation-marker, and paused-side-spawn cases
- `tests/test_routing_strategy.py` - Directives-length warning plus boundary cases

## Decisions Made

- Unready daemons yield an inert link (offered but zero-POST) rather than a dropped link, so the distinct unready detail flows through the existing error channel with no `_chain_for` signature change; `_ollama_attempt` itself stays attempt-only and ready daemons route normally.
- 4xx and schema-invalid answers keep falling through to the next link (the existing tested contract): the plan pins retry counts plus details, not chain short-circuit, and rewriting the fall-through test would violate the existing contract without an explicit mandate.
- Pause fires only when at least one link reports a connection-level error and no attempted link reports anything else; skipped, unready, and errorless (missing-key) links are neutral, and the pause engine is the last refused link.
- Pause is turn-scoped, not session-sticky: the pre-turn hook resumes every ask (D-08 retries next ask), the side hook skips while paused, and the paused side event prices nothing (`decision_model_for("paused")` is None).
- Only the ask tightens under the body cap: criteria overshoot ships after the ask empties and the server judges, where a real 413 holds with the engine-plus-code detail; the marker appends once per verdict even when both calls shrink.
- `format_hold_line` needed no change: pause, transport-hold, validation, unready, and truncation notes all render through the existing hold shape with their distinct details, which already print under quiet.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Dual-engine test fakes moved to the preflight-aware contract**
- **Found during:** Task 1 (chain consults `local_engine_ready`)
- **Issue:** Every dual-engine `urlopen` fake plus the stub HTTP server only spoke decision POSTs, so preflight GETs 404'd/AttributeError'd and ready-daemon tests skipped the local link (9 failures).
- **Fix:** Added the `_with_preflight` test-seam wrapper serving `/api/version` plus `/api/tags` around the POST fakes (GETs bypass the POST recorders, so exact POST-count assertions stand), and added `do_GET` handlers to the stub server with a preflight-first assertion.
- **Files modified:** tests/test_routing.py
- **Verification:** TestLocalEngine 39 passed plus full routing files green
- **Committed in:** 1f3d9ca (part of task commit)

**2. [Rule 3 - Blocking] Plan-mandated detail-contract updates to existing tests**
- **Found during:** Tasks 1-2 (unready skip plus engine-plus-cause details plus pause)
- **Issue:** The plan revises hold details the old tests pinned byte-identically: retry exhaustion (`openrouter 503`), stale choice and failed effort reads (`openrouter invalid table`), and the both-failing case (pause verdict).
- **Fix:** Re-aimed the four assertions at the mandated details and renamed the both-failing test to `test_offline_dual_strategy_pauses_routing`; the missing-key and decide-level `openrouter failed` byte-identical shapes are preserved via the errorless fallback.
- **Files modified:** tests/test_routing.py
- **Verification:** Full routing files green plus full repo suite green
- **Committed in:** 1f3d9ca, b574b25 (part of task commits)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both keep the suite truthful across the mandated contract changes. No scope creep.

## Issues Encountered

- The directives-warning test initially asserted a bare `"warning" in text`, which false-hit on the tmp path: pytest embeds the test name (`test_directives_warning_boundary`) in the path and the report echoes the source path. Fixed by matching the full warning line content (`warning: directives exceed ~4K chars`).
- The `clef` preflight test initially failed because the shared fake only pulled `nimble`: the tag-membership check correctly rejected `clef`. Fixed by pulling `clef`/`clef-flash` in that fake, which also documents that floor and tag checks compose.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 08-04 (builds on the hardened chain, pause flag, and truncation discipline): `decide()` verdicts carry pause/unready/truncation details the setup/docs work can quote, and the `paused`/`unready`/`invalid` detail vocabulary is stable.
- Calibration debt carries forward unchanged: provisional `0.70`/`0.05` defaults still await 08-05 probe distributions; fault-injection coverage here is hermetic (stubbed `urlopen`), with live-engine behavior unchanged from the 08-01 verification.
- No live verification in this plan beyond the hermetic suite: preflight, fault, pause, and truncation paths are all covered by stubbed tests; the stub-server test pins the real-HTTP preflight order (`/api/version` then `/api/tags`).

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-12*
