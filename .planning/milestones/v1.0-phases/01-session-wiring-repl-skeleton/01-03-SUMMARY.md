---
phase: 01-session-wiring-repl-skeleton
plan: 03
subsystem: cli-durability
tags: [bedrock-gate, provider-config, kill-resume, snapshot-sessions, typer]
requires: [SES-01, SES-03]
provides: [first-run-bedrock-gate, persisted-provider-config, kill-resume-tests]
affects: [phase-5-model-switching]
tech-stack:
  added: []
  patterns: [preflight-before-side-effects, injectable-probe, fail-soft-config]
key-files:
  created:
    - strands_code_cli/provider_config.py
    - strands_code_cli/first_run.py
    - tests/test_kill_resume.py
    - tests/test_first_run.py
  modified:
    - strands_code_cli/main.py
key-decisions:
  - Gate runs before index construction: a failing preflight creates zero filesystem side effects
  - ProviderConfig.load is fail-soft on missing/corrupt files but raises on unknown keys
  - Kill-safety rests on per-message snapshot saves; explicit save is determinism-only on clean exit
requirements-completed: [SES-01, SES-03]
coverage:
  - id: D1
    description: "First-run Bedrock-or-stop gate runs before construction with zero side effects"
    requirement: "SES-03"
    verification:
      - kind: unit
        ref: "tests/test_first_run.py#TestPreflightGate"
        status: pass
      - kind: unit
        ref: "tests/test_first_run.py#TestFirstRunCli"
        status: pass
    human_judgment: false
  - id: D2
    description: "Provider choice persists in YAML config for Phase 5 to inherit"
    requirement: "SES-01"
    verification:
      - kind: unit
        ref: "tests/test_first_run.py#TestProviderConfigPersistence"
        status: pass
    human_judgment: false
  - id: D3
    description: "SIGKILL mid-idle resumes transcript plus agent state without exit flush"
    requirement: "SES-03"
    verification:
      - kind: integration
        ref: "tests/test_kill_resume.py#TestKillResume"
        status: pass
    human_judgment: false
  - id: D4
    description: "Clean exit explicitly saves and bumps index recency deterministically"
    requirement: "SES-03"
    verification:
      - kind: unit
        ref: "tests/test_kill_resume.py#TestCleanExitFlush"
        status: pass
    human_judgment: false
  - id: D5
    description: "Live SIGKILL of the real CLI mid-idle restores transcript plus working plan on relaunch"
    requirement: "SES-03"
    verification: []
    human_judgment: true
    rationale: "Killing the dev shell process cannot be automated safely in CI; needs the manual probe from the plan verification."
duration: ~30 min
completed: 2026-09-24T07:10:00Z
status: complete
---

# Phase 01 Plan 03: Durability Slice Summary

Bedrock-or-stop first-run gate with persisted provider config, plus the
kill-resume guarantee pinned by offline tests: per-message snapshots
survive SIGKILL, clean exits flush deterministically.

## Performance

- **Duration:** ~30 min
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- `strands_code_cli/provider_config.py` (new): `ProviderConfig` dataclass
  with `yaml.safe_load`/`safe_dump` under the platformdirs user config
  dir, unknown-key rejection, fail-soft defaults on corrupt YAML, 0o700
  config home, no secrets in the file.
- `strands_code_cli/first_run.py` (new): `preflight_credentials` with a
  cheap STS `get_caller_identity` ambient-chain probe, injectable for
  offline tests; failure prints the Bedrock pointer and exits 2.
- `main.py` (extended, not rewritten): gate moved strictly before index
  construction and session resolution; loaded model string feeds
  `create_harness(model=...)`; `_preflight_credentials` kept as a thin
  wrapper so existing test seams hold.
- `tests/test_kill_resume.py` (5 tests): restore-without-flush keeps
  transcript plus `agent.state`; kill loses at most the in-flight turn;
  explicit-save round-trip, no-manager no-op, index recency bump.
