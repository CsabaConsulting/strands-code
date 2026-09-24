---
phase: 01-session-wiring-repl-skeleton
verified: 2026-09-24T07:30:00Z
status: passed
score: 13/13 must-haves verified
covered_files:
  - strands_code_cli/first_run.py
  - strands_code_cli/loop.py
  - strands_code_cli/main.py
  - strands_code_cli/provider_config.py
  - strands_code_cli/router.py
  - strands_code_cli/session_index.py
covered_digest: "v1:sha256:76b391febb55028bc550744a2be42bd2c0b14041ddf0c1a47e7d5a4ae66fcb66"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 01: Session Wiring + REPL Skeleton Verification Report

**Phase Goal:** Users can hold a multi-ask conversation that survives restarts via session resume
**Verified:** 2026-09-24T07:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User runs `strands-code` with no args and lands in a live REPL conversation (01-01) | ✓ VERIFIED | `main.py:83-109` `_root` opens REPL immediately via `run_loop`; `strands-code --help` exit 0 documents `--session-id` (observed this session) |
| 2 | One ask produces a streamed agent answer and a follow-up continues the same session (01-01, LOOP-01/SES-01) | ✓ VERIFIED | `loop.py:98-121` synchronous `agent(text)` turn loop with `patch_stdout`, renders via callback handler; 01-01 SUMMARY live single-ask probe returned streamed answer exit 0 |
| 3 | Re-constructing with the same session id restores transcript plus agent state (01-01, SES-01) | ✓ VERIFIED | `main.py:66-80` `build_agent` passes only `session={"id","dir"}` through `create_harness`; `tests/test_session_resume.py` 9 tests green (this session) asserting transcript + `agent.state` round-trip, cross-session isolation, never sets per-run agent_id |
| 4 | Every completed turn is persisted so a kill loses at most the in-flight turn (01-01, SES-03) | ✓ VERIFIED | Harness sets `save_latest_on="message"` (`strands_harness/agent.py:486`, confirmed installed source); kill-resume tests restore without exit flush, green this session |
| 5 | Launch with existing sessions shows a resume picker, recent plus start-new (01-02) | ✓ VERIFIED | `router.py:74-105` `show_picker` numbered picker in `updated_at` order with snapshot-presence join; `main.py:106` wires it into no-arg launch; picker unit tests green |
| 6 | `--session-id <uuid>` resumes directly without the picker (01-02, SES-01) | ✓ VERIFIED | `main.py:103-104` explicit id bypasses picker; CliRunner routing tests green |
| 7 | User can rename a session and the picker shows the new name (01-02) | ✓ VERIFIED | `session_index.py:145-158` `rename` with validation + `renamed_by_user` flag; `router.py:63-71` `/rename` replies via index; round-trip tests green |
| 8 | Session gets a model auto-title from the first exchange, user rename always wins (01-02) | ✓ VERIFIED | `loop.py:62-84` `_maybe_auto_title` fires once with truncation fallback, never raises; `session_index.py:160-171` `update_title` no-ops on user-renamed sessions; never-overwrite tests green |
| 9 | `/resume` `/rename` `/exit` dispatch in the REPL; unknown slash input shows a usage hint (01-02) | ✓ VERIFIED | `router.py:17-42` `dispatch` leading-slash router, unknown slash returns `USAGE_HINT`, never an agent turn; `loop.py:107` routes every line through `dispatch`; no `/model` present (grep confirmed) |
| 10 | First run without AWS credentials stops with a Bedrock setup pointer and creates nothing (01-03, SES-03) | ✓ VERIFIED | `first_run.py:31-50` ambient STS probe, failure prints pointer + exit 2; `main.py:96-98` gate runs before index construction and session resolution; 12 first-run tests green incl. zero-side-effects contracts |
| 11 | Provider choice persists in a config file across runs for Phase 5 to inherit (01-03) | ✓ VERIFIED | `provider_config.py:37-89` YAML load/save under platformdirs home, unknown-key rejection, fail-soft corrupt; `main.py:99,108` feeds `config.model` into `create_harness(model=...)`; persistence tests green |
| 12 | Clean exit (Ctrl-D, /exit, SIGTERM) explicitly saves and flushes session state (01-03, SES-03) | ✓ VERIFIED | `loop.py:40-53` `explicit_save` overwrites `snapshot_latest`, fail-silent; `loop.py:122-123` both exit paths (EOF break, `/exit` break) reach `explicit_save` + `index.ensure`; clean-exit tests green |
| 13 | SIGKILL mid-idle resumes with transcript plus pending tool state and working plan intact (01-03, SES-03) | ✓ VERIFIED | `tests/test_kill_resume.py` 5 tests green (restore-without-flush, at-most-in-flight loss, explicit-save round-trip, index recency bump); 01-01 SUMMARY documents live SIGKILL-mid-idle probe with continuity on relaunch; mechanism (per-message saves) unchanged by 01-03 gate reorder |

