# DEBUG G-7-1a: idle side approval self-denies instead of bounded-wait

- Test: 1 (severity critical)
- TRUTH: "Idle side approvals announce once and wait for the next turn's pump (D-11 bounded-wait)"
- Status: ROOT CAUSE FOUND (suspected cause CONFIRMED)

## Symptoms (user-observed)

1. Mid-turn, a btw side shell approval worked (served by the turn pump).
2. After the main turn finished, the side's next approval (`python_repl`)
   denied itself with `CONFIRMATION_FAILED`.
3. `RuntimeWarning: coroutine 'Application.run_async' was never awaited`
   (choice.py broken-prompt path) instead of the expected
   `btw approval needed — will prompt when the next turn starts.`
   (BTW_IDLE_APPROVAL) plus waiting for the next turn.

## Root cause (confirmed)

`ApprovalBroker.pump()` has no nesting depth. The turn pump's `__exit__`
unconditionally clears `_pumping`, wiping the still-entered session pump's
state. Every later idle side approval then takes the inline `prompt()` path
on the SDK worker thread, where prompt_toolkit fails → deny.

Causal chain, with evidence:

1. `run_loop` enters the session pump once for the whole session
   (loop.py:1447-1449). The comment at loop.py:1438-1441 states the design
   intent explicitly: "The session broker pump stays entered across idle
   gaps (turn pumps nest inside it), so a side approval requested while
   main-idle enqueues for the next turn instead of running inline on the
   worker thread."
2. Each turn nests a second `broker.pump(cancel_event)` inside it —
   `_pump_parallel` (loop.py:398-399) for btw turns, `_invoke_agent`
   (loop.py:627) otherwise. Note `_invoke_parallel`'s own docstring
   (loop.py:333-334) claims it "never nests `broker.pump`" — true only of
   the turn level; it nests inside the *session* pump.
3. `pump.__exit__` (policy_gate.py:233-236) restores `_cancel`/`_pump_ident`
   but calls `self._pumping.clear()` unconditionally. After the first turn
   ends, `_pumping` is clear while the session pump is still logically
   entered. `pump()`'s exit is the ONLY `.clear()` site (grep over
   strands_code_cli/ + tests/ confirms; no other `_pumping` mutation).
4. The outliving side worker's next approval calls `broker.request()`
   (policy_gate.py:269): `_pumping` clear → `prompt()` runs inline on the
   SDK worker thread instead of enqueueing.
