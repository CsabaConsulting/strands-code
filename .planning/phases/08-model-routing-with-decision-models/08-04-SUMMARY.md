---
phase: 08-model-routing-with-decision-models
plan: "04"
subsystem: routing
tags: [decision-api, setup, validate, docs, uattest, pytest]

requires:
  - phase: 08-03
    provides: Hardened two-call chain, pause flag, truncation discipline, detail vocabulary
provides:
  - Decisions-catalog fetch, cache, and refresh beside the chat-catalog path
  - Split-catalog guided setup (chat candidates, decisions decider, nimble local default)
  - Validate judging the decider against the cached decisions catalog
  - Decision-API strategy docs with two verbatim-validating examples
  - UAT scenarios r1-r4 for the Decision-API flow (r1 proven green live)
affects: [08-05, model-routing, uattest]

actuals:
  tokens: 17744
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns: [split-catalog-setup, decisions-cache-validate]

key-files:
  created: []
  modified:
    - strands_code_cli/live_pricing.py
    - strands_code_cli/router.py
    - strands_code_cli/routing.py
    - docs/ROUTING.md
    - scripts/uattest/driver.py
    - scripts/uattest/README.md
    - tests/test_live_pricing.py
    - tests/test_routing_strategy.py

key-decisions:
  - "Decisions cache plus refresh wiring landed in task 1 (live_pricing.py is only in task 1's file list) so disk-cache-only validate and live r1 both work"
  - "Decision entries sort by prompt price (input-only billing) and drop the obsolete structured key; chat entries keep their shape untouched"
  - "Empty local-tag input takes nimble (the RESEARCH default); abort stays via ESC/EOF/Ctrl-C at the other prompts"
  - "Rig scenarios advertise levels [auto, off] so routing succeeds on any boot model without reasoning support"
  - "r2 pins tev1:0.8b (actually pulled here); nimble's 9.5GB is not on this machine"

patterns-established:
  - "Decisions disk cache (openrouter-decision-models.json) populated by /cost refresh, read by validate"
  - "Hold-note shape assertion (HOLD_NOTE_RE) for rig retry branches"

requirements-completed:
  - MODEL-03

coverage:
  - id: D1
    description: "Split-catalog guided setup with alias/zero-context filtering and typed fallback"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestRouteSetup"
        status: pass
    human_judgment: false
  - id: D2
    description: "Decisions-catalog fetch, disk cache, and refresh reporting"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_live_pricing.py#TestFetchDecisionModels+TestRefreshCaches"
        status: pass
    human_judgment: false
  - id: D3
    description: "Validate judging the decider against the cached decisions catalog with zero network calls"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestRouteValidate"
        status: pass
    human_judgment: false
  - id: D4
    description: "Docs shipping two example strategies that validate verbatim"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestRouteValidate::test_docs_routing_examples_validate_verbatim"
        status: pass
    human_judgment: false
  - id: D5
    description: "UAT r1 (split-catalog setup plus validate) proven green live"
    requirement: "MODEL-03"
    verification:
      - kind: e2e
        ref: "scripts/uattest/driver.py r1 -> R1 PASS"
        status: pass
    human_judgment: false
  - id: D6
    description: "UAT r2/r3/r4 updated for the Decision-API flow (System One, toggle, side)"
    requirement: "MODEL-03"
    verification: []
    human_judgment: true
    rationale: "Updated but not run live: only r1 is in the plan verify, and r2/r3/r4 need extended live-model time (Bedrock turns, side spawns) beyond this execution"

duration: 17min
completed: 2026-10-12
status: complete
---

# Phase 08 Plan 04: Setup, Validate, Docs, UAT Summary

**Split-catalog guided setup (chat candidates, decisions decider), decisions-catalog validation, Decision-API strategy docs with validating examples, and r1-r4 rig updates with live r1 green.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-10-12T06:08:38Z
- **Completed:** 2026-10-12T06:26:00Z
- **Tasks:** 3
- **Files modified:** 8
- **Execution mode:** SEQUENTIAL via generic-agent workaround (typed GSD dispatch unavailable in this session)

## Accomplishments