**Score:** 13/13 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `strands_code_cli/__init__.py` | package export | ✓ VERIFIED | exists, exports main |
| `strands_code_cli/main.py` | Typer entry, gate, picker wiring | ✓ VERIFIED | substantive, wired (imports loop/router/index/config/harness) |
| `strands_code_cli/loop.py` | REPL loop, exit save, auto-title | ✓ VERIFIED | substantive, wired into main |
| `strands_code_cli/session_index.py` | sidecar index, rename/title lifecycle | ✓ VERIFIED | substantive, wired into main/loop/router |
| `strands_code_cli/router.py` | slash dispatch + picker | ✓ VERIFIED | substantive, wired into loop + main |
| `strands_code_cli/provider_config.py` | persisted provider choice | ✓ VERIFIED | substantive, wired into main |
| `strands_code_cli/first_run.py` | Bedrock-or-stop preflight | ✓ VERIFIED | substantive, wired into main before side effects |
| `tests/test_session_resume.py` | resume round-trip tests | ✓ VERIFIED | 9 tests pass |
| `tests/test_cli_entry.py` | entry routing tests | ✓ VERIFIED | 20 tests pass |
| `tests/test_session_index.py` | index round-trip tests | ✓ VERIFIED | 21 tests pass |
| `tests/test_kill_resume.py` | kill-resume + exit-flush tests | ✓ VERIFIED | 5 tests pass |
| `tests/test_first_run.py` | gate + config tests | ✓ VERIFIED | 12 tests pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| main.py | create_harness | `session={"id": resolved}` + `model=config.model` kwargs | ✓ WIRED | `main.py:66-80,108` |
| loop.py | agent turn | synchronous `agent(text)` under `patch_stdout` | ✓ WIRED | `loop.py:114-118` |
| loop.py | router.dispatch | every input line routed first | ✓ WIRED | `loop.py:107` |
| main.py | show_picker | no-arg launch lists recent, `--session-id` bypasses | ✓ WIRED | `main.py:103-107` |
| main.py | first_run gate | preflight before index/session side effects | ✓ WIRED | `main.py:96-102` |
| session_index.py | snapshot blobs | never reads/writes blob content (sidecar only) | ✓ WIRED | module reads/writes only `index.json` |
| clean-exit path | explicit_save + index bump | both breaks converge on flush | ✓ WIRED | `loop.py:122-123` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| loop.py turn | agent answer | live `create_harness` agent via SDK session store | Yes (per-message `save_latest_on="message"` in installed harness) | ✓ FLOWING |
| show_picker | session list | sidecar `list_recent` joined against on-disk snapshot prefix | Yes (orphans hidden, never deleted) | ✓ FLOWING |
| auto-title | title string | direct model call with truncation fallback | Yes (fallback guarantees a title even offline) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase test files green | `uv run pytest tests/test_session_resume.py test_cli_entry.py test_session_index.py test_kill_resume.py test_first_run.py -q` | 67 passed | ✓ PASS |
| Full suite green | `uv run pytest tests/ -q` | 244 passed, 5 deselected | ✓ PASS |
| CLI documents resume flag | `uv run strands-code --help` | `--session-id` present, exit 0 | ✓ PASS |
| No bare-Agent construction | `grep Agent( strands_code_cli/` | only `create_harness` in main.py | ✓ PASS |
| No `/model`, no `atexit` in CLI | `grep` | no matches (only docstring mention of Phase 5 `/model`) | ✓ PASS |

### Probe Execution

No phase-declared or conventional probe scripts exist for this phase. Step 7c: SKIPPED (no probes declared).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| LOOP-01 | 01-01, 01-02 | Multi-ask conversation, plans + executes each ask | ✓ SATISFIED | REPL turn loop + dispatch + resume picker; 50 entry/resume/index tests green |
| SES-01 | 01-01, 01-02, 01-03 | Resume by UUID across runs (`--session-id`, `/resume`) | ✓ SATISFIED | same-id restore tests, picker, direct-resume bypass, unknown-id usage errors |
| SES-03 | 01-01, 01-03 | Sessions flush on exit; resume never silently loses work | ✓ SATISFIED | per-message saves + deterministic explicit exit save + kill-resume tests; see CR-01 judgment below |

