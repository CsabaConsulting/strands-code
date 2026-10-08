---
status: complete
phase: 07-subagents-btw-side-channel
source: [07-VERIFICATION.md]
started: 2026-10-06T09:05:00Z
updated: 2026-10-07T07:10:00Z
round: 2
---

## Current Test

[testing complete — round 2]

## Tests

### 1. Start a long main task, fire /btw needing approval, let main finish first
expected: Tagged [btw] prompt is announced at idle ('btw approval needed — will prompt when the next turn starts.') and served by the next turn's pump; fenced block lands without scrambling the prompt line
result: issue
reason: "R2: nesting fix works (no self-deny; approval queued and served by next turn with tagged dialog; side stayed in scope). BUT user rejects the idle UX: queued approval hides until an unrelated next turn is typed (24h idle = 24h hidden); BTW_IDLE_APPROVAL only prints when the prompt returns, so an idling user never sees it; looked 'stuck/gone'. Exit silently drops the parked side (cancel + join-abort after drain, no transcript note)."

### 2. Run main + btw concurrently, press Ctrl-C once
expected: Chooser offers main/btw/both and cancels only the named target (ESC cancels nothing)
result: pass
reason: "R2: cancel-side with btw approval in flight — chooser correct, NO orphan dialog (pump-side skip works), clean fenced 'Cancelled by user' (no EventLoopException fence), main streamed untouched to completion with cost+memory. Residual: one SDK logger.error line ('exception=<TurnCancelled> | event loop cycle failed' from strands event_loop.py:408) — harness noise, below gap bar per user verdict."

### 3. Fire /btw mid-task while main streams
expected: Fenced btw blocks arrive live with main output outside and no torn lines
result: pass

### 4. Review LOOP-03 safety prohibition: btw mutations face the same deny-first gate
expected: No weaker btw approval lane exists; trust_delegated auto-trust is announced in the transcript
result: pass
reason: "User confirmed: everything gated, denials held. Spin-off gap G-7-4 filed during review (dialog attribution)."

### 5. Review LOOP-03 transparency prohibition: side content never presented as main content
expected: Fences, prompts, history appends, /policy last entries all carry btw identity
result: pass
reason: "User confirmed G-7-4 covers the dialog-attribution defect; fences/headers/history identity otherwise held (plus fencing-style fix suggestion folded into G-7-4)."

### 6. Review LOOP-03 memory-safety prohibition: side reasoning never memorialized as durable user memory
expected: Side agent recalls shared facts but never writes the fact store or curate queue
result: pass
reason: "User confirmed. Verified: /tmp/uattest store has 5 main-task facts, zero side leakage across 6+ side runs; /tmp/uatinit store has only Oct-5 /init leftovers (today's turns there were all cancelled, which correctly memorializes nothing); curate queue empty as expected."

## Summary

total: 6
passed: 5
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-7-1a
  truth: "Idle side approvals announce once and wait for the next turn's pump (D-11 bounded-wait)"
  status: resolved
  resolved_by: 07-04-PLAN.md
  resolved_at: 2026-10-07
  reason: "User reported: side python_repl approval after main-end denied itself (CONFIRMATION_FAILED + RuntimeWarning: run_async never awaited) instead of announcing 'will prompt when the next turn starts'"
  severity: critical
  test: 1
  artifacts: [strands_code_cli/policy_gate.py]
  missing: ["DIAGNOSED (.planning/debug/DEBUG-g-7-1a.md): confirmed — pump.__exit__ (policy_gate.py:233-236) unconditionally clears _pumping (sole clear site repo-wide), wiping the still-entered session pump (loop.py:1447-1449; design intent at 1438-1441 says turn pumps nest inside it). Every later idle side approval takes inline prompt() on the SDK worker thread where asyncio nesting fails → deny; has_pending stays False so BTW_IDLE_APPROVAL never prints. Fix: nesting refcount in pump enter/exit; regression test enter-session/exit-turn then assert still-pumping + enqueue-not-inline."]
- gap_id: G-7-1b
  truth: "Side agent answers ONLY the btw question and never continues the main task (D-04/D-09 scope)"
  status: resolved
  resolved_by: 07-04-PLAN.md
  resolved_at: 2026-10-07
  reason: "User reported: side agent, after listing /tmp, issued python_repl containing the MAIN essay task inside the btw fence; essay rendered twice (main + btw)"
  severity: high
  test: 1
  artifacts: [strands_code_cli/btw.py]
  missing: ["DIAGNOSED (.planning/debug/DEBUG-g-7-1b.md): confirmed + sharpened — spawn snapshots live history incl. the unanswered main directive (loop.py:572-574); the absorb branch (btw.py:168-172) MERGES main directive + btw question into ONE trailing user turn (upstream _with_history never meets this case: harness children spawn inside tool calls where trailing user turns are already-answered toolResults); neither BTW_FRAMING (btw.py:63-66) nor BTW_FORK_PREAMBLE (btw.py:69-72) forbids performing earlier turns, and CODE_AGENT_INSTRUCTIONS says 'solve tasks'. Attribution proven real (not render leak): [btw] tag classifies by agent identity. Recommended fix A+B: harden framing (ONLY + do-not-perform-main) AND mark the in-flight non-toolResult user turn as context-only; exclusion (C) as fallback if live repro still fails. Verify live."]
