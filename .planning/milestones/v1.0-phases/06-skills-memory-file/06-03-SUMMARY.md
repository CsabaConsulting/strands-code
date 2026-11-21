---
phase: 06-skills-memory-file
plan: 03
subsystem: memory
tags: [curate-queue, memory-review, revise-rounds, init-scan, merge-scan, silent-mode]

requires:
  - phase: 06-skills-memory-file
    provides: plan 06-02 dual-file load/save/inject spine plus MemoryModeState and _memory_message skeleton
  - phase: 04-plan-act-modes-steering
    provides: D-04 freeform revise-round grammar reused by NL revise
  - phase: 03-permissions-gate
    provides: single-HITL ask spine vocabulary and radio_choice dialog reused by curate prompts
provides:
  - CurateQueue plus Proposal plus promotion sweep feeding the /memory review loop
  - NL revise rounds with quoted review and accept/revert/iterate
  - /init repo scan with draft-through-curate and merge-never-clobber re-runs
  - Source-aware approve routing (init vs curate writers) plus root pointer block
affects: [slash routing, completer, future memory consumers, UAT prompt shape]

actuals:
  tokens: 25157
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns: [consumer-after-turn with armed holders, snapshot-as-read-base for init apply, budgeted pure scan with forbidden-path guards]

key-files:
  created: [tests/test_memory_curate.py]
  modified: [strands_code_cli/memory_modes.py, strands_code_cli/memory_file.py, strands_code_cli/router.py, strands_code_cli/loop.py, strands_code_cli/skills.py]

key-decisions:
  - "ReviseState/InitState mirror ModeState: session-sticky, in-memory, never survive the session"
  - "consume_revise_turn returns Optional[str]: None means iterate re-armed and the loop re-invokes"
  - "One revise turn per boundary: a wired revise arm ends the review, rest stay pending"
  - "Iterate with an empty instruction fails closed to revert (never re-arms a broken prompt)"
  - "Section-span primitives canonicalized in memory_file.py; router delegates (no triplication)"
  - "Init fence label is ```proposed: <Section>; consume queues stale-labeled blocks only"
  - "Root pointer lives under ## Memory with the pointer sentence first; hand-written lines preserved"

patterns-established:
  - "Armed-holder post-turn consumers: router returns (agent, text) with armed state, loop drains after the turn, never the router"
  - "Drain loops re-invoke through _invoke_agent with plan prefix plus metrics; failed follow-ups disarm with a note"
  - "Ctrl-C during a memory round disarms before propagating, so interrupts leave files byte-identical"

requirements-completed: [SKILL-02]

coverage:
  - id: D1
    description: "/memory review loop: promotion sweep caps at 3 per sweep, list/approve/deny verbs act immediately, turn-boundary review prompts in curate mode and auto-applies with silent lines in silent mode, denied ids never re-queue"
    requirement: "SKILL-02"
    verification:
      - kind: unit
        ref: "tests/test_memory_curate.py#TestCurateLoop"
        status: pass
    human_judgment: false
  - id: D2
    description: "NL revise rounds: /memory revise returns an agent turn with the quoted template, consume quotes the revised block plus summary, accept applies verbatim with marker refresh, revert and missing fences leave files byte-identical, iterate re-arms"
    requirement: "SKILL-02"
    verification:
      - kind: unit
        ref: "tests/test_memory_curate.py#TestReviseRounds"
        status: pass
    human_judgment: false
  - id: D3
    description: "/init repo scan plus draft-through-curate: shallow/deep scans stay capped and skip sessions plus key-shaped files, diff flags missing/unmarked/stale sections only, labeled blocks queue as init proposals, approving writes full sections to .agent plus thin pointer lines to root, re-runs never clobber approved memory"
    requirement: "SKILL-02"
    verification:
      - kind: unit
        ref: "tests/test_memory_curate.py#TestInitScan"
        status: pass
    human_judgment: false
  - id: D4
    description: "Arrow-key dialog rendering of the curate and revise prompts on a real tty"
    requirement: "SKILL-02"
    verification: []
    human_judgment: true
    rationale: "Tests exercise the typed (non-tty) prompt path plus the shared radio_choice control; the tty branch wiring is untested hermetically and needs one live-terminal pass"

duration: 18min
completed: 2026-10-04
status: complete
---

# Phase 6 Plan 03: Curation Surface Summary

**/memory approve/deny review loop fed by promotion polls, NL revise rounds with quoted accept/revert/iterate, and /init repo-scan drafting through curate approval with merge-never-clobber — full suite green at 775 passed.**

