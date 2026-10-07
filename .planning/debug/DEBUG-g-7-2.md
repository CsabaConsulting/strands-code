# DEBUG G-7-2: cancel-with-approval-in-flight race

UAT gap (test 2, severity high). TRUTH (D-08): "Cancel with an approval
dialog in flight cancels cleanly: no orphan dialogs, no dialog storms,
no internal exceptions."
Chooser routing was correct in all UAT attempts — not the bug
(`resolve_cancel_targets`, loop.py:203-215; tag wiring covered by
`test_ask_passes_tag_cancel_to_broker`).

## Symptoms (user-observed)

(a) After cancel-side, the dead side's Approve? dialog still popped and
trapped the user until main finished.
(b) Cancel-side with queued approvals: repeated Approve? dialogs + a
second 'Cancel which?' chooser + `btw failed (EventLoopException)`
(also seen on cancel-both: `exception=<TurnCancelled> | event loop
cycle failed`).
(c) Cancel-both appeared to wait for main to finish naturally.

## Root causes

### RC-1 (causes a + phantom half of b): pump serves dead-tag requests — CONFIRMED

`_ApprovalRequest` carries no tag/cancel event (policy_gate.py:162-176),
so the pump cannot tell a dead worker's request from a live one. All
three serve sites run unconditionally after `poll()`:
loop.py:467-470 (parallel pump), loop.py:503-506 (cancel-main hold),
loop.py:638-641 (single-worker pump).

WR-03 `discard()` (policy_gate.py:279-291) only removes a request
STILL QUEUED when the aborted waiter runs. Two gaps:

1. Dequeue-then-cancel: pump `poll()`s, then cancel lands (or the pump
was already blocked in `run_prompt()` on stdin). `discard()` hits the
`ValueError -> pass` path (test-pinned as no-op,
tests/test_broker.py:113-123) and the dialog runs for a dead worker.
Its answer goes nowhere (waiter raised `TurnCancelled`).
2. Queued-at-cancel: after cancel-side the pump `continue`s
(loop.py:494-495) and immediately polls. The waiter notices cancel on
a 50 ms poll (policy_gate.py:186-188); the pump usually wins, serving
the dead side's still-queued request as a phantom dialog. The chooser
itself widens this: while the chooser blocks the pump, no polling
happens, so any side request queued during chooser dwell is guaranteed
served-after-cancel unless the waiter wins the microsecond race.

Fix shape F-1 below (tag + pump-side skip) closes both gaps.

### RC-2 (correction to "dead worker's LATER requests"): queue holds at most one req per live worker — SUSPECT PARTIALLY REFUTED

