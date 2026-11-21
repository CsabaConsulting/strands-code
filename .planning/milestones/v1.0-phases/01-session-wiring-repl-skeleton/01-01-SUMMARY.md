---
phase: 01-session-wiring-repl-skeleton
plan: 01
subsystem: cli-tracer-slice
tags: [repl, sessions, typer, prompt-toolkit, create-harness, tracer]
requires: [LOOP-01, SES-01, SES-03]
provides: [strands-code-entry, repl-loop, session-index, resume-test]
affects: [01-02-picker-config, 01-03-hardening]
tech-stack:
  added: [typer-0.27.2, prompt-toolkit-3.0.53, platformdirs-4.11.12]
  patterns: [create_harness-session-dict, sidecar-title-index, patch_stdout-turn]
key-files:
  created:
    - strands_code_cli/__init__.py
    - strands_code_cli/main.py
    - strands_code_cli/loop.py
    - strands_code_cli/session_index.py
    - tests/test_session_resume.py
  modified:
    - pyproject.toml
    - uv.lock
    - .gitignore
key-decisions:
  - Sidecar title index; snapshot blobs never touched by CLI code
  - Session id pre-validated through the SDK validator before any side effect
  - Preflight credential probe on every launch until plan 02 config lands
requirements-completed: [LOOP-01, SES-01, SES-03]
duration: ~40 min
completed: 2026-09-24T06:35:00Z
---

# Phase 01 Plan 01: Tracer Slice Summary

Working `strands-code` entry, minimal REPL loop, session wiring via
`create_harness`, sidecar index core, and a passing cross-process resume
test. Full stack proven live: ask, streamed answer, exit, resume.

## Accomplishments

- `SessionIndex` sidecar (`mint`, `ensure`, `list_recent`, `rename`,
  `update_title`): 0o700 dirs, symlink refusal, atomic writes, fail-soft
  reads. Never touches snapshot blobs.
- `tests/test_session_resume.py` (9 tests): same-id re-construction
  restores transcript plus `agent.state` (default agent id only),
  cross-session isolation, no-bare-Agent contract, T-01-01 negative
  (`--session-id ../../x` is a usage error creating nothing), entry
  routing, fresh-UUID mint on no-arg.
- Package scaffold: floor-only pins, `strands-code` console script;
  library imports with no CLI deps pulled in (asserted).
- Entry plus loop: no-arg REPL, `--session-id` routing, SDK-validator
  id check, Bedrock-pointer preflight, `create_harness` with id plus
  dir keys only, `patch_stdout` turns, Ctrl-C line-cancel, Ctrl-D
  clean exit with explicit `snapshot_latest` save plus index bump.

## Commits

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | End-to-end session round-trip | 9593433 | session_index.py, test_session_resume.py, __init__.py |
| 2 | Package scaffold plus console script | 7253811 | pyproject.toml, uv.lock |
| 3 | Minimal entry plus REPL loop | a989cd7 | main.py, loop.py, __init__.py, test_session_resume.py, .gitignore |

## Verification

- `uv run pytest tests/ -q`: 186 passed (177 baseline + 9 new), 5 deselected.
- `uv run strands-code --help`: exit 0, documents `--session-id`.
- Live: no-arg launch reaches REPL; piped ask returned the streamed
  answer and exited 0 with `snapshot_latest.json` written.
- Live kill probe: SIGKILL mid-idle, relaunch same id exit 0 with
  continuity; pre-relaunch state held the index entry and no snapshot,
  matching the at-most-in-flight-turn guarantee.
- Failure signals observed: mutated transcript expectation fails;
  bad session id exits non-zero; help failed pre-`main.py`.

## Deviations from Plan

- **[Rule 2 - Missing] Validate-before-side-effects**: `_root` built
  `SessionIndex` (mkdir) before id validation, creating `.agent/` for
  malformed ids. Fixed: pure validation first. Found by: Task 3 test.
  Commit: a989cd7.
- **[Rule 2 - Missing] `.agent/` gitignore**: session runtime data was
  untracked, one stray commit away from versioned snapshots. Added one
  line to `.gitignore`. Commit: a989cd7.
- **[Sequencing] `__init__` export deferred**: final `main` export
  landed in Task 3 with `main.py`; Tasks 1-2 kept a placeholder so
  every commit stayed green. No behavior impact.
- **[Rule 3 - Blocker] Typer 0.27 renames**: `CliRunner` uses
  `isolation()` (stdio only, no fs chdir) and the default handler
  lives in `code_agent`, not `callback_handler`. Adapted; fs-sensitive
  tests use `monkeypatch.chdir`. Commits: a989cd7.

**Total deviations:** 4 auto-fixed (2 missing-functionality, 1 blocker,
1 sequencing). **Impact:** none on scope; all within tracer files plus
one `.gitignore` line.

## Threat Model Coverage

- T-01-01 (mitigate): id pre-validated via SDK `validate_identifier`
  plus blank/dot-segment rejection; `BadParameter` usage error, zero
  side effects; negative test green.
- T-01-02 (mitigate): symlinked index roots/files raise `ValueError`;
  snapshot I/O left to SDK storage guards.
- T-01-03 (mitigate): session and index dirs created `0o700` with
  `chmod`; transcripts never logged.
- T-01-04 (accept): resumed content trusted-to-self per plan.

## Deferred / Next

- Picker, provider config, first-run module land in plans 02/03;
  preflight currently probes every launch (fail-closed without
  network even when creds exist).
- `validate_identifier`/`Identifier` import from semi-private SDK
  paths (`strands.session.snapshot_session_manager`,
  `strands._identifier`); no public export exists.
- Assumption flags from the plan (empty-input re-prompt, strict turn
  ordering, no in-flight replay) hold as implemented; live multi-turn
  UX beyond the single-ask probe is plan 02 scope.

## Self-Check: PASSED

- All key-files exist on disk; `git log --grep="feat(01-01)"`
  returns 3 commits (9593433, 7253811, a989cd7).
- Every task `<acceptance_criteria>` re-run green; plan
  `<verification>` items green or live-proven above.
- Ready for 01-02.
