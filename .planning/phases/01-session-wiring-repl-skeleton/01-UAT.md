---
status: testing
phase: 01-session-wiring-repl-skeleton
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md]
started: 2026-09-24T07:45:00Z
updated: 2026-09-24T07:45:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 1
name: Fresh launch smoke test
expected: |
  Run strands-code in a terminal with no prior sessions. REPL boots without errors, shows the conversation prompt, and --help documents --session-id. (Needs AWS creds for live asks; prompt-only checks work without.)
awaiting: user response

## Tests

### 1. Fresh launch smoke test
expected: Run strands-code with no prior sessions. REPL boots without errors, shows the conversation prompt, and --help documents --session-id.
result: [pending]

### 2. Ask and follow up in one conversation
expected: Type an ask, watch a streamed agent answer, then ask a follow-up that continues the same session.
result: [pending]

### 3. Resume a session by UUID
expected: Re-launch with --session-id of a previous session and continue where it left off, transcript intact.
result: [pending]

### 4. Cancel and exit cleanly
expected: Ctrl-C cancels the current line without quitting; Ctrl-D exits cleanly with state saved.
result: [pending]

### 5. Resume picker at launch
expected: Launch with existing sessions shows a numbered picker (recent plus start-new); picking one resumes it.
result: [pending]

### 6. Slash commands dispatch
expected: /resume lists sessions, /rename renames the current one, /exit leaves; an unknown slash command shows a usage hint instead of an agent turn.
result: [pending]

### 7. Rename sticks, auto-title fills once
expected: After the first exchange the session gets an auto-title; renaming it keeps the custom name on later turns.
result: [pending]

### 8. First run without AWS credentials stops safely
expected: With no AWS credentials, launch stops with a Bedrock setup pointer (exit 2) and creates no session artifacts.
result: [pending]

### 9. Live SIGKILL mid-idle restores on relaunch
expected: Kill -9 the CLI mid-idle, relaunch with the same session id, transcript plus working plan are intact.
result: [pending]

### 10. First-run Bedrock-or-stop gate with zero side effects
expected: First-run Bedrock-or-stop gate runs before construction with zero side effects
result: pass
source: automated
coverage_id: D1

### 11. Provider choice persists in YAML config
expected: Provider choice persists in YAML config for Phase 5 to inherit
result: pass
source: automated
coverage_id: D2

### 12. SIGKILL mid-idle resumes without exit flush
expected: SIGKILL mid-idle resumes transcript plus agent state without exit flush
result: pass
source: automated
coverage_id: D3

### 13. Clean exit saves deterministically
expected: Clean exit explicitly saves and bumps index recency deterministically
result: pass
source: automated
coverage_id: D4

## Summary

total: 13
passed: 4
issues: 0
pending: 9
skipped: 0
blocked: 0

## Gaps

[none yet]