- Added `fetch_openrouter_decision_models` hitting the models endpoint with the decisions output-modality filter (public, no key, None on any failure), plus `_store_decisions`, a `decisions` key in `cached_tables`, and refresh coverage — so `/cost refresh` populates the decisions disk cache that offline validate reads.
- Rebuilt setup on split catalogs: `_setup_decision_entries` keeps decisions-modality entries with positive context while dropping tilde aliases, zero-context rows, and unknown shapes (sorted by prompt price, then id); `_setup_pick_decision` offers them via radio-on-tty and validated typed id off-tty with one re-prompt, falling back to typed entry when unreachable with no assumed default; `_setup_local_model` takes `nimble` on empty input.
- Repointed the decider check in `validate_strategy` from the chat disk cache to the decisions-catalog ids, with a fix line naming the decisions listing on mismatch and disk-cache-only reads (zero network calls asserted).
- Rewrote `docs/ROUTING.md` for the Decision-API schema (criteria prose, gate knobs, engine pins, 26-cap, hold/pause notes) with two full examples — multi-candidate OpenRouter and single-candidate local — that validate verbatim under test.
- Updated rig scenarios r1-r4 for the Decision-API flow: split-catalog setup with decisions-radio price proof, System One path with a zero-spend assertion, toggle round-trip with both-confidences lines and hold-note shape checks, side-headed routed line — and ran r1 live green (candidate `nvidia/switchyard`, decider `inception/mercury-decide:free`).
- Extended the suites to 1226 tests green (full repo): fetch seam tests, refresh decisions tests, 7 new setup cases, 4 new validate cases including the docs-verbatim and zero-network tests.

## Task Commits

Each task was committed atomically:

1. **Task 1: Split-catalog setup enumeration for candidates and decider** - `62035a1` (feat)
2. **Task 2: Validate against the decisions catalog plus strategy docs** - `073ca8e` (feat)
3. **Task 3: UAT scenarios r1-r4 for the Decision-API flow** - `3cca0c3` (test)

## Files Created/Modified

- `strands_code_cli/live_pricing.py` - Decisions fetch, shared entry parser, decisions store, refresh plus cached-tables keys
- `strands_code_cli/router.py` - `_setup_decision_entries`, rebuilt `_setup_pick_decision`, nimble-default `_setup_local_model`, split-catalog setup flow
- `strands_code_cli/routing.py` - `_cached_decision_ids` plus repointed decider lines and fixes in `validate_strategy`
- `docs/ROUTING.md` - Decision-API concepts, quick start, two validating examples, new-schema manual edits, hold/pause troubleshooting
- `scripts/uattest/driver.py` - Decisions-catalog `live_decision_id`, r1-r4 scenario updates, routed-line and hold-note helpers
- `scripts/uattest/README.md` - Decision-capable pull and decisions-catalog wording for r2/r3
- `tests/test_live_pricing.py` - Fetch seam tests, decisions refresh tests, dual-fetch fake
- `tests/test_routing_strategy.py` - Decisions fixture plus dual-catalog helper, 7 new setup tests, migrated plus 4 new validate tests

## Decisions Made

- Decisions cache plus refresh wiring landed in task 1: the plan specified only the fetch, but disk-cache-only validate (task 2) and live r1 (`/cost refresh` then validate-known, task 3) both require a populated decisions disk cache, and `live_pricing.py` sits only in task 1's file list.
- Decision entries sort by prompt price (decision calls bill input only) and drop the obsolete `structured` key (`{id, label, sort}`); chat entries keep their shape untouched as the mirror reference.
- Empty local-tag input takes `nimble` (the RESEARCH default tag); abort stays available via ESC/EOF/Ctrl-C at every other prompt, and abort-without-write is pinned at the decider prompt.
- Rig scenarios advertise `levels: [auto, off]` on both candidates: reasoning-free levels validate on any boot model (nova-micro has no reasoning support), keeping the scripted runs deterministic.
- r2 pins `tev1:0.8b` (verified pulled on this machine with a live 08-01 round-trip); `nimble` (9.5GB) is not pulled here.
- Docs examples pin `typesafe/jev-1.13`, re-verified live at implementation time (19 catalog entries, alias plus zero-context rows still present — the setup filters they justify were observed live).
- `cost_context.py` (`refresh_report`) left untouched: it sits in neither task's file list, and the report ignoring the new summary key is incomplete display, not incorrect behavior.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Decisions cache plus refresh wiring beyond the specified fetch**
- **Found during:** Task 1 (decisions fetch) working toward task 2/3 acceptance
- **Issue:** The plan specified only `fetch_openrouter_decision_models`, but task 2 mandates disk-cache-only validate reads and task 3's live r1 asserts validate-known after `/cost refresh` — with no writer for a decisions disk cache, validate would stay permanently unchecked and r1 would fail live.
- **Fix:** Extracted the shared `_models_entries` parser, added `_store_decisions`, a `decisions` key in `cached_tables`, and decisions coverage in `refresh_caches` with summary reporting.
- **Files modified:** strands_code_cli/live_pricing.py, tests/test_live_pricing.py
- **Verification:** Refresh decisions tests plus cached-tables test; live r1 `known in the cached decisions catalog`
- **Committed in:** 62035a1 (part of task commit)

