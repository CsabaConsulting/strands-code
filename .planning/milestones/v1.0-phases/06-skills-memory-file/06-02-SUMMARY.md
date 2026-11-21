---
phase: 06-skills-memory-file
plan: 02
subsystem: memory
tags: [memory-file, conventions, ContextInjector, mtime-reload, curate-mode]

requires:
  - phase: 06-skills-memory-file
    provides: plan 06-01 SkillIndex plus BUILTIN_SLASH_HEADS collision contract
  - phase: 04-plan-act-modes-steering
    provides: ModeState session-sticky holder shape and register_steering_hook idempotency
provides:
  - Dual-file memory load/save/inject spine (STRANDS.md + .agent/MEMORY.md, .agent wins)
  - Per-turn external-edit reload sweep with one transcript note per changed file
  - Session-sticky curate/silent MemoryModeState plus /memory mode verb
  - Memory flush on exit and after /compact and /clear history mutations
affects: [06-03 curate queue plus revise plus init, slash routing, completer]

actuals:
  tokens: 9121
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns: [CLI-owned ContextInjector with mtime-memoized render, loop-owned snapshot with turn-boundary sweep, explicit_save-mirrored flush]

key-files:
  created: [strands_code_cli/memory_file.py, strands_code_cli/memory_modes.py, tests/test_memory_file.py]
  modified: [strands_code_cli/main.py, strands_code_cli/loop.py, strands_code_cli/router.py, strands_code_cli/skills.py]

key-decisions:
  - "Corrupt frontmatter keeps the full body as injected text plus a transcript note (never a crash, never silent)"
  - "Empty dual load renders no injection block (None) instead of an empty system-reminder"
  - "Whole-block truncation at MEMORY_INJECT_CAP with the marker last, so oversized content provably ends with it"
  - "Reload-note filename is the watched path string (STRANDS.md / .agent/MEMORY.md), never file content"
  - "flush_memory sits only on the exit path and the /compact//clear branch, per the plan's explicit scope"

patterns-established:
  - "MemorySnapshot record: injected texts plus mtimes dict plus missing display names"
  - "sweep-then-reload loop boundary: sweep paths, single load_memory, one note per changed path"
  - "_memory_message verb skeleton: mode verb live, every other verb returns _MEMORY_USAGE until 06-03"

requirements-completed: [SKILL-02]

coverage:
  - id: D1
    description: "Dual memory files load with frontmatter stripped, root text before .agent text, and the .agent-wins precedence line in one untrusted-marked system-reminder block"
    requirement: "SKILL-02"
    verification:
      - kind: unit
        ref: "tests/test_memory_file.py#TestMemoryFileContract"
        status: pass
    human_judgment: false
  - id: D2
    description: "Frontmatter keys plus section markers round-trip through atomic save/load; corrupt frontmatter degrades without raising; symlinks refuse; oversized content truncates with the marker; .agent file gets 0o600"
    requirement: "SKILL-02"
    verification:
      - kind: unit
        ref: "tests/test_memory_file.py#TestMemoryFileContract"
        status: pass
    human_judgment: false
  - id: D3
    description: "Injector registration is idempotent per agent; render memoizes on canonical mtimes and re-renders only on change"
    requirement: "SKILL-02"
    verification:
      - kind: unit
        ref: "tests/test_memory_file.py#TestMemoryFileContract#test_register_twice_registers_exactly_once"
        status: pass
    human_judgment: false
  - id: D4
    description: "External edits detected at the turn boundary with exactly one reload note per changed file; first-load banner names both files with mtimes or the /init pointer; flush runs on exit and after history mutations"
    requirement: "SKILL-02"
    verification:
      - kind: unit
        ref: "tests/test_memory_file.py#TestMemoryReload"
        status: pass
    human_judgment: false
  - id: D5
    description: "/memory mode announces and flips the session-sticky curate/silent holder; unknown verbs return usage; silent-note line format pinned"
    requirement: "SKILL-02"
    verification:
      - kind: unit
        ref: "tests/test_memory_file.py#TestMemoryModes"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-10-04
status: complete
---

# Phase 6 Plan 02: Memory Contract Summary

**Dual-file repo memory (STRANDS.md + .agent/MEMORY.md) auto-loads through a CLI-owned userTurn injector with .agent-wins precedence, per-turn external-edit reload, session-sticky curate/silent modes, and flush-on-exit — full suite green at 722 passed.**

Executed as `gsd-executor` under the generic-agent workaround (typed dispatch unavailable this session).

## Performance