5. Inline on the worker thread, `read_answer` → `_dialog_answer` →
   `radio_choice` → prompt_toolkit `Application.run()` inside a thread with
   a running asyncio loop → `asyncio.run` cannot nest → exception → caught
   by `except Exception: return None  # broken prompt denies`
   (choice.py:171-174), emitting the `run_async was never awaited`
   RuntimeWarning. This is exactly the failure mode the broker docstring
   warns about (policy_gate.py:206-207: "observed `run_async was never
   awaited` → fail-closed deny").
6. `None` → `"n"` → gate denies → SDK `Confirm.evaluate` fails →
   `event.cancel_tool = "CONFIRMATION_FAILED: ..."`
   (strands/interventions/registry.py:139).
7. Because the request never queued, `has_pending` stays False, so
   `_drain_idle_btw` (loop.py:679-684) never prints BTW_IDLE_APPROVAL
   (btw.py:60) — the announce-once path is unreachable.

Differential check: mid-turn approvals work because the turn pump is
entered then; only post-turn (idle) approvals fail — matches the
unconditional-clear mechanism exactly.

Why tests missed it: `test_idle_approval_announced_once_then_served_next_turn`
(tests/test_btw.py:952+) models session-pump-entered + idle request, but
never enters+exits a turn pump nested inside the session pump first.

## Reasoning checkpoint

```yaml
reasoning_checkpoint:
  hypothesis: "Turn-pump __exit__ unconditionally clears _pumping, destroying the still-entered session pump, so idle side approvals run inline on the worker thread where prompt_toolkit fails closed."
  confirming_evidence:
    - "policy_gate.py:234 unconditional _pumping.clear() in pump.__exit__; sole clear site repo-wide"
    - "loop.py:1438-1441 design comment requires nesting; loop.py:398-399/627 nest a turn pump inside the session pump"
    - "policy_gate.py:269 inline path taken exactly when _pumping clear — matches worker-thread symptom"
    - "choice.py:173-174 broken-prompt deny + run_async warning matches observed warning; policy_gate.py:206-207 docstring names this failure"
    - "registry.py:139 CONFIRMATION_FAILED follows from a denied Confirm"
    - "Differential: mid-turn works (pump entered), idle fails (pump wiped)"
  falsification_test: "If a nested turn-pump exit left _pumping set (depth counter), the idle request would enqueue and the drain would announce — test sketch below asserts exactly this."
  fix_rationale: "A depth counter makes __exit__ restore the outer pump's entered state instead of destroying it — the mechanism (lost entered state) is fixed, not the symptom (inline failure)."
  blind_spots: "No live tty repro run (read-only investigation); relies on code-path evidence + existing tests. Thread-safety of the counter assumes pumps enter/exit only on the main thread (true today: session + turn pumps are both main-thread)."
  candidate_causes:
    - "code: missing nesting depth in ApprovalBroker.pump (CONFIRMED)"
    - "config: none plausible — no flag gates pump nesting; environment ruled out by deterministic mechanism"
  and_gate: "No — single condition (one turn completed while a side outlives) suffices; mid-turn success vs idle failure isolates it."
```

## Fix shape (precise, minimal)

In `ApprovalBroker` (policy_gate.py:216-236): add a nesting depth counter
(+ keep the save/restore, ideally as a stack):

- `__init__`: add `self._depth = 0`.
- `pump()` enter: `self._depth += 1` before/alongside `self._pumping.set()`.
- `pump()` exit (finally): restore `_cancel`/`_pump_ident` from saved values,
  `self._depth -= 1`, and only `self._pumping.clear()` when depth reaches 0
  (clamp at 0 for unbalanced-exit safety).
- Optional but recommended: replace the single `old_cancel, old_ident`
  locals with an explicit stack so triple nesting (session + turn + any
  future inner pump) restores correctly; all pump enter/exit today is
  main-thread-only so no lock is required (document that invariant).
- Do NOT touch `request()`, `poll()`, `has_pending`, `_drain_idle_btw`,
  or choice.py — they already implement the intended contract once the
  entered state survives.

One-line alternative considered and rejected: re-entering the session pump
after each turn — racy (a side approval landing between turn exit and
re-enter would still go inline) and fights the documented design.

## Regression-test sketch (tests/test_broker.py)

```python
def test_nested_turn_pump_exit_preserves_session_pump():
    broker = ApprovalBroker()
    session_cancel, turn_cancel = threading.Event(), threading.Event()
    with broker.pump(session_cancel):
        with broker.pump(turn_cancel):
            pass  # turn ends inside the session
        assert broker._pumping.is_set()          # entered state survives
        assert broker._cancel is session_cancel  # outer cancel restored
        # An idle side approval now ENQUEUES (worker blocks) instead of
        # running inline on the worker thread:
        box = {}
        t = threading.Thread(target=lambda: box.setdefault("a", broker.request(lambda: "allow")))
        t.start()
        assert broker.has_pending              # queued, not inline
        broker.poll(timeout=2.0).run_prompt()  # next turn's pump serves it
        t.join(timeout=5)
        assert box == {"a": "allow"}
    assert not broker._pumping.is_set()        # full exit still clears
```

Also add: exception-inside-turn-pump variant (finally path must still
preserve), and extend the test_btw.py idle-announce test to nest a turn
pump enter+exit before the idle request (the exact G-7-1a shape).

- Oracle type: derived (contract from loop.py:1438-1441 + D-11 bounded-wait).
- Boundary neighbors: single pump (existing tests), two-deep (above),
  exception-unwind, unbalanced/double exit (clamp, no negative depth),
  cancel-object identity restored to the session event.
