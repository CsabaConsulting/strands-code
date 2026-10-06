---
status: testing
phase: 07-subagents-btw-side-channel
source: [07-VERIFICATION.md]
started: 2026-10-06T09:05:00Z
updated: 2026-10-06T09:05:00Z
---

## Current Test

number: 1
name: Start a long main task, fire /btw needing approval, let main finish first
expected: |
  Tagged [btw] prompt is announced at idle ('btw approval needed — will prompt when the next turn starts.') and served by the next turn's pump; fenced block lands without scrambling the prompt line
awaiting: user response

## Tests

### 1. Start a long main task, fire /btw needing approval, let main finish first
expected: Tagged [btw] prompt is announced at idle ('btw approval needed — will prompt when the next turn starts.') and served by the next turn's pump; fenced block lands without scrambling the prompt line
result: [pending]

### 2. Run main + btw concurrently, press Ctrl-C once
expected: Chooser offers main/btw/both and cancels only the named target (ESC cancels nothing)
result: [pending]

### 3. Fire /btw mid-task while main streams
expected: Fenced btw blocks arrive live with main output outside and no torn lines
result: [pending]

### 4. Review LOOP-03 safety prohibition: btw mutations face the same deny-first gate
expected: No weaker btw approval lane exists; trust_delegated auto-trust is announced in the transcript
result: [pending]

### 5. Review LOOP-03 transparency prohibition: side content never presented as main content
expected: Fences, prompts, history appends, /policy last entries all carry btw identity
result: [pending]

### 6. Review LOOP-03 memory-safety prohibition: side reasoning never memorialized as durable user memory
expected: Side agent recalls shared facts but never writes the fact store or curate queue
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
