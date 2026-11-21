---
status: complete
phase: 11-codeact-action-interface
source: [11-01-SUMMARY.md, 11-02-SUMMARY.md, 11-03-SUMMARY.md]
started: 2026-10-15T00:00:00Z
updated: 2026-10-15T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Start the CLI from scratch; it boots without errors and a basic turn runs (main.py was modified this phase).
result: pass
evidence: User transcript — booted to REPL, comparison turn ran, usage line + cost shown. (reasoningContent x7 lines are a pre-existing provider warning, not a phase regression.)

### 2. Interface label on every turn (11-01 D3)
expected: Every turn prints its interface label naming the interface used — confirm one 'interface: tool/codeact' line per turn in a live session. (Exact label strings are unit-tested; the run_loop print site executes only in a live REPL turn.)
result: pass
evidence: User transcript — 'interface: tool' on both the first turn and a follow-up turn (after /model switch).

### 3. Startup default and switch persistence (11-01 D4)
expected: Sessions start on tool-calling unless --codeact or remember-last config says otherwise; switches apply next-ask and persist. Confirm with one live --codeact start plus a /codeact switch and restart.
result: pass
retest: 2026-10-16 after 11-04 fix (user transcript: bare --codeact booted, /codeact reports code; orchestrator: driver.py a1 -> A1 PASS)
evidence: Core behaviors confirmed by user transcript — fresh start defaults to tool, --codeact code starts on code, /codeact tool switches with announcement. Bare/import questions resolved as designed (see chat). G-11-1 closed.

### 4. Stint reset on live switch (11-02 D2)
expected: Stint REPL persists within the stint, resets on switch, never bleeds into tool turns. Confirm one live /codeact switch starts a fresh stint.
result: pass
evidence: User transcript with random-value discrimination — bare print(x) returned 996654 within stint, NameError after /codeact tool + /codeact code. (First attempt inconclusive: model reconstructed x from context; re-ran with exact-code phrasing.)

### 5. Live code turn executes in stint (11-02 D3)
expected: Code turns execute through the stint interpreter; tool turns use the always-on interpreter unchanged. Confirm one live code turn executes in the stint and the next tool turn is unshaped.
result: pass
evidence: User transcript — code turn ran in stint (random 929079), then /codeact tool + normal ask answered unshaped with 'interface: tool'.

### 6. /codeact toggle with transcript announcement (11-01 D1)
expected: /codeact toggles the session interface with a transcript announcement; bare reports, invalid verbs stay safe.
result: pass
source: automated
coverage_id: 11-01-D1

### 7. Code prefix at send, tool turns byte-identical (11-01 D2)
expected: Code turns carry the code-first prefix at send; tool turns are byte-identical to today.
result: pass
source: automated
coverage_id: 11-01-D2

### 8. Switching never mutates history (11-01 D5)
expected: Switching interfaces never mutates conversation history.
result: pass
source: automated
coverage_id: 11-01-D5

### 9. session_turns and /cost rows unchanged (11-01 D6)
expected: session_turns row shape and /cost rows unchanged by interface records.
result: pass
source: automated
coverage_id: 11-01-D6

### 10. Stint-scoped sandbox with file/shell parity (11-02 D1)
expected: Code turns run in a stint-scoped sandbox with file/shell parity functions.
result: pass
source: automated
coverage_id: 11-02-D1

### 11. Both-mode /code /tool routing (11-02 D4)
expected: Both-mode routes each ask explicitly via /code or /tool; bare asks get the routing usage reply.
result: pass
source: automated
coverage_id: 11-02-D4

### 12. No prompts on execution path (11-02 D5)
expected: No approval prompt, dialog, or stdin read exists anywhere on the execution path.
result: pass
source: automated
coverage_id: 11-02-D5

### 13. Suite green with stint changes (11-02 D6)
expected: Full suite stays green with the stint, swap, and routing changes merged.
result: pass
source: automated
coverage_id: 11-02-D6

### 14. Whole-block approval preview (11-03 D1)
expected: Code approvals preview the full block with one prompt per code action.
result: pass
source: automated
coverage_id: 11-03-D1

### 15. Denial revise hint (11-03 D2)
expected: Denials feed a revise hint back into the live turn.
result: pass
source: automated
coverage_id: 11-03-D2

### 16. One rule system for CodeAct (11-03 D3)
expected: Always/Never rules apply to CodeAct approvals through the one policy.toml rule system.
result: pass
source: automated
coverage_id: 11-03-D3

### 17. python_repl plan-denied (11-03 D4)
expected: python_repl stays plan-denied regardless of interface with mode vocabulary only.
result: pass
source: automated
coverage_id: 11-03-D4

### 18. /cost identical for both interfaces (11-03 D5)
expected: /cost rows are byte-identical for tool and codeact turns.
result: pass
source: automated
coverage_id: 11-03-D5

### 19. Rules and history carry across switches (11-03 D6)
expected: Remembered rules and full history carry across interface switches unchanged.
result: pass
source: automated
coverage_id: 11-03-D6

### 20. Suite green with approval changes (11-03 D7)
expected: Full suite green with the approval and coherence changes merged.
result: pass
source: automated
coverage_id: 11-03-D7

## Summary

total: 20
passed: 20
issues: 0
pending: 0
skipped: 0

## Gaps

- gap_id: G-11-1
  truth: "Bare --codeact starts the session in code mode without requiring a value"
  status: closed-2026-10-16-test-3-retest-pass
  reason: "User reported: bare --codeact rejected with Option '--codeact' requires an argument; expects a value-less switch (or --codeact on/true)"
  severity: minor
  test: 3
  root_cause: "main.py declares codeact as a valued typer.Option (str|None) with membership validation, so Click rejects a bare --codeact before any project code runs. No flag_value/implied-value path exists."
  artifacts: ["strands_code_cli/main.py:211-222 (--codeact valued option + BadParameter validation)"]
  missing: ["Optional-value flag: bare --codeact implies code; explicit tool/code/both still accepted; invalid values still rejected pre-gate"]
