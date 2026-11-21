---
phase: 01-session-wiring-repl-skeleton
plan: 02
subsystem: cli-entry-ux
tags: [repl, sessions, picker, slash-commands, auto-title, typer]
requires: [LOOP-01, SES-01]
provides: [resume-picker, slash-router, session-rename, model-auto-title]
affects: [01-03-hardening]
tech-stack:
  added: []
  patterns: [leading-slash-dispatch, picker-join-snapshot-presence, rename-wins-auto-title]
key-files:
  created:
    - strands_code_cli/router.py
    - tests/test_cli_entry.py
    - tests/test_session_index.py
  modified:
    - strands_code_cli/loop.py
    - strands_code_cli/main.py
    - strands_code_cli/session_index.py
key-decisions:
  - Picker joins index recency against on-disk snapshot prefixes; orphans hidden, never deleted
  - /resume is list-and-relaunch (no live session switch); /rename validates, never raises in the REPL
  - Auto-title is one direct model call with truncation fallback; renamed_by_user flag guards manual renames
requirements-completed: [LOOP-01, SES-01]
duration: ~35 min
completed: 2026-09-24T06:51:25Z
---

# Phase 01 Plan 02: Entry UX Expansion Summary

Full entry UX on the proven tracer: resume picker, direct
`--session-id` resume, `/resume` `/rename` `/exit` slash dispatch with
usage hints, UUID rename, and model auto-titles that never clobber a
manual rename.

## Accomplishments

- `strands_code_cli/router.py` (new): `dispatch` leading-slash router
  (`/resume` list or per-id relaunch hint, `/rename` through index
  validation, `/exit`; unknown slash returns `USAGE_HINT`, never an
  agent turn; no `/model` per D-06) and `show_picker` numbered picker
  (recent plus start-new, `updated_at` order, snapshot-presence join,
  abort/empty returns None for start-new).
- `loop.py` (extended, not rewritten): every line routes through
  `dispatch` first; `_maybe_auto_title` fires once after the first
  exchange — cheap direct model call, six-word cap, first-ask
  truncation fallback, separator sanitization, failures logged never
  raised.
- `main.py` (extended): no-arg launch shows the picker when snapshots
  back it, mints fresh when empty; `--session-id` bypasses the picker
  entirely; malformed-id validation still precedes all side effects.
- `session_index.py` (extended): `rename` validates (reject blanks and
  path separators, 120-char cap, titles only in sidecar JSON) and sets
  `renamed_by_user`; `update_title` no-ops on user-renamed sessions;
  mint/ensure stamp the flag; on-load backfill keeps pre-flag files
  auto-titlable.
- `tests/test_cli_entry.py` (20 tests): dispatch branches, picker
  order/join/start-new, auto-title model-cap and fallback, CliRunner
  no-arg/`--session-id`/picker-choice/malformed-id routing with the
  agent construction seam patched out.
- `tests/test_session_index.py` (21 tests): mint, recency ordering,
  rename round-trip plus KeyError, parametrized T-02-01 negatives,
  length cap, sidecar-only storage, auto-title fill plus
  never-overwrite (index and loop-helper level), corrupt/non-dict
  fail-soft reads, pre-flag backfill.

## Commits

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Slash router stub plus picker flow | d3dcd15 | router.py, loop.py, main.py, test_cli_entry.py |
| 2 | Entry routing tests | 97eb6ae | test_cli_entry.py |
| 3 | Rename plus auto-title lifecycle with index tests | e64153f | session_index.py, test_session_index.py |

## Verification

- `uv run pytest tests/test_cli_entry.py tests/test_session_index.py tests/test_session_resume.py -q`: 50 passed.
- `uv run pytest tests/ -q`: 227 passed (186 baseline + 41 new), 5 deselected.
- Planner scans: API-coverage — no external REST API in scope (title
  call uses the agent's own model handle, no new HTTP surface);
  assumption-delta — no second-case transition (strict input order,
  unknown/malformed ids are usage replies, single title attempt);
  schema-gate — no ORM files (sidecar JSON index needs no migration).
- Failure signals observed: patcher/mock mixup failed fast
  (`assert_called_once` on a patcher); separator rename replied
  "Cannot rename" pre-validation; suite caught both before commit.

## Deviations from Plan

- **[Rule 3 - Blocker] Test helper shape**: `_patched_launch` returned
  raw patchers, so `with` targets had no mock attrs. Fixed: helper is a
  contextmanager yielding `(build, loop)` mocks. Found by: Task 2 test
  run. Commit: 97eb6ae.
- **[Sequencing] Test-file split across tasks**: Task 1 created
  `tests/test_cli_entry.py` with dispatch/picker/auto-title units and
  Task 2 extended it with CliRunner routing (plan assigns the file to
  Task 2; writing it in Task 1 kept Task 1's `<verify>` command
  runnable). Separator-rejection and rename-wins tests deferred to
  Task 3 where their index validation lives. No behavior impact.

**Total deviations:** 2 auto-fixed (1 blocker, 1 sequencing). **Impact:**
none on scope; all within plan files.

## Threat Model Coverage

- T-02-01 (mitigate): rename rejects blanks, `/`, `\`, NUL and caps at
  120 chars; titles stored only in sidecar JSON (asserted: no file
  named by title); REPL surfaces failures as replies, never raises.
  Negative tests green.
- T-02-02 (mitigate): picker filters index entries to ids with a
  snapshot prefix (`<session_dir>/session/<id>`, verified against the
  installed SDK key layout plus a live offline probe); corrupt/non-dict
  index reads as empty without raising.
- T-02-03 (accept): title call sends only the first exchange text
  (first 500 chars) the user already typed; no additional context.

## Deferred / Next

- Picker, not provider config or first-run module: preflight still
  probes every launch (fail-closed without network even when creds
  exist) — 01-03 scope per 01-01 summary.
- `/resume <id>` advises relaunch with `--session-id`; no live session
  switch in the running loop (out of scope for this plan).
- Auto-title uses the agent's direct model handle when present and
  truncation otherwise; prompt wording (six-word cap) is untuned.

## Self-Check: PASSED

- All key-files exist on disk; `git log --grep="feat(01-02)"`
  returns 3 commits (d3dcd15, 97eb6ae, e64153f).
- Every task `<acceptance_criteria>` re-run green; plan
  `<verification>` items green above.
- Ready for 01-03.