- **Duration:** 8 min
- **Started:** 2026-10-04T22:19:17Z
- **Completed:** 2026-10-04T22:27:17Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Dual-file loader plus atomic saver plus mtime-memoized `ContextInjector` plugin, registered once per agent from `build_agent` with explicit `skills=True` / `memory=True` harness seams
- Turn-boundary reload sweep with one transcript note per changed file, first-load banner with mtimes or the `/init` pointer, and `flush_memory` on exit plus after `/compact`/`/clear`
- Session-sticky `MemoryModeState` (curate default) with the `/memory mode [curate|silent]` verb, usage skeleton for the 06-03 curate verbs, and `USAGE_HINT` entry
- 26 hermetic tests (`TestMemoryFileContract`, `TestMemoryReload`, `TestMemoryModes`) — no live model, no network

## Task Commits

Each task was committed atomically:

1. **Task 1: Dual-file loader plus injector plugin plus build_agent registration** - `d419cb0` (feat)
2. **Task 2: Turn-boundary reload sweep plus first-load banner plus flush on exit** - `a618c18` (feat)
3. **Task 3: Session-sticky memory modes plus /memory mode verb** - `a8bbe38` (feat)

Deviation fix: **Shadow memory-named skills under the new /memory builtin** - `2da793a` (fix)

**Plan metadata:** `docs: complete plan` (this SUMMARY)

## Files Created/Modified

- `strands_code_cli/memory_file.py` (NEW) - Paths, frontmatter defaults, scaffold sections, parse/dump, snapshot, load, render, sweep, banner, injector registration
- `strands_code_cli/memory_modes.py` (NEW) - `MemoryModeState` curate/silent holder plus `silent_note` helper
- `tests/test_memory_file.py` (NEW) - Contract, reload, and modes tests with the observed injector import path in the module docstring
- `strands_code_cli/main.py` (MOD) - Explicit `skills`/`memory` harness kwargs plus `register_memory_plugin` call
- `strands_code_cli/loop.py` (MOD) - Loop-owned snapshot, first-load banner, turn-boundary sweep, `flush_memory` plus two call sites
- `strands_code_cli/router.py` (MOD) - `/memory` branch, `_memory_message` skeleton, `memory_mode` kwarg, `USAGE_HINT` entry
- `strands_code_cli/skills.py` (MOD) - `memory` joins `BUILTIN_SLASH_HEADS` (deviation fix)

## Decisions Made

- Corrupt frontmatter keeps the full body as injected text plus a `console.print` transcript note naming the file — satisfies "defaults plus a note, never a crash" with no content loss.
- Empty dual load renders `None` (injector skips) rather than an empty `<system-reminder>` block.
- Truncation applies to the whole rendered block at `MEMORY_INJECT_CAP` with the marker appended last, so the acceptance "oversized content ends with the marker" holds literally.
- `sweep_memory_files` and `memory_banner` take an optional `paths` pair defaulting to the canonical files, keeping tmp-fixture tests hermetic without `chdir`.
- `flush_memory` call sites are exactly the exit path and the `/compact`/`/clear` branch per the plan scope — auto-compact and model-switch `explicit_save` sites untouched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `memory` to BUILTIN_SLASH_HEADS with shadow test**
- **Found during:** Post-task-3 review (cross-plan contract check)
- **Issue:** Plan 06-02 lands the `/memory` builtin branch, and both 06-01-SUMMARY and the `skills.py` docstring record that `/memory` joins `BUILTIN_SLASH_HEADS` when its branch lands — but no 06-02 task listed `skills.py`. Without the entry, a skill named `memory` would not warn as shadowed and would still complete, violating the D-02 collision contract.
- **Fix:** Added `"memory"` to the frozenset, updated the docstring (`/init` still deferred to 06-03), added `test_memory_skill_shadowed_by_memory_builtin` to `tests/test_skills.py`.
- **Files modified:** strands_code_cli/skills.py, tests/test_skills.py
- **Verification:** Full suite green (722 passed, 5 deselected)
- **Committed in:** 2da793a (standalone fix commit; task commits were already sealed)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Recorded-contract fulfillment, no scope creep. No other deviations — plan executed as written.

## Issues Encountered

None — all three tasks verified first-try against their acceptance criteria, and the plan-level gate (`uv run pytest tests/ -q`) stayed green throughout.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Load/save/inject spine is production-ready for plan 06-03: `_memory_message` skeleton, `MemoryModeState`/`silent_note`, and `dump_memory_file` section handling are the exact extension points 06-03 names.
- Note for 06-03: the loop does not yet own a `MemoryModeState` (dispatch uses the throwaway default until the 06-03 review loop consumes the holder) — sequencing, not a gap.
- Note for 06-03: `/init` still needs its `BUILTIN_SLASH_HEADS` entry when its branch lands (docstring records this).

---
*Phase: 06-skills-memory-file*
*Completed: 2026-10-04*
