---
phase: 07-subagents-btw-side-channel
fixed: 2026-10-06
fix_scope: critical_warning
findings_in_scope: 4
fixed_count: 4
skipped_count: 0
commits:
  - 48d48ab
  - 121205a
  - 647dc55
  - 6b10c56
---

# Phase 07: Review-Fix Report (iteration 1)

**Scope:** CR-01 plus WR-01, WR-02, WR-03. Info findings (IN-01..IN-05) out of scope.

## What was fixed

### CR-01: RENDER_LOCK self-deadlock — fixed

**Commit:** `48d48ab` — `strands_code_cli/btw.py`, `tests/test_btw.py`

- `RENDER_LOCK` is now `threading.RLock()` with the reentrancy rationale in the
  docstring. Cross-thread mutual exclusion (the contiguity guarantee) is unchanged;
  same-thread nesting by `FencedBtwHandler` into the shared `LockedHandler` is legal.
- Regression test `test_production_nesting_reenters_without_deadlock` wraps
  `FencedBtwHandler(LockedHandler(_Body), ...)` — the production combination no
  prior test exercised — in a timeout-guarded thread so a regression fails instead
  of hanging the suite.

### WR-01: Stale both_running swallows Ctrl-C — fixed

**Commit:** `121205a` — `strands_code_cli/loop.py`

- The pump's legacy `except KeyboardInterrupt` branch now sets `cancel_event` too
  (idempotent), per the review's suggested patch, so a SIGINT arriving while the
  flag is stale still stops the turn. No dedicated test: the race window
  (flag-clear vs signal arrival) is not deterministically reproducible; covered by
  existing cancel-path tests plus the full suite.

### WR-02: Idle /skills reload races outliving side agent — fixed

**Commit:** `647dc55` — `strands_code_cli/loop.py`, `strands_code_cli/router.py`,
`tests/test_skills.py`

- `_refresh_harness_skills` returns a deferral note
  ("model registry refresh deferred — side answer running") without touching the
  shared plugin when `btw_session.has_live` is true. (`btw_session` is created
  after the closure is defined, but the closure only runs via dispatch, so the
  late binding is safe.)
- `_skills_message` appends a truthy refresh return as a parenthetical to the
  reload reply while still reloading the CLI index; existing `None`-returning
  callers are unaffected. Docstrings updated (the "never disagreeing" rule now
  documents the deferral exception).
- Test `test_deferred_harness_refresh_reloads_index_with_note` pins the
  reply-plus-note contract at the router level.

### WR-03: Orphaned approvals resurface as phantom prompts — fixed

**Commit:** `6b10c56` — `strands_code_cli/policy_gate.py`, `tests/test_broker.py`

- Added `ApprovalBroker.discard(req)` (best-effort removal under the queue mutex,
  no `task_done` bookkeeping — nothing calls `join()`).
- Hooked into `request()`'s `TurnCancelled` path rather than inside
  `_ApprovalRequest.wait_answer` (which has no broker reference): same waiter-knows
  principle as the review suggests, without changing `_ApprovalRequest`'s
  signature. All three abort paths (pre-set cancel, mid-wait cancel, answered-None)
  flow through it; already-polled requests make `discard` a harmless no-op.
- Tests: `test_cancelled_waiter_discards_orphaned_request` (aborted waiter's
  request leaves the queue empty) and `test_discard_of_polled_request_is_noop`
  (foreign/already-polled requests never raise).

## What was verified

- Per-fix affected files: `test_btw.py` (35 passed), `test_plan_cancel.py` +
  `test_router_btw.py` (32 passed), `test_skills.py` (47 passed), `test_broker.py` +
  `test_policy_gate.py` (42 passed).
- Full suite: `uv run pytest -q` → **883 passed, 6 deselected** (integration marker),
  green.
- Each fix committed atomically with hooks on, no `--no-verify`: `48d48ab`,
  `121205a`, `647dc55`, `6b10c56`.

## What remains

- IN-01..IN-05 untouched (out of `critical_warning` scope); IN-03 (session
  pump/pool teardown on crashing exceptions) and IN-05 (shared interpreter/model
  thread-safety audit) are the most substantive follow-ups.
- WR-01 has no dedicated regression test (non-deterministic race); relies on
  existing cancel-path coverage.