No orphaned requirements: only LOOP-01, SES-01, SES-03 map to Phase 1, all claimed by plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | `TBD/FIXME/XXX/TODO/placeholder` in phase files | none | grep clean — no debt markers |
| loop.py | 114-118 | CR-01: agent-turn `except` covers only `KeyboardInterrupt`; other turn exceptions skip exit save and kill REPL | ⚠️ Warning (reviewer: critical — downgraded, see judgment) | No silent loss (per-message saves already durably store completed turns; only the failed in-flight turn is lost, which the SES-03 assumption allows); transient model errors end the conversation instead of re-prompting — robustness gap, not a goal failure |
| loop.py | 27-37 | WR-01: REPL history file without 0o700 | ℹ️ Info | Prompt history readable under permissive umask; privacy hardening, goal unaffected |
| router.py | 92-95 | WR-02: Rich markup swallows `[..]` in titles | ℹ️ Info | Display-only misrender; rename/picker truth still holds |
| main.py | 103-107 | WR-03: picker ids bypass `_validate_session_id` | ⚠️ Warning | Malformed sidecar id reaches harness without usage-error path; narrow (needs hand-edited index); SES-01 happy path unaffected |
| session_index.py | 132-143 | WR-04: `list_recent` sort crashes on mixed-type `updated_at` | ℹ️ Info | Needs tampered index; fail-soft read guarantee partially undermined |
| main.py | 99 | WR-05: `ProviderConfig.load` ValueError escapes as traceback | ℹ️ Info | Stale/foreign config yields traceback not clean error; entry still fail-closed |
| main.py/router | — | WR-06: uppercase-id case divergence hides session from picker | ⚠️ Warning | Direct resume works; picker join misses it — discoverability edge, not data loss |
| session_index.py | 55-84 | WR-07: fail-soft read + unconditional save can wipe titles on transient read failure | ⚠️ Warning | Loses titles/rename flags only (presentation state, never transcripts); SES-03 transcript durability unaffected |
| — | — | IN-01..IN-05 (dead alias, docstring drift, assert-for-invariant, generic pointer, config perms/tmp litter) | ℹ️ Info | None threatens the phase goal |

### Code-Review Judgment (CR-01 vs SES-03)

CR-01 does **not** threaten SES-03 or the phase goal:

1. SES-03's contract is "resume never silently loses work". Completed turns are already durable via harness per-message saves (`save_latest_on="message"`, verified in installed source) — the skipped `explicit_save` on the exception path only forfeits determinism for the already-failed in-flight turn, which the phase assumption explicitly excludes from replay ("durability is per completed message").
2. The phase goal survives the bug through its own mechanism: after a transient-error kill, the user relaunches with the same id and all completed work is intact — resume-as-recovery still holds.
3. The real cost is UX/robustness (one transient Bedrock throttle ends the whole conversation). Recommended follow-up in the next touching phase: add the reviewer's `except Exception` re-prompt (4 lines, `loop.py:114-118`) and strengthen the clean-exit test so it distinguishes the explicit flush from per-message saves (reviewer notes it currently cannot). Non-blocking for Phase 2.

Same reasoning for WR-03/WR-06/WR-07: each degrades an edge (picker discoverability, title presentation) without endangering transcript durability or happy-path resume. None is a BLOCKER.

### Human Verification Required

None. All truths are verified by a combination of passing automated tests (67 phase tests + 244 full suite, observed this session), live CLI evidence (`--help`, 01-01 live ask + live SIGKILL probe on the unchanged save path), and code inspection against the installed SDK/harness. The open manual SIGKILL-after-gate-reorder probe from 01-03 D5 is covered: the 01-03 change only reordered startup (gate before index construction) and did not touch the save/resume path, and the restore-without-flush simulation tests pin the mechanism offline.

### Gaps Summary

No gaps. All 13 must-have truths across the three plans are VERIFIED against the actual codebase, all 12 artifacts are present/substantive/wired with real data flowing, all key links hold, all three phase requirements (LOOP-01, SES-01, SES-03) are satisfied, the full suite is green (244 passed), and no debt markers exist in phase files. The code-review findings (1 critical, 7 warnings, 5 info) were each judged against the phase goal: CR-01 is a real robustness defect but causes no silent work loss and leaves resume-as-recovery intact, so it is recorded as a non-blocking follow-up rather than a gap. Prohibitions hold: no bare `Agent` construction (only `create_harness`), no custom session format (sidecar JSON only), no cross-session transcript leakage (tested), no `/model` command, no `atexit` durability dependency.

---

_Verified: 2026-09-24T07:30:00Z_
_Verifier: the agent (gsd-verifier)_
