---
status: complete
phase: 07-subagents-btw-side-channel
source: [07-VERIFICATION.md]
started: 2026-10-06T09:05:00Z
updated: 2026-10-07T06:20:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Start a long main task, fire /btw needing approval, let main finish first
expected: Tagged [btw] prompt is announced at idle ('btw approval needed — will prompt when the next turn starts.') and served by the next turn's pump; fenced block lands without scrambling the prompt line
result: issue
reason: "Mid-turn shell approval worked, but after main finished: (1) side's python_repl approval denied itself with CONFIRMATION_FAILED + RuntimeWarning instead of announce+defer; (2) side agent executed the MAIN essay task inside the btw fence (python_repl with essay content). Digest did land at the end."

### 2. Run main + btw concurrently, press Ctrl-C once
expected: Chooser offers main/btw/both and cancels only the named target (ESC cancels nothing)
result: issue
reason: "Chooser routing correct in all attempts (cancel-main, cancel-both, and no-approval cancel-side all behaved). BUT cancel racing an approval dialog breaks: (a) after cancel-side, the dead side's Approve? dialog still popped and trapped the user until main finished; (b) cancel-side with queued approvals produced repeated Approve? dialogs + a second chooser + 'btw failed (EventLoopException)' instead of clean cancel; (c) cancel-both waited for main to finish naturally. Also side ran main's 'sleep 30' (G-7-1b again)."

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
passed: 4
issues: 2
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-7-1a
  truth: "Idle side approvals announce once and wait for the next turn's pump (D-11 bounded-wait)"
  status: failed
  reason: "User reported: side python_repl approval after main-end denied itself (CONFIRMATION_FAILED + RuntimeWarning: run_async never awaited) instead of announcing 'will prompt when the next turn starts'"
  severity: critical
  test: 1
  artifacts: [strands_code_cli/policy_gate.py]
  missing: ["DIAGNOSED (.planning/debug/DEBUG-g-7-1a.md): confirmed — pump.__exit__ (policy_gate.py:233-236) unconditionally clears _pumping (sole clear site repo-wide), wiping the still-entered session pump (loop.py:1447-1449; design intent at 1438-1441 says turn pumps nest inside it). Every later idle side approval takes inline prompt() on the SDK worker thread where asyncio nesting fails → deny; has_pending stays False so BTW_IDLE_APPROVAL never prints. Fix: nesting refcount in pump enter/exit; regression test enter-session/exit-turn then assert still-pumping + enqueue-not-inline."]
- gap_id: G-7-1b
  truth: "Side agent answers ONLY the btw question and never continues the main task (D-04/D-09 scope)"
  status: failed
  reason: "User reported: side agent, after listing /tmp, issued python_repl containing the MAIN essay task inside the btw fence; essay rendered twice (main + btw)"
  severity: high
  test: 1
  artifacts: [strands_code_cli/btw.py]
  missing: ["DIAGNOSED (.planning/debug/DEBUG-g-7-1b.md): confirmed + sharpened — spawn snapshots live history incl. the unanswered main directive (loop.py:572-574); the absorb branch (btw.py:168-172) MERGES main directive + btw question into ONE trailing user turn (upstream _with_history never meets this case: harness children spawn inside tool calls where trailing user turns are already-answered toolResults); neither BTW_FRAMING (btw.py:63-66) nor BTW_FORK_PREAMBLE (btw.py:69-72) forbids performing earlier turns, and CODE_AGENT_INSTRUCTIONS says 'solve tasks'. Attribution proven real (not render leak): [btw] tag classifies by agent identity. Recommended fix A+B: harden framing (ONLY + do-not-perform-main) AND mark the in-flight non-toolResult user turn as context-only; exclusion (C) as fallback if live repro still fails. Verify live."]
- gap_id: G-7-2
  truth: "Cancel with an approval dialog in flight cancels cleanly: no orphan dialogs, no dialog storms, no internal exceptions (D-08)"
  status: failed
  reason: "User reported: (a) dead side's Approve? dialog popped after cancel-side and trapped user till main finished; (b) repeated Approve? dialogs + second chooser + 'btw failed (EventLoopException)' after cancel-side with queued approvals; (c) cancel-both waited for main natural finish"
  severity: high
  test: 2
  artifacts: [strands_code_cli/loop.py, strands_code_cli/policy_gate.py]
  missing: ["DIAGNOSED (.planning/debug/DEBUG-g-7-2.md): RC-1 CONFIRMED — _ApprovalRequest untagged (policy_gate.py:162), all 3 pump serve sites unconditional (loop.py:470/506/641), pump wins race vs waiter 50ms poll → dialog for dead worker; fix F-1 tag requests + pump-side skip on set tag event. RC-2 PARTIALLY REFUTED — queue holds at most one req per live worker, no tag-wide purge needed. RC-3 CONFIRMED no-fix — second chooser is by-design escalation (Ctrl-C inside phantom dialog); dies with F-1. RC-4 CONFIRMED extends — SDK wraps TurnCancelled in EventLoopException so our except-TurnCancelled sites are dead for real agents; fix F-2 unwrap + map to clean cancel rendering. RC-5 CONFIRMED half-by-design — cancel join waits on SDK step granularity; fix F-3 ack-before-join + doc, no thread preemption."]
- gap_id: G-7-4
  truth: "Approval dialogs identify their agent and request (transparency: side content never presented ambiguously)"
  status: failed
  reason: "User reported: with several approvals in a row, could not tell which Approve? box belonged to main vs side. The 'Approval needed: [tag]' header carries the tag but the interactive dialog box itself does not."
  severity: medium
  test: 4
  artifacts: [strands_code_cli/policy_gate.py, strands_code_cli/choice.py]
  missing: ["Carry the [main]/[btw] tag plus a short request descriptor (tool + detail snippet) into the Approve? dialog title/header so each box is self-identifying in multi-dialog flows. User suggestion: consider rendering the dialog (or its response echo) as fenced --- lines in the btw-block style so identity reads the same way everywhere."]