Default SDK executor is `ConcurrentToolExecutor` (asyncio tasks, same
loop thread; agent.py:534, concurrent.py:56-90). But `ask` is invoked
synchronously on the loop thread (hitl.py:236, no try/except — raises
propagate) and `wait_answer` blocks that thread in 50 ms slices
(policy_gate.py:186), starving sibling tasks until the pump answers.
So in practice each worker has <=1 outstanding ask; the queue holds at
most 2 (main + side). There is no unbounded dead-side backlog: the
"repeated dialogs" are dead-side phantom(s) + main's legitimate queued
approvals in sequence, plus user-driven repeats (RC-3). Ask exceptions
are NOT swallowed by the SDK ("If it raises, the exception propagates
and aborts the run", hitl.py:167-169), so the cancelled worker always
dies on its first `TurnCancelled` — it cannot keep asking.

### RC-3 (second chooser in b): user Ctrl-C inside the phantom dialog; escalation to both is by design — CONFIRMED, no fix needed

Ctrl-C in any dialog re-raises `KeyboardInterrupt` (choice.py:120-125,
175-176) -> pump `except KeyboardInterrupt` -> `_choose_cancel_targets()`
(loop.py:485) with NO re-entry guard. A second Ctrl-C inside the chooser
escalates to `("main", "btw")` deliberately: returning empty would park
executor shutdown on uncancelled workers (loop.py:234-244). So mashing
Ctrl-C while trapped in a phantom dialog opens chooser #2 and can
cancel both. A guard would break the anti-park rule; the real fix is
removing the provocation (F-1). Document, don't guard.

### RC-4 (internal-exception text in b): SDK wraps TurnCancelled in EventLoopException; our `except TurnCancelled` sites are dead for real agents — CONFIRMED (extends suspected cause)

`event_loop_cycle` wraps every non-listed exception; `TurnCancelled` is
not in the pass-through tuple (event_loop.py ~394-411), producing the
observed log `exception=<TurnCancelled> | event loop cycle failed` and
raising `EventLoopException(original=TurnCancelled)` (exceptions.py:6-18)
out of `agent()`. Consequences:

- Side worker: `_finish_btw_turn` catches `Exception` and renders
`btw failed (EventLoopException)` (loop.py:304-308, btw.py:128-137)
instead of clean "Cancelled by user".
- `except TurnCancelled` at loop.py:545, loop.py:634, loop.py:1239,
loop.py:1595 NEVER fires for real agents (only for test doubles that
raise `TurnCancelled` directly). Single-worker mid-approval Ctrl-C with
absorbed KI surfaces as `Turn failed (EventLoopException)` via the
generic handler (loop.py:1597-1612) instead of the cancel UX.

Fix shape F-2 (unwrap + map to cancel).

### RC-5 (symptom c): cancel-both join waits on SDK step granularity + silent join — CONFIRMED as mechanism; half by design

After both events are set, the pump raises (loop.py:529-537) and
`with ThreadPoolExecutor as turn_pool` exit joins the main worker
(`shutdown(wait=True)`). Worker abort latency = SDK checkpoint
granularity: approval-parked aborts in <=50 ms (wait_answer);
Bedrock model streams abort promptly (bedrock.py:90-132 cancel_poll
race); but a synchronous tool run has NO mid-tool checkpoint (cancel
observed before tools at event_loop.py:875 and after at ~1000) — a
long shell/python step runs to completion. That matches the
"Cancelling after the current step…" copy (loop.py:198): step
granularity is the design. The UAT-perceived hang is amplified because
nothing is printed before the join (cancel lines print in run_loop only
after `_invoke_agent` returns), so a mid-tool cancel-both looks exactly
like "main finishing naturally". Also note the SIGINT handler sets NO
event while `both_running` is set (loop.py:757-759) and workers run
uncancelled during chooser dwell — both intentional (D-08 names targets).

Fix shape F-3 (ack-before-join + doc); do NOT attempt thread preemption.

## Fix shapes

F-1 (core, kills a + phantom-b): tag requests, skip dead ones pump-side.
`_ApprovalRequest.__init__(prompt, cancel=None)` stores the waiter's
event; `broker.request` passes it through. After every `poll()`, if
`req.cancel is not None and req.cancel.is_set()`: do NOT `run_prompt()`;
instead mark done-with-None (new `req.abort()`: `answer=None`,
`_done.set()`) so a not-yet-aborted waiter raises `TurnCancelled` via
the cancel/None path, then keep polling. Apply at loop.py:470, :506,
:641. `cancel=None` (legacy/tests) always serves. Drain loop, not
single skip, so a dead main+side pair both drop.

F-2 (internal exceptions): add `policy_gate.worker_cancelled(exc)`:
True for `TurnCancelled` or `EventLoopException` whose
`original_exception` chain contains `TurnCancelled`. `_finish_btw_turn`
renders a fenced "Cancelled by user" note (never "btw failed") on
cancel; loop.py:545/634 map it onto the existing `KeyboardInterrupt`
path; run_loop:1595 and _drain_revise_rounds:1239 accept it defensively.
Import `EventLoopException` from `strands.types.exceptions` (SDK-owned).

F-3 (cancel-both wait): print the two-press ack line in the pump cancel
branches BEFORE raising (join happens at pool exit); keep step
granularity. Doc note: sync tools run to completion; streams and
approval waits abort promptly.

F-4 (explicit non-fix): no chooser re-entry guard; keep KI-in-chooser
-> both (anti-park rule, loop.py:234-244). Re-verify after F-1 that the
second chooser no longer reproduces without deliberate double Ctrl-C.

## Regression-test sketches (tests/test_broker.py + tests/test_loop_cancel.py)

T-1 phantom skip (deterministic, no timing): pump active; worker thread
`broker.request(prompt, cancel)` with PRE-SET cancel event; pump side
polls and applies F-1 skip: assert prompt callable never ran AND waiter
raised `TurnCancelled`.
T-2 mixed queue: queue side req (set event) + main req (live event);
F-1 drain serves ONLY main's, in order; side waiter got `TurnCancelled`.
T-3 wrap mapping: `worker_cancelled(EventLoopException(TurnCancelled()))`
True; `worker_cancelled(EventLoopException(ValueError()))` False;
`_finish_btw_turn` with EventLoopException-wrapped future renders fenced
cancel note, output contains no "failed (".
T-4 ack-before-join: pump cancel branch emits the cancel line before the
join point (capfd; extract helper if needed for unit scope).
T-5keep: existing WR-03 tests (test_broker.py:91-123) still pass.

## Reasoning checkpoint

hypothesis: "Phantom dialogs come from the pump serving dead-tag
requests (untagged queue + serve-unconditional + discard loses the
poll race); internal-exception text comes from the SDK wrapping
TurnCancelled in EventLoopException, defeating our except-TurnCancelled
sites; cancel-both waiting is the pool join over SDK step-granularity
cancel with no pre-join ack."
confirming_evidence: untagged _ApprovalRequest + 3 unconditional serve
sites; 50 ms waiter poll vs immediate pump poll; SDK wrap code + log
line matching the UAT string verbatim; dead except sites (real agents
can only surface the wrapped type); shutdown(wait=True) join +
checkpoint-only SDK cancel.
falsification_test: if a live repro after F-1+F-2 still shows a
dead-side dialog or "EventLoopException" text, this hypothesis is wrong.
fix_rationale: F-1 removes the phantom at the only choke point that sees
both workers (the pump); F-2 restores the cancel mapping the SDK wrap
broke; F-3 addresses the perceived hang without unsafe preemption.
blind_spots: no live tty repro (headless); waiter-starvation claim rests
on code reading, not a concurrency probe; Bedrock prompt-cancel read
from SDK code, not observed live.
candidate_causes: code (untagged queue, dead except sites) +
environment (SDK wrap + step granularity, provider stream behavior).
and_gate: yes — user-visible storm needs pump race AND SDK wrap AND
user Ctrl-C response; each fix stands alone regardless.

## Current focus

ROOT CAUSE FOUND. Read-only investigation; no source edits made.