- gap_id: G-7-2
  truth: "Cancel with an approval dialog in flight cancels cleanly: no orphan dialogs, no dialog storms, no internal exceptions (D-08)"
  status: resolved
  resolved_by: 07-04-PLAN.md
  resolved_at: 2026-10-07
  reason: "User reported: (a) dead side's Approve? dialog popped after cancel-side and trapped user till main finished; (b) repeated Approve? dialogs + second chooser + 'btw failed (EventLoopException)' after cancel-side with queued approvals; (c) cancel-both waited for main natural finish"
  severity: high
  test: 2
  artifacts: [strands_code_cli/loop.py, strands_code_cli/policy_gate.py]
  missing: ["DIAGNOSED (.planning/debug/DEBUG-g-7-2.md): RC-1 CONFIRMED — _ApprovalRequest untagged (policy_gate.py:162), all 3 pump serve sites unconditional (loop.py:470/506/641), pump wins race vs waiter 50ms poll → dialog for dead worker; fix F-1 tag requests + pump-side skip on set tag event. RC-2 PARTIALLY REFUTED — queue holds at most one req per live worker, no tag-wide purge needed. RC-3 CONFIRMED no-fix — second chooser is by-design escalation (Ctrl-C inside phantom dialog); dies with F-1. RC-4 CONFIRMED extends — SDK wraps TurnCancelled in EventLoopException so our except-TurnCancelled sites are dead for real agents; fix F-2 unwrap + map to clean cancel rendering. RC-5 CONFIRMED half-by-design — cancel join waits on SDK step granularity; fix F-3 ack-before-join + doc, no thread preemption."]
- gap_id: G-7-1-R2
  truth: "An idle side approval is visible and servable at idle — never hidden until the next turn, never silently dropped on exit (D-11)"
  status: failed
  reason: "User reported (R2): side approval queued while idle stayed invisible until an unrelated second turn was SUBMITTED with Enter (not while typing); looked stuck/gone ('had I waited 24h it would hide for a day'); exit behavior unknown"
  severity: high
  test: 1
  artifacts: [strands_code_cli/loop.py]
  missing: ["Fresh gap per #1921 (G-7-1a mechanism confirmed working in R2: queued + served + tagged). Defects: (1) BTW_IDLE_APPROVAL prints only in _drain_idle_btw, which runs when the idle prompt RETURNS a line or at exit — an idling user never sees it; announce promptly at turn boundary when side live + approval pending. (2) No idle affordance to serve a queued approval without typing a dummy turn — revisit D-11 multiplex primary or add prompt-with-timeout poll / explicit idle-serve affordance. (3) Exit path (loop.py ~1758-1766) cancels the parked side during shutdown join with no transcript note — announce the dropped side. Needs diagnosis + fix plan."]
- gap_id: G-7-1-R2b
  truth: "Mid-turn approval dialogs respond to input promptly with no phantom repeats, even while the other agent streams"
  status: failed
  reason: "User reported (R2 test-1 rerun): felt an unnecessary queued/duplicate approval (approved twice; transcript shows each box once, so likely swallowed inputs forced repeats); selector movement very delayed, 'swallowing every second input' while main streamed around the open dialog. CORROBORATED (R2 test-2 attempt): same lag on the Cancel-which chooser — cursor moved only every ~3rd keypress, Enter needed multiple presses, dialog seemingly repeated."
  severity: medium
  test: 1
  artifacts: [strands_code_cli/choice.py, strands_code_cli/loop.py]
  missing: ["Investigate dialog input latency under concurrent streaming output (prompt_toolkit app competing with patch_stdout re-render churn from the other worker); repro: mid-turn dialog + heavy streaming, measure key-to-highlight latency and Enter loss. Fix direction unknown — needs diagnosis. Strike if not reproducible."]
- gap_id: G-7-4
  truth: "Approval dialogs identify their agent and request (transparency: side content never presented ambiguously)"
  status: resolved
  resolved_by: 07-04-PLAN.md
  resolved_at: 2026-10-07
  reason: "User reported: with several approvals in a row, could not tell which Approve? box belonged to main vs side. The 'Approval needed: [tag]' header carries the tag but the interactive dialog box itself does not."
  severity: medium
  test: 4
  artifacts: [strands_code_cli/policy_gate.py, strands_code_cli/choice.py]
  missing: ["Carry the [main]/[btw] tag plus a short request descriptor (tool + detail snippet) into the Approve? dialog title/header so each box is self-identifying in multi-dialog flows. User suggestion: consider rendering the dialog (or its response echo) as fenced --- lines in the btw-block style so identity reads the same way everywhere."]