- `tests/test_first_run.py` (12 tests): non-zero exit, Bedrock pointer,
  zero filesystem side effects, no direct credential reads, config
  round-trip/persistence/unknown-key/corrupt-YAML/no-secrets contracts.

## Task Commits

Each task was committed atomically:

1. **Task 1: provider config plus first-run gate** - `e547db6` (feat)
2. **Task 2: kill-resume plus exit-flush tests** - `ce648e9` (feat)
3. **Task 3: first-run negative tests** - `67104e1` (feat)

## Files Created/Modified

- `strands_code_cli/provider_config.py` - YAML provider config load/save (D-06)
- `strands_code_cli/first_run.py` - Credential preflight + Bedrock pointer (D-05)
- `strands_code_cli/main.py` - Gate-before-side-effects wiring, config model feed
- `tests/test_kill_resume.py` - SIGKILL-simulation and clean-exit tests (SES-03)
- `tests/test_first_run.py` - Fail-fast gate and config persistence tests (SES-03)

## Decisions Made

- Gate placement before `SessionIndex` construction: the index mkdir is a
  side effect, so the preflight must precede it for the zero-side-effects
  acceptance to hold.
- `load()` fail-soft vs strict split: corrupt/unparseable YAML yields
  defaults (T-03-02 fail-soft), unknown keys raise `ValueError` so typos
  never silently reach `create_harness`.
- Kill-safety attribution: per-message `save_latest_on="message"` owns
  crash safety; `explicit_save` on clean exit is determinism-only and
  fail-silent (T-03-03 accepted).

## Deviations from Plan

### Auto-fixed Issues

**1. [Sequencing] Task 1 `<verify>` names a test file owned by Task 3**
- **Found during:** Task 1 (provider config plus first-run gate)
- **Issue:** Task 1's `<verify>` runs `tests/test_first_run.py`, which the
  plan assigns to Task 3 and does not exist yet at Task 1 time.
- **Fix:** Verified Task 1 with the full suite green plus a `/tmp` scratch
  probe of every acceptance clause (gate exit code, pointer text, empty
  filesystem, config round-trip, unknown-key rejection); the named test
  file landed in Task 3 and passes.
- **Files modified:** none in repo (probe kept under `/tmp`)
- **Verification:** `uv run pytest tests/ -q` 227 passed; probe printed
  `TASK1 ACCEPTANCE OK`
- **Committed in:** e547db6 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (sequencing). **Impact on plan:** none
on scope; plan ordering ambiguity absorbed without extra files.

## Threat Model Coverage

- T-03-01 (mitigate): probe errors surface a static pointer; config file
  holds only the provider string (no-secrets test asserts absence of
  secret/access/token); failure log emits only the exception type name,
  never credential material. Verified by code inspection plus tests.
- T-03-02 (mitigate): unknown keys raise `ValueError`; corrupt YAML falls
  back to defaults; unknown keys never reach `create_harness`. Negative
  tests green.
- T-03-03 (accept): flush is best-effort over per-message saves; explicit
  save failures log and never raise.

## Issues Encountered

None - plan executed as written apart from the sequencing note above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 complete: tracer (01-01) plus entry UX (01-02) plus durability
  (01-03) all green; `uv run pytest tests/ -q` 244 passed, 5 deselected.
- Phase 5 `/model` inherits `ProviderConfig.load().model`; no new flags
  were added in this plan.
- Manual probe still open: SIGKILL the real CLI mid-idle, relaunch with
  the same id, confirm transcript plus working plan (D5 above).

## Self-Check: PASSED

- All key-files exist on disk; `git log --grep="feat(01-03)"` returns 3
  commits (e547db6, ce648e9, 67104e1).
- Every task `<acceptance_criteria>` re-run green; plan `<verification>`
  items green except the manual SIGKILL probe (D5, human judgment).

---
*Phase: 01-session-wiring-repl-skeleton*
*Completed: 2026-09-24*