Executed as `gsd-executor` under the generic-agent workaround (typed dispatch unavailable this session).

## Performance

- **Duration:** 18 min
- **Started:** 2026-10-04T22:56:26Z
- **Completed:** 2026-10-04T23:14:51Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments

- Curate queue (`Proposal`, `CurateQueue`, `sweep_promotions` capped at 3) with `/memory list/approve/deny` verbs and a turn-boundary review runner that prompts per proposal in curate mode or auto-applies with silent lines in silent mode
- NL revise rounds: `/memory revise` arms a session-sticky round and starts its agent turn; the post-turn consumer quotes the revised block plus summary, then accept applies verbatim with marker refresh, revert keeps bytes identical, iterate re-arms with the new instruction
- `/init` repo scan (shallow layout/README/manifests/docs/policy; deep adds source imports-plus-docstrings, dependency names, tests plus runner config) under file/byte caps that never read sessions or key-shaped files, with stale-only diffing and labeled-block drafting through curate approval
- Merge-never-clobber apply: init approvals replace-or-append full sections with fresh markers and upsert thin summary lines under the root pointer block; re-runs only draft missing or stale sections

## Task Commits

Each task was committed atomically:

1. **Task 1: Curate queue plus promotion sweep plus /memory review verbs** - `817e37d` (feat)
2. **Task 2: NL revise rounds with quoted review and accept-revert-iterate** - `864fc02` (feat)
3. **Task 3: /init repo scan plus draft-through-curate plus merge-never-clobber** - `2f15ec1` (feat)

**Plan metadata:** `docs: complete plan` (this SUMMARY)

## Files Created/Modified

- `tests/test_memory_curate.py` (NEW) - `TestCurateLoop`, `TestReviseRounds`, `TestInitScan`: 52 hermetic tests, canned text only, no live model, no network
- `strands_code_cli/memory_modes.py` (MOD) - `Proposal`, `CurateQueue` plus `sweep_promotions`, `ReviseState`, `InitState`, prompt builders, sweep/marker constants
- `strands_code_cli/memory_file.py` (MOD) - `scan_repo` plus `ScanReport`, `diff_sections`, `apply_init_proposal`, shared `section_span`/`fresh_marker`/`UPDATED_MARKER_RE`, root pointer constants
- `strands_code_cli/router.py` (MOD) - `/memory` list/approve/deny verbs, `/memory revise` and `/init` agent-turn branches, `apply_approved_proposal` source routing, `curate`/`revise`/`init` kwargs, `USAGE_HINT` entries
- `strands_code_cli/loop.py` (MOD) - `review_memory_queue`, `consume_revise_turn` plus iterate drain, `consume_init_turn`, loop-owned holders, boundary sweep/review wiring, disarm safety nets
- `strands_code_cli/skills.py` (MOD) - `init` joins `BUILTIN_SLASH_HEADS` (deviation fix)
- `tests/test_memory_file.py` (MOD) - Usage/hint expectations updated for the extended `/memory` verbs (plan-mandated)
- `tests/test_skills.py` (MOD) - `/init` shadow test (deviation fix)
- `tests/test_plan_cancel.py`, `tests/test_model_switch.py` (MOD) - Hermetic fact-dir pins for scripted loop runs (deviation fix)

## Decisions Made

- `ReviseState`/`InitState` mirror `ModeState`: session-sticky, in-memory, armed by dispatch and consumed by the loop after the turn — the router never prompts and never writes.
- `consume_revise_turn` returns `Optional[str]`: a reply string for terminal paths, `None` when iterate re-arms so the drain loop re-invokes with the new instruction.
- One revise turn per boundary: a wired revise arm ends the review so only one template runs; remaining proposals stay pending for the next turn.
- Iterate with an empty instruction fails closed to revert rather than re-arming a broken prompt.
- Section-span primitives live canonically in `memory_file.py` (`section_span`, `fresh_marker`, `UPDATED_MARKER_RE`); the router delegates instead of triplicating the heading/marker logic.
- `apply_init_proposal(proposal, snapshot)` uses the snapshot as its read base with frontmatter round-tripped from disk; callers pass a fresh snapshot (the loop sweeps at the boundary).
- Init fence label is ` ```proposed: <Section> `; the consumer queues stale-labeled blocks only (first block wins on repeats), per the merge-scan truth that only missing or stale sections become proposals.
- Root pointer lives under `## Memory` with the pointer sentence first and one `- Section: first line` summary per section (200-char cap); unrecognized hand-written lines in the span are preserved, never dropped.
- Scan parsing is regex/AST stdlib-only (3.10-safe, no tomllib); outline hygiene caps each included file at 4000 chars and each listing at 200 entries with honest truncation notes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added `init` to BUILTIN_SLASH_HEADS with shadow test**
- **Found during:** Task 3 (`/init` branch landing)
- **Issue:** The `/init` builtin branch landed but no task listed `skills.py`, so an `init`-named skill would not warn as shadowed — the same D-02 gap 06-02 fixed for `/memory`, and its SUMMARY explicitly deferred `/init` to 06-03.
- **Fix:** Added `"init"` to the frozenset, dropped the landed-deferral docstring note, added `test_init_skill_shadowed_by_init_builtin`.
- **Files modified:** strands_code_cli/skills.py, tests/test_skills.py
- **Verification:** Full suite green (775 passed, 5 deselected)
- **Committed in:** 2f15ec1 (Task 3 commit)