**2. [Rule 3 - Blocking] Plan-mandated contract updates to existing setup/validate tests**
- **Found during:** Tasks 1-2 (split-catalog setup, decisions-catalog validate)
- **Issue:** Existing tests pinned the old contracts byte-identically: TestRouteSetup picked deciders from chat `structured` entries, and TestRouteValidate seeded the chat cache and asserted `known in the cached catalog` lines.
- **Fix:** Moved setup decider picks to the decisions fixture (with alias/zero-context/chat-only exclusion asserts) and migrated all 13 validate seeds to the decisions cache with updated line assertions.
- **Files modified:** tests/test_routing_strategy.py
- **Verification:** Full task files green (111 passed) plus full repo suite green
- **Committed in:** 62035a1, 073ca8e (part of task commits)

**3. [Rule 3 - Blocking] Rig strategies gained advertised levels**
- **Found during:** Task 3 (r2/r3/r4 updates)
- **Issue:** Under the two-call design a picked candidate with no levels holds (`advertises no levels`), so the hand-written r2/r3/r4 strategies as specified could never print a `Routed →` line.
- **Fix:** Added `levels: [auto, off]` to both candidates in all three strategies; reasoning-free levels validate regardless of boot-model thinking support.
- **Files modified:** scripts/uattest/driver.py
- **Verification:** `py_compile` clean; r1 live green (r2/r3/r4 updated, not run)
- **Committed in:** 3cca0c3 (part of task commit)

**4. [Rule 2 - Missing Critical] Rig README updated alongside the driver**
- **Found during:** Task 3 (rig updates)
- **Issue:** The README (outside the plan's file list) prescribed a chat-model pull (`qwen3:1.7b`) and the "cheapest structured id" — following it after the driver update would fail r2 at preflight and mislead r3 setup.
- **Fix:** Updated the r2/r3 lines to the decision-capable pull and decisions-catalog wording.
- **Files modified:** scripts/uattest/README.md
- **Verification:** Wording matches the updated driver behavior
- **Committed in:** 3cca0c3 (part of task commit)

---

**Total deviations:** 4 auto-fixed (2 missing critical, 2 blocking)
**Impact on plan:** All four close gaps the plan's own acceptance criteria require (wired cache, truthful tests, routable rig strategies, truthful rig docs). No scope creep.

## Issues Encountered

- Live decisions catalog re-verified at implementation time (19 entries): `typesafe/jev-1.13` still listed, `~typesafe/jev-latest` alias and zero-context `respan` rows still present — the setup filters dropped exactly those 4 rows live (15 usable), confirming T-08-33 end to end.
- Live r1 picked `nvidia/switchyard` (chat) and `inception/mercury-decide:free` (decisions) — cheapest-first ordering verified against the real catalogs, and the saved strategy carried no key material.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for 08-05 (builds on split-catalog setup, decisions-cache validate, and the rig): probe calibration can enumerate live decision models via `fetch_openrouter_decision_models` plus `_setup_decision_entries`, and the provisional `0.70`/`0.05` defaults (shown in the docs example) await probe distributions.
- r2/r3/r4 are updated but unrun live (only r1 is in the plan verify): they need tmux plus `OPENROUTER_API_KEY` plus the Ollama daemon, and r3/r4 additionally serve turns on Bedrock — run them when live-model time is available.
- `refresh_report` does not yet render the decisions summary key (`cost_context.py` was out of scope for both tasks): a one-line display follow-up if `/cost refresh` should show the decisions count.

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-12*
