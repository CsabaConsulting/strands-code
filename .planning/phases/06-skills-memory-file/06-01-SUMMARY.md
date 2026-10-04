---
phase: 06-skills-memory-file
plan: 01
subsystem: skills
tags: [skills, slash-commands, autocomplete, prompt_toolkit, AgentSkills]

requires:
  - phase: 05-model-cost-context-commands
    provides: reply-only router dispatch tri-state plus transcript-first loop UX
provides:
  - Local skill loading from ./.agent/skills via the SDK Skill.from_directory seam
  - Dynamic /<skill> slash invocation with trailing-text input
  - Builtin-wins collision contract with visible shadow warnings (D-02)
  - /skills list/show/remove management command
  - Fuzzy slash completer completing the full local:<name> form
affects: [06-02 memory file, 06-03 init scaffolding, slash routing, completer]

actuals:
  tokens: 8804
  tasks: 3
  commits: 5

tech-stack:
  added: []
  patterns: [load-once index with derived warnings, router-composes-loop-runs skill turns, DynamicCompleter refreshable word callable]

key-files:
  created: [strands_code_cli/skills.py, strands_code_cli/completer.py, tests/test_skills.py]
  modified: [strands_code_cli/router.py, strands_code_cli/loop.py]

key-decisions:
  - "BUILTIN_SLASH_HEADS single-sourced in skills.py for shadow detection and completer words; /memory and /init join it in plans 06-02/06-03"
  - "Skill warnings derived from current entries (not stored), so remove keeps them consistent"
  - "SkillIndex.remove method delegates to the module-level remove_skill guard helper and evicts the cache entry"
  - "/skills list is a single bare-name-sorted list with shadowed entries tagged inline"
  - "Loop passes its SkillIndex into dispatch (plan gap, Rule 2) so /<skill> and /skills work live"

patterns-established:
  - "SkillEntry record: SDK-loaded fields plus CLI namespace state (source, namespaced, shadowed)"
  - "Exact-match-only skill resolution: bare or local:<name>, unknown names fall through to the Unknown-command reply"
  - "Completer words as a zero-arg (bare, display) callable rebuilt per invocation"

requirements-completed: [SKILL-01]

coverage:
  - id: D1
    description: "SkillIndex loads local skills; missing dir yields empty index; symlinked root raises; malformed skills warn-and-skip; collisions produce exact shadow warnings"
    requirement: "SKILL-01"
    verification:
      - kind: unit
        ref: "tests/test_skills.py#TestSkillIndex"
        status: pass
    human_judgment: false
  - id: D2
    description: "/<skill> routes (\"agent\", composed) with skill instructions plus trailing text; builtins win collisions; unknown slashes keep the Unknown-command reply"
    requirement: "SKILL-01"
    verification:
      - kind: unit
        ref: "tests/test_skills.py#TestSkillRouting"
        status: pass
    human_judgment: false
  - id: D3
    description: "/skills lists sorted entries with shadowed tags, shows full records with verbatim allowed-tools, and removes only plain dirs inside ./.agent/skills"
    requirement: "SKILL-01"
    verification:
      - kind: unit
        ref: "tests/test_skills.py#TestSkillsCommand"
        status: pass
    human_judgment: false
  - id: D4
    description: "Fuzzy completer completes local:<name> on bare prefixes, omits shadowed/removed skills, and the loop wires it plus prints shadow warnings once at startup"
    requirement: "SKILL-01"
    verification:
      - kind: unit
        ref: "tests/test_skills.py#TestSkillCompleter"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-10-04
status: complete
---

# Phase 6 Plan 01: Local skills load, invoke, and discovery Summary

**Local AgentSkills.io skills load from ./.agent/skills as /<name> slashes with builtin-wins shadowing, /skills management, and fuzzy namespaced autocomplete**

## Performance

- **Duration:** 6 min
- **Started:** 2026-10-04T22:09:10Z
- **Completed:** 2026-10-04T22:14:51Z
- **Tasks:** 3 (+1 proof test)
- **Files modified:** 5
- **Executor:** generic-agent workaround for gsd-executor (typed dispatch unavailable this session)

