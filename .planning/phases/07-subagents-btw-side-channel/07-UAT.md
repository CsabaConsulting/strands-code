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
  missing: ["Nesting count in ApprovalBroker.pump: __exit__ unconditionally clears _pumping, wiping the session pump's entered state when the turn pump exits; every later idle side approval takes the inline prompt() path on the SDK worker thread where prompt_toolkit fails. Fix: refcount enter/exit; regression test enter-session/exit-turn then assert still-pumping + enqueue-not-inline."]
- gap_id: G-7-1b
  truth: "Side agent answers ONLY the btw question and never continues the main task (D-04/D-09 scope)"
  status: failed
  reason: "User reported: side agent, after listing /tmp, issued python_repl containing the MAIN essay task inside the btw fence; essay rendered twice (main + btw)"
  severity: high
  test: 1
  artifacts: [strands_code_cli/btw.py]
  missing: ["Fork carries the main user message with no assistant response yet; BTW_FRAMING does not bound scope strongly enough, so the model adopts the unanswered main task after finishing the side question. Fix direction: explicit scope boundary in framing (answer ONLY the trailing btw question, end turn when answered) and/or mark the in-flight main turn in the fork. Verify live."]
- gap_id: G-7-2
  truth: "Cancel with an approval dialog in flight cancels cleanly: no orphan dialogs, no dialog storms, no internal exceptions (D-08)"
  status: failed
  reason: "User reported: (a) dead side's Approve? dialog popped after cancel-side and trapped user till main finished; (b) repeated Approve? dialogs + second chooser + 'btw failed (EventLoopException)' after cancel-side with queued approvals; (c) cancel-both waited for main natural finish"
  severity: high
  test: 2
  artifacts: [strands_code_cli/loop.py, strands_code_cli/policy_gate.py]
  missing: ["Hypotheses (verify in fix plan): (a) pump dequeues side request then cancel lands — WR-03 discard only covers waiter-side abort, pump still runs the dialog for a dead worker; pump must skip requests whose tag event is set. (b) dead worker's LATER queued requests are never discarded — discard one covers only the current waiter request; need tag-wide purge on cancel. Second chooser likely user mashing Ctrl-C while stuck — consider chooser re-entry guard. EventLoopException must map to clean 'Cancelled by user' rendering. (c) cancel-both join waits on worker cancel granularity — confirm SDK behavior, consider prompt cancel responsiveness."]
- gap_id: G-7-4
  truth: "Approval dialogs identify their agent and request (transparency: side content never presented ambiguously)"
  status: failed
  reason: "User reported: with several approvals in a row, could not tell which Approve? box belonged to main vs side. The 'Approval needed: [tag]' header carries the tag but the interactive dialog box itself does not."
  severity: medium
  test: 4
  artifacts: [strands_code_cli/policy_gate.py, strands_code_cli/choice.py]
  missing: ["Carry the [main]/[btw] tag plus a short request descriptor (tool + detail snippet) into the Approve? dialog title/header so each box is self-identifying in multi-dialog flows. User suggestion: consider rendering the dialog (or its response echo) as fenced --- lines in the btw-block style so identity reads the same way everywhere."]
