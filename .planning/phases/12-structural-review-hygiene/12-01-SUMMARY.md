---
phase: 12-structural-review-hygiene
plan: "01"
subsystem: infra
tags: [radon, xenon, ruff, import-linter, complexity, hygiene, tracer]

requires:
  - phase: 11-codeact-action-interface
    provides: green 1553-test suite as the guardrail baseline
provides:
  - Dev tooling (radon/xenon/ruff/import-linter) with fork-scoped gate configs
  - D-15 dead-code deletion with no dangling references
  - Ruff-clean, ruff-formatted fork-owned tree
  - docs/STRUCTURE.md measurement report citing breakup numbers
affects: [12-02, 12-03, 12-05, structural-review, repackaging]

actuals:
  tokens: 112400
  tasks: 3
  commits: 4

tech-stack:
  added: [radon 6.0.1, xenon 0.9.3, ruff 0.17.1, import-linter 2.15]
  patterns: [fork-path-scoped gates, composition-root import contract]

key-files:
  created:
    - docs/STRUCTURE.md
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Composition-root import-linter contract (KEPT); D-15 knowledge contract inexpressible, CLEANUP-01 stays on absence+grep gate"
  - "Absolute-only xenon gating (--max-absolute C) per Q5 resolution"
  - "A5 closed: no module-path-derived secret names on fork paths"

patterns-established:
  - "Gate configs live in pyproject.toml with [tool.ruff] force-exclude + [tool.importlinter] contracts"
  - "D-04 reports follow the ROUTING.md shape: title + scope paragraph, Method/Numbers/Contracts/Breakup sections"

requirements-completed:
  - STRUCT-01
  - CLEANUP-01

coverage:
  - id: D1
    description: "Dev tooling installed and configured for fork-owned paths only"
    requirement: "STRUCT-01"
    verification:
      - kind: other
        ref: "uv run ruff check strands_code_cli tests scripts (exit 0)"
        status: pass
      - kind: other
        ref: "uv.lock contains radon/xenon/ruff/import-linter entries"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-15 dead code deleted with no dangling references"
    requirement: "CLEANUP-01"
    verification:
      - kind: other
        ref: "test ! -e examples/pdf_to_okf_bundle && test ! -e strands_code_agent/knowledge"
        status: pass
      - kind: other
        ref: "anchored dangling-reference grep over fork-owned Python files (no match)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Fork-owned tree ruff-clean and ruff-formatted, upstream byte-identical"
    requirement: "STRUCT-01"
    verification:
      - kind: other
        ref: "uv run ruff check + ruff format --check (exit 0, 77 files)"
        status: pass
      - kind: other
        ref: "git diff --quiet -- strands_code_agent/ (empty)"
        status: pass
    human_judgment: false
  - id: D4
    description: "docs/STRUCTURE.md records complexity/coupling numbers with cited breakup rationale"
    requirement: "STRUCT-01"
    verification:
      - kind: other
        ref: "grep required sections and strings (4 ## sections, STRUCT-01, xenon)"
        status: pass
    human_judgment: true
    rationale: "Section presence is automated but number transcription accuracy was established by executor cross-check (radon vs xenon), not by a pinned test — a reviewer citing the breakup should confirm the figures"
  - id: D5
    description: "Full test suite passes after cleanup, format, and measurement"
    requirement: "STRUCT-01"
    verification:
      - kind: other
        ref: "uv run pytest tests/ -q (1532 passed, 11 deselected, no failed/error)"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-10-16
status: complete
---

# Phase 12 Plan 01: Hygiene Spine Summary

**Tracer-first hygiene spine: radon/xenon/ruff/import-linter tooling with fork-scoped configs, D-15 dead-code deletion, whole-tree format pass, and the committed STRUCTURE.md measurement report — suite green throughout.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-10-16T06:41:49Z
- **Completed:** 2026-10-16T06:50:03Z
- **Tasks:** 3
- **Files modified:** 75 (+ this summary)

## Accomplishments