## Accomplishments

- SkillIndex loads local skills through `Skill.from_directory` with the D-02 namespace contract: bare names stay colon-free, `local:<name>` mapping lives in the index only
- Dynamic `/<skill>` slash routes `("agent", composed)` with the untrusted-marker template; shadowed skills are unreachable even via the namespaced form
- `/skills` lists sorted entries with shadowed tags, shows full records, and removes via a traversal/symlink-guarded helper
- Fuzzy slash completer matches bare names and completes `local:<name>`; loop owns one SkillIndex, wires the completer, prints shadow warnings once, and passes the index to dispatch
- Full suite green: 695 passed, 5 deselected (27 new skill tests, zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer — SkillIndex load plus dynamic /skill slash end to end** - `6515ccc` (feat)
2. **Task 2: /skills list, show, and traversal-guarded remove** - `b547f20` (feat)
3. **Task 3: Fuzzy skill completer plus loop wiring and startup warnings** - `91163e3` (feat)
4. **Proof test: loop startup prints shadow warnings once** - `2e55ac2` (test)

**Plan metadata:** `docs: complete plan` (this SUMMARY commit)

## Files Created/Modified

- `strands_code_cli/skills.py` - SkillEntry record, SkillIndex (load/resolve/list/remove), shadow warnings, traversal-guarded remove_skill
- `strands_code_cli/completer.py` - SlashCompleter plus build_completer DynamicCompleter/FuzzyCompleter factory
- `strands_code_cli/router.py` - dispatch skills kwarg, dynamic /skill branch, /skills branch with _skills_message plus _SKILLS_USAGE, USAGE_HINT extension
- `strands_code_cli/loop.py` - Loop-owned SkillIndex, PromptSession completer wiring, startup shadow-warning print, skills passed to dispatch
- `tests/test_skills.py` - TestSkillIndex, TestSkillRouting, TestSkillsCommand, TestSkillCompleter; module docstring records the SDK import path

## Decisions Made

- BUILTIN_SLASH_HEADS single-sourced in skills.py for both shadow detection and completer words; `/memory` and `/init` deliberately excluded until plans 06-02/06-03 add those branches (listing them now would shadow currently-invocable skills with no builtin to win)
- Warnings derived from current entries via a property instead of stored at load, so `/skills remove` of a shadowed skill keeps warnings consistent for free
- `SkillIndex.remove` resolves, deletes through the module-level `remove_skill` guard, and evicts the cache entry so removed skills stop completing without restart
- `/skills` bare list renders one bare-name-sorted list with shadowed entries tagged inline (satisfies both the sorted-output and shadowed-tag requirements; no separate trailing group)
- Refusal reply for symlinked/outside-root removal (`Refused to remove skill ...`) and the show record layout were plan-unspecified; chose fail-closed wording consistent with existing reply style

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Loop passes its SkillIndex into dispatch**

- **Found during:** Task 3 (Fuzzy skill completer plus loop wiring)
- **Issue:** Task 3 wired the completer and startup warnings but never passed the loop-owned SkillIndex to `dispatch`, which would leave `/<skill>` invocation and `/skills` reporting "No skills loaded" in the live loop — the whole plan's router work unreachable in production
- **Fix:** Added `skills=skills` to the `dispatch` call in `run_loop` (one kwarg; default `None` keeps all other callers green)
- **Files modified:** strands_code_cli/loop.py
- **Verification:** Full suite green (695 passed); live path now matches the dispatch-level tests
- **Committed in:** 91163e3 (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** The fix is required for basic operation of the shipped feature; no scope creep.

## Issues Encountered

- Self-authored startup test first used abstract `prompt_toolkit.history.History`; switched to `InMemoryHistory` — one-line fix, suite green.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- SKILL-01 complete: skills load, invoke, collide safely, and are discoverable
- Ready for 06-02 (memory file): `BUILTIN_SLASH_HEADS` is the documented extension point for `/memory`, and `/init` follows in 06-03
- No blockers or concerns

---
*Phase: 06-skills-memory-file*
*Completed: 2026-10-04*