**2. [Rule 2 - Missing Critical] Routed init approvals through apply_init_proposal**
- **Found during:** Task 3 (wiring the D-10 split)
- **Issue:** The plan requires approving an init proposal to write the full section plus upsert the root pointer, but the task-1 approve verb routes every source through the append writer — init approvals would have duplicated stale sections and never touched root.
- **Fix:** Added `apply_approved_proposal` source routing (init sources → `apply_init_proposal` with a fresh snapshot; others → append writer) and pointed the approve verb plus boundary review at it, with a routing test through real dispatch.
- **Files modified:** strands_code_cli/router.py, strands_code_cli/loop.py, tests/test_memory_curate.py
- **Verification:** `test_approve_routes_init_proposal_to_init_writer` plus full suite green
- **Committed in:** 2f15ec1 (Task 3 commit)

**3. [Rule 1 - Bug] Made section spans marker-aware**
- **Found during:** Task 2 (accept-path test failure: a marker above the next heading was attributed to the previous section's span)
- **Issue:** Span ends stopped only at the next `## ` heading, so freshness markers glued to the following heading leaked into reads and appends could orphan them.
- **Fix:** Span ends now also stop at a marker line directly above a heading; reads strip trailing blank lines; the task-1 append writer shares the same helper.
- **Files modified:** strands_code_cli/router.py, tests/test_memory_curate.py
- **Verification:** `test_section_span_keeps_marker_glued_to_next_heading` plus full suite green
- **Committed in:** 864fc02 (Task 2 commit)

**4. [Rule 1 - Bug] Pinned hermetic fact dirs in scripted loop-run tests**
- **Found during:** Task 3 (plan-level full-suite gate: 16 failures in test_plan_cancel.py and test_model_switch.py)
- **Issue:** The new turn-boundary review queued promotion proposals from this checkout's ambient (git-ignored) harness fact files and prompted on stdin, crashing scripted `run_loop` drivers that never touch stdin.
- **Fix:** Pointed `MEMORY_FACT_DIR` at a tmp path in the `_run_script` driver and via a `TestTurnGuard` autouse fixture — the real boundary path still runs, against an empty dir. No assertions changed.
- **Files modified:** tests/test_plan_cancel.py, tests/test_model_switch.py
- **Verification:** Full suite green (775 passed, 5 deselected)
- **Committed in:** 2f15ec1 (Task 3 commit)

---

**Total deviations:** 4 auto-fixed (2 missing critical, 2 bugs)
**Impact on plan:** All four were required for correctness or suite integrity; no scope creep. The tty dialog branch (D4) is disclosed for one live-terminal pass rather than auto-fixed.

## Issues Encountered

- `capsys`/`capfd` cannot observe prompt text printed inside `output_context` (the `StdoutProxy` bypasses pytest capture); the quoted-review assertion records `builtins.print` calls instead.
- The plan's task-1 line references for `router.py` had drifted (plan cited `_diff_message` at lines 433-468; the branch now sits past the model picker); the `_diff_message`/`_mode_message` reply-only verb shape was followed regardless.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- SKILL-02 is complete: skills spine (06-01), memory contract (06-02), and the curation surface (06-03) are all landed with the full suite green.
- Phase 6 closes after this plan; the `/init` + `/memory` surface is ready for end-of-phase UAT, including the D4 live-terminal dialog check.
- Residual for later phases: the `.agent/memory` promotion source currently keys on filename diffs — a richer harness extraction signal can layer on the same queue without changing the review contract.

---
*Phase: 06-skills-memory-file*
*Completed: 2026-10-04*
