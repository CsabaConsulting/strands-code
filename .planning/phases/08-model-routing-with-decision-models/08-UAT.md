---
status: testing
phase: 08-model-routing-with-decision-models
source: [08-VERIFICATION.md]
started: 2026-10-12T08:05:00Z
updated: 2026-10-12T08:05:00Z
---

## Current Test

number: 1
name: Run `python3 scripts/uattest/driver.py r2`, `r3`, `r4` (tmux + OPENROUTER_API_KEY + Ollama + Bedrock)
expected: |
  R2/R3/R4 PASS — live local-engine route, /model override respect, side-ask parity against real engines
awaiting: user response

## Tests

### 1. Run `python3 scripts/uattest/driver.py r2`, `r3`, `r4` (tmux + OPENROUTER_API_KEY + Ollama + Bedrock)
expected: R2/R3/R4 PASS — live local-engine route, /model override respect, side-ask parity against real engines
result: [pending]

### 2. Re-run `python3 scripts/uattest/driver.py r1` after the GAP-01 loader fix (regression)
expected: R1 PASS (was green pre-fix; confirms the loader change did not regress the cloud path)
result: [pending]

### 3. Run `python3 scripts/route-probe.py --run openrouter && python3 scripts/route-probe.py --run local && python3 scripts/route-probe.py --compare`
expected: 20+20 JSONL verdicts, exit 0, no model-verdict drift vs evals/routing-probe/baseline.json
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
