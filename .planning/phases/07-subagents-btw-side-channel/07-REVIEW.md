---
phase: 07-subagents-btw-side-channel
reviewed: 2026-10-06T08:33:23Z
depth: standard
files_reviewed: 15
files_reviewed_list:
  - strands_code_cli/btw.py
  - strands_code_cli/diff_gate.py
  - strands_code_cli/loop.py
  - strands_code_cli/main.py
  - strands_code_cli/policy_gate.py
  - strands_code_cli/router.py
  - strands_code_cli/skills.py
  - strands_code_cli/steering.py
  - tests/test_broker.py
  - tests/test_btw.py
  - tests/test_cost_context.py
  - tests/test_model_switch.py
  - tests/test_plan_cancel.py
  - tests/test_policy_gate.py
  - tests/test_router_btw.py
findings:
  critical: 1
  warning: 3
  info: 5
  total: 9
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-10-06T08:33:23Z
**Depth:** standard
**Files Reviewed:** 15
**Status:** issues_found

## Summary

Reviewed the Phase 7 mid-turn `/btw` side channel: the new `btw.py` module, the dual-future pump and cancel chooser in `loop.py`, per-tag approval routing in `policy_gate.py`, the steering carve-out, the `PendingStore` lock retrofit, and the six touched test modules. The fork/fence/queue mechanics, history append pairing, idle-drain delivery, and per-tag batch namespacing are sound and well-pinned by hermetic tests.

One Critical defect blocks this phase: the production handler wiring nests `RENDER_LOCK` on the same thread through a non-reentrant `threading.Lock`, so the first side-channel content message deadlocks the session. Three Warnings cover a Ctrl-C race in the pump's cancel path, an idle `/skills reload` racing an outliving side agent on the shared plugin object, and orphaned approval requests resurfacing as phantom prompts after cancel. No test-reliability issues found; the timing-sensitive tests carry adequate headroom and all spawned threads/pipes are joined.

## Critical Issues

### CR-01: RENDER_LOCK self-deadlock — FencedBtwHandler re-enters a non-reentrant lock via the shared LockedHandler