- Dev tooling installed (radon 6.0.1, xenon 0.9.3, ruff 0.17.1, import-linter 2.15) with `[tool.ruff]` (py310, force-exclude, F+E+I, E501 ignored, first-party roots) and `[tool.importlinter]` (composition-root contract, KEPT) in pyproject.toml
- D-15 targets deleted (`examples/pdf_to_okf_bundle/`, `strands_code_agent/knowledge/`, `tests/test_okf_bundle.py`) with the anchored dangling-reference grep empty; `tests/test_search.py` kept (zero knowledge references, TOOL-04 suite)
- Whole-tree format + autofix: 61 ruff errors fixed (55 automatic, 6 by hand), 62 files reformatted, upstream package byte-identical
- Committed `docs/STRUCTURE.md` (D-04): 2706 blocks, avg A (3.87), 17 red blocks worse than C, composition-root contract status, breakup rationale citing loop/routing/dispatch boundaries
- Full suite green after every task: 1532 passed, 11 deselected, no failed/error
- Research assumption A5 closed: no module-path-derived secret names — all `os.environ` reads on fork paths use string literals, and the single dynamic lookup iterates the literal tuple `("AWS_REGION", "AWS_DEFAULT_REGION")` (live_pricing.py:346-347)

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer tooling + dead-code deletion** - `944262e` (chore)
2. **Task 2: Whole-tree ruff format + autofix** - `3c6ecfe` (chore)
3. **Task 3: Radon measurement + D-04 report** - `18ab2e8` (chore)

**Plan metadata:** `docs(12-01)` summary commit (this file)

## Files Created/Modified

- `docs/STRUCTURE.md` - D-04 measurement report (Method, Numbers, Contracts, Breakup rationale)
- `pyproject.toml` - Four dev deps (lower-bound pins) + `[tool.ruff]`, `[tool.ruff.lint]`, `[tool.ruff.lint.isort]`, `[tool.importlinter]` tables
- `uv.lock` - Resolved pins for the new dev deps + transitives (mando, colorama, grimp)
- 64 fork-owned `.py` files - Format + autofix pass (strands_code_cli, tests, scripts)
- Deleted: `examples/pdf_to_okf_bundle/` (2 files), `strands_code_agent/knowledge/` (5 files), `tests/test_okf_bundle.py`

## Decisions Made

- Composition-root import-linter contract ("feature modules never import `strands_code_cli.main`", ignoring the `__init__` re-export) instead of a D-15 knowledge contract: import-linter rejects subpackages of external packages and the module no longer exists, so the D-15 intent stays guarded by the path-absence + anchored-grep CI step (12-05 wires it)
- Xenon gating is absolute-only (`--max-absolute C`) per the RESEARCH Q5 resolution; module/average grades not adopted
- Rule-scope `ignore = ["E501"]` adopted per CF-04 (formatter owns line length); documented as configuration, not a waiver

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Initial import-linter contract crashed the tool, reworked to composition-root contract**
- **Found during:** Task 3 (Radon measurement plus committed D-04 report)
- **Issue:** First draft (forbid `strands_code_agent.knowledge` from CLI) failed twice: lint-imports demands `include_external_packages` for external forbidden modules, then rejects them anyway ("subpackages of external packages are not valid")
- **Fix:** Replaced with the composition-root contract over internal modules only; verified KEPT (28 files, 74 dependencies, exit 0)
- **Files modified:** pyproject.toml
- **Verification:** `uv run lint-imports` exits 0 with "Contracts: 1 kept, 0 broken"
- **Committed in:** 18ab2e8 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Config-only fix required for the "installed and configured" truth; no scope change. The D-15 guard moves to the CI absence+grep step as documented in the report.

## Issues Encountered

None. Xenon exits 1 at baseline (17 blocks worse than C) — expected per CF-03; enforcement flips to blocking after the breakup in plan 12-05.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for 12-02 (breakup, part 1): tooling proven end to end, tree formatted so move diffs stay pure, STRUCTURE.md numbers cite the loop/routing/dispatch boundaries, and the suite is green at 1532 passed.

---
*Phase: 12-structural-review-hygiene*
*Completed: 2026-10-16*
