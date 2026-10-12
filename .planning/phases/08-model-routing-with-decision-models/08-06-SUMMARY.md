---
phase: 08-model-routing-with-decision-models
plan: "06"
subsystem: routing
tags: [decision-api, gap-closure, yaml-bool, validation, probe-runner, pytest]

requires:
  - phase: 08-05
    provides: Probe runner with unconditional local-tag resolution (fixed here)
  - phase: 08-01
    provides: Decision core loader and choice validation (hardened here)
provides:
  - YAML-bool-tolerant candidate loader (unquoted on/off levels normalize to strings)
  - Str-guarded choice validation (unhashable answers hold, never raise)
  - Lazy local-tag resolution in the probe runner (cloud-only runs need no daemon)
affects: [model-routing, uattest, calibration]

actuals:
  tokens: 1541
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns: [yaml-bool-fold-mirroring, str-guard-before-membership, lazy-tag-resolution]

key-files:
  created: []
  modified:
    - strands_code_cli/routing.py
    - scripts/route-probe.py
    - tests/test_routing_strategy.py
    - tests/test_routing.py

key-decisions:
  - "Bool fold uses identity checks (is True/False) so int levels still skip"
  - "Lazy-tag check runs under uv run python; bare python3 re-execs and drops the check context"

patterns-established:
  - "Loader folds hand-edit YAML scalars to typed strings at parse time (mirrors _parse_engine)"

requirements-completed:
  - MODEL-03

coverage:
  - id: D1
    description: "Unquoted on/off candidate levels load as usable string-level candidates"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing_strategy.py#TestBoolLevelNormalization"
        status: pass
      - kind: other
        ref: "uv run python -c _parse_candidate levels probe (ok: ['auto', 'off'])"
        status: pass
    human_judgment: false
  - id: D2
    description: "Non-string choice answers hold with None at both membership checks"
    requirement: "MODEL-03"
    verification:
      - kind: unit
        ref: "tests/test_routing.py#TestUnhashableChoiceHolds"
        status: pass
    human_judgment: false
  - id: D3
    description: "Cloud-only probe runs complete without local-tag resolution"
    requirement: "MODEL-03"
    verification:
      - kind: other
        ref: "/tmp/lazy_tag_check.py (raising resolver, exit 0)"
        status: pass
      - kind: other
        ref: "python3 scripts/route-probe.py --dry-run (20 probes, exit 0)"
        status: pass
    human_judgment: false

duration: 4min
completed: 2026-10-12
status: complete
---

# Phase 08 Plan 06: Gap Closure Summary

**GAP-01/02/03 closed: YAML-bool levels normalize in the candidate loader, unhashable choice answers hold instead of raising, and cloud-only probe runs skip local-tag resolution — all pinned by hermetic tests.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-10-12T07:25:28Z
- **Completed:** 2026-10-12T07:28:55Z
- **Tasks:** 3
- **Files modified:** 4
- **Execution mode:** SEQUENTIAL via generic-agent workaround (typed GSD dispatch unavailable in this session)

## Accomplishments

- GAP-01 fixed: `_candidate_skip_reason` accepts bool entries in `levels` and `_parse_candidate` folds them to `on`/`off` strings, so hand-edited strategies and the r2/r3/r4 rig strategies load as usable candidates and validate instead of reporting "no usable candidates".
- GAP-02 fixed: both choice membership checks (`_validate_choice_shape`, `validate_choice_answer`) return None unless `choice` is a str in the table, so list/dict/tuple answers hold per D-08 with no TypeError escaping to direct callers; `_validate_effort_answer` inherits the fix through the shared shape check.
- GAP-03 fixed: `cmd_run` resolves the local tag only on the local-engine path (`LOCAL_MODEL_PIN` recorded for cloud runs, explicit `local_model` still honored everywhere), so `--run openrouter` needs no Ollama daemon; local runs still resolve plus warm exactly as before.

## Task Commits

Each task was committed atomically:

1. **Task 1: Normalize YAML-bool levels in the candidate loader (GAP-01)** - `08d6d4a` (fix)
2. **Task 2: Guard choice validation against unhashable answers (GAP-02)** - `e27b322` (fix)
3. **Task 3: Resolve the probe local tag lazily for cloud-only runs (GAP-03)** - `eb7db12` (fix)

## Files Created/Modified

- `strands_code_cli/routing.py` - Bool-tolerant `_candidate_skip_reason` plus normalizing `_parse_candidate`; str-guarded `_validate_choice_shape` plus `validate_choice_answer`
- `scripts/route-probe.py` - Lazy local-tag resolution in `cmd_run`
- `tests/test_routing_strategy.py` - `TestBoolLevelNormalization` (False→off, True→on, unquoted-YAML loads usable, int still skips)
- `tests/test_routing.py` - `TestUnhashableChoiceHolds` (list/dict/tuple hold on both paths, string control validates)

## Decisions Made

- Bool fold uses `is True`/`is False` identity checks (not truthiness) so an int level like `3` can never be folded — it still skips via the shared gate.
- The lazy-tag scratch check runs under `uv run python` rather than bare `python3`: importing route-probe.py from a bare interpreter triggers its venv re-exec, which re-runs the module as `__main__` with the check script's (empty) argv and exits 2 before the check body runs.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 08 gap closure is complete: GAP-01/02/03 fixed with the full routing suite green (287 passed, 2 deselected) and no regressions.
- Live UAT stays human-verified per 08-VERIFICATION.md: rig r2/r3/r4 plus r1 regression (now unblocked), and the probe live run plus `--compare` on both engines.

---
*Phase: 08-model-routing-with-decision-models*
*Completed: 2026-10-12*