**File:** `strands_code_cli/btw.py:36`
**Issue:** `RENDER_LOCK` is a plain `threading.Lock` (non-reentrant). `FencedBtwHandler.__call__` (btw.py:117-122) holds `RENDER_LOCK` while delegating to its inner handler, and in production that inner handler IS the shared `LockedHandler` (btw.py:391 wraps the parent's `LockedHandler(DEFAULT_CODE_AGENT_CALLBACK_HANDLER)` from main.py:156; `LockedHandler.__call__` at btw.py:91-93 acquires `RENDER_LOCK` again). Same-thread re-acquire of a `threading.Lock` blocks forever. I verified `print_plain` (output.py:34-42) touches no lock, so this nesting is the only same-thread path — and it is unconditional.

Blast radius: the first side content message parks the side worker thread holding `RENDER_LOCK` forever. The main worker then parks in its own `LockedHandler`, so neither future completes and the pump spins forever. Ctrl-C after that wedges executor shutdown (parked workers ignore cancel events), requiring SIGKILL. Every real mid-turn `/btw` triggers it.

The existing contiguity test (`tests/test_btw.py:187`) never covers this combination — it wraps the raw `_Body` double, not a `LockedHandler` — so the suite is green while production wedges.
**Fix:**
```python
# strands_code_cli/btw.py:36
RENDER_LOCK = threading.RLock()
"""Serializes whole message blocks ... Reentrant: FencedBtwHandler holds
it while delegating to the shared LockedHandler inner on the same thread."""
```
Cross-thread mutual exclusion (the contiguity guarantee) is unchanged; same-thread nesting becomes legal. Add a regression test that wraps `FencedBtwHandler(LockedHandler(_Body(...)), ...)` and asserts it returns (e.g. via a timeout-guarded thread or direct call), since no current test exercises the production nesting.

## Warnings

### WR-01: Stale both_running lets a Ctrl-C fall through to silent full-turn completion

**File:** `strands_code_cli/loop.py:473`
**Issue:** The turn SIGINT handler sets no event while `both_running` is set (loop.py:753-755 — the chooser names targets instead). The pump's `except KeyboardInterrupt` legacy branch (loop.py:474-480) assumes the opposite: its comment states "the main event is already set by the turn SIGINT handler", and it sets only the (stale) `btw.cancel_event`. Race: the side future completes but `both_running` is not yet cleared when SIGINT arrives — the handler sets nothing (flag still set), the pump takes the legacy branch (`btw_future.done()` is true) which also sets nothing on main — so the main worker never observes cancel, the `turn_pool` exit join waits for natural completion, and `run_loop` then prints the "Cancelling…" copy for a turn that was never cancelled. The window is narrow (flag-clear vs signal arrival) but the outcome is a swallowed cancel plus misleading UX.
**Fix:**
```python
except KeyboardInterrupt:
    if btw_future is None or btw_future.done():
        # Legacy path: the handler normally sets the main event, but a
        # stale both_running flag may have suppressed it — set here too
        # (idempotent) so the turn always stops.
        cancel_event.set()
        btw.cancel_event.set()
        unregister_btw_cancel(broker)
        raise
```

### WR-02: Idle /skills reload mutates the shared AgentSkills plugin while an outliving side agent may use it

**File:** `strands_code_cli/loop.py:1370`
**Issue:** `build_agent` constructs one `AgentSkills` plugin (main.py:129) shared into every side rebuild via the replayed `_harness_kwargs` (btw.py:344-393 replays the SAME `skills` object). `_refresh_harness_skills` (loop.py:1370-1379) calls `plugin.set_available_skills(...)` from the idle prompt, where a D-11 outliving side run may still be mid-turn on `side_pool` using that same plugin's registry/tool. That is a mutation-concurrent-with-use race on one SDK object whose thread-safety is unproven — the main agent is idle at that point, but the side agent is not. Same shape as the `PendingStore` race this phase audited and locked, but unaudited here.
**Fix:** Defer the harness refresh while a side run is live (CLI index reload can still proceed), e.g. in `_refresh_harness_skills` return early when `btw_session.has_live` is true and note it in the reload reply ("model registry refresh deferred — side answer running"); or serialize registry access with a lock if the SDK documents one.

### WR-03: Approval requests orphaned by cancel resurface as phantom prompts on the next turn

**File:** `strands_code_cli/policy_gate.py:177`
**Issue:** `_ApprovalRequest.wait_answer` raises `TurnCancelled` when its event fires, but the request object stays in `broker._queue` when the pump never polled it. Nothing ever removes it: `bind_turn` clears only the batch cache, and pump exit does not drain. The next turn's pump then serves the dead worker's request — `run_prompt` runs the dialog/input for a worker that is gone. The cancel-both path (loop.py:525-533) makes this near-systematic rather than racy: the pump stops polling to run the chooser dialog, so a side worker blocked in approval at cancel time almost certainly leaves its request queued; the idle drain then also prints `BTW_IDLE_APPROVAL` for the dead request. I confirmed the phantom answer is harmless (it binds to the dead request; no live tool call is gated on it), so this is confusion/wasted prompts, not a fail-open — but it is user-visible incorrect behavior. Note the fix must NOT be drain-on-pump-exit: D-11 legitimately carries a LIVE side request across turn-pump exits.
**Fix:** Best-effort self-removal on abort — the waiter, not the pump, knows the request is dead:
```python
# policy_gate.py: in ApprovalBroker
def discard(self, req: "_ApprovalRequest") -> None:
    """Drop a request orphaned by cancel (best-effort; live waiters never call this)."""
    with self._queue.mutex:
        try:
            self._queue.queue.remove(req)
        except ValueError:
            pass  # already polled; nothing orphaned
```
Call it from the `TurnCancelled` paths in `wait_answer` (re-raise after). No `task_done` bookkeeping is needed since nothing calls `join()` on this queue — note that in the comment.

## Info

### IN-01: append_btw_turn has no absorb guard for user-trailing history

**File:** `strands_code_cli/btw.py:174`
**Issue:** `fork_btw_history` absorbs the framed question into a trailing user message so roles strictly alternate (btw.py:167-170), but `append_btw_turn` unconditionally appends a fresh user turn. I traced the flush sites (`_pump_parallel` end-flush, `_drain_idle_btw`) and could not construct a reachable user-trailing state through the current cancel/fail/retry paths (flushes land after successful, assistant-trailing turns; the empty-retry `del history[before:]` only runs when no btw content flushed), so this is hardening, not a live bug. Still, the invariant is implicit and one future flush-site change away from breaking.
**Fix:** Mirror the fork rule: if `messages` ends with a user message, append the `/btw` text block into it instead of adding a message — or assert assistant-trailing so the violation fails loudly in tests rather than at the provider.

### IN-02: build_btw_agent KeyErrors on parents without callback_handler

**File:** `strands_code_cli/btw.py:391`
**Issue:** `kwargs["callback_handler"]` raises a bare `KeyError` when the replayed kwargs lack the key (any agent not built by `build_agent`, or a double without `_harness_kwargs`). In `_spawn_next` this surfaces as a fenced spawn error and the dequeued question is dropped. Production always sets the key, so this only bites tests/doubles — but the `KeyError: 'callback_handler'` message misdirects.
**Fix:** `handler = kwargs.get("callback_handler")` with an explicit `ValueError("parent kwargs carry no callback_handler …")` when missing.

### IN-03: Session pump/pool teardown skipped on a crashing exception

**File:** `strands_code_cli/loop.py:1434`
**Issue:** `session_pump.__enter__()` is manual (loop.py:1434-1436) with the matching `__exit__`, `side_pool.shutdown`, save, and flush only on the fall-through path (loop.py:1697-1710). An uncaught exception escaping the loop body (e.g. from a review `apply_fn`) skips all of it; the comment acknowledges the broker flag is mooted by process death, but `side_pool` threads are non-daemon, so an in-flight side run delays interpreter exit via the executor `atexit` join instead of being cancelled promptly.
**Fix:** Wrap the `while True:` loop in `try/finally` with the existing teardown block (drain, cancel live, pool shutdown, pump exit) in the `finally`.

### IN-04: btw.running stays set after a main-only cancel reaps the side

**File:** `strands_code_cli/loop.py:497`
**Issue:** The main-only cancel hold (loop.py:497-524) reaps the side via `_finish_btw_turn`, nulls the future, and clears `both_running` — but never clears session-scoped `btw.running`. Until the next turn's first `_spawn_next` clears it on the empty queue, a mid-turn submit echoes "queued (#N in line)" for an idle side. Cosmetic and self-healing, but the submit-echo truthfulness this phase carefully maintains has one stale window.
**Fix:** Clear `btw.running` in that branch when `btw.spawn_queue.empty()` (same rule as `take_done_live`), or centralize the reap-and-clear sequence.

### IN-05: Shared interpreter/tool/model objects have no thread-safety audit

**File:** `strands_code_cli/btw.py:344`
**Issue:** The side rebuild deliberately shares the model, tools (including the stateful REPL interpreter tool), and interventions objects with the parent for concurrent use, but only `PendingStore` received this phase's explicit audit-and-lock treatment (diff_gate.py:101-106) and only the gate received explicit concurrency design (per-tag batch, thread-local ask context). Concurrent `execute_code` against one interpreter's executor state and concurrent `generate` against one model object ride on undocumented SDK/library thread-safety.
**Fix:** No code change proposed without evidence — extend the audit: run a tracer with main and side turns issuing simultaneous REPL/tool/model calls (or cite the SDK's thread-safety guarantee) and record the outcome the way the `PendingStore` docstring does.

---

_Reviewed: 2026-10-06T08:33:23Z_
_Reviewer: Muse Code (gsd-code-reviewer; generic-agent workaround)_
_Depth: standard_
