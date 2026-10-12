---
status: diagnosed
phase: 08-model-routing-with-decision-models
source: [08-VERIFICATION.md]
started: 2026-10-12T08:05:00Z
updated: 2026-10-12T10:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Run `python3 scripts/uattest/driver.py r2`, `r3`, `r4` (tmux + OPENROUTER_API_KEY + Ollama + Bedrock)
expected: R2/R3/R4 PASS — live local-engine route, /model override respect, side-ask parity against real engines
result: issue
reported: "r3 TIMEOUT waiting for main-end; r4 TIMEOUT waiting for side-spawn 'Side question noted' (tracebacks in chat; transcripts /tmp/uatr8/r3.log, r4.log)"
severity: blocker

### 2. Re-run `python3 scripts/uattest/driver.py r1` after the GAP-01 loader fix (regression)
expected: R1 PASS (was green pre-fix; confirms the loader change did not regress the cloud path)
result: pass

### 3. Run `python3 scripts/route-probe.py --run openrouter && python3 scripts/route-probe.py --run local && python3 scripts/route-probe.py --compare`
expected: 20+20 JSONL verdicts, exit 0, no model-verdict drift vs evals/routing-probe/baseline.json
result: pass

## Summary

total: 3
passed: 2
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-08-1
  truth: "R2/R3/R4 PASS — live local-engine route, /model override respect, side-ask parity against real engines"
  status: failed
  reason: "User reported: r3 TIMEOUT waiting for main-end; r4 TIMEOUT waiting for side-spawn"
  severity: blocker
  test: 1
  root_cause: "Rig strategies hardcode bedrock/amazon.nova-micro-v1:0, whose base id supports only INFERENCE_PROFILE throughput in us-west-2 (confirmed via get-foundation-model); every routed turn to it fails at ConverseStream. r3 hung because wait_main_end watches only the cost line that failed turns never print (loop.py break skips record_turn_metrics). r4's main turn failed before the /btw stagger so the side ask landed on idle, where /btw is by design a main turn (router D-01). No product bug."
  artifacts:
    - path: "scripts/uattest/driver.py"
      issue: "write_strategy blocks (r2/r3/r4) hardcode throughput-incompatible Bedrock id; wait_main_end/wait_routed lack fail-fast on 'Turn failed'"
  missing:
    - "Replace rig candidate with bedrock/us.amazon.nova-micro-v1:0 (ACTIVE SYSTEM_DEFINED profile, validated invokable-form)"
    - "Fail fast in rig on 'Turn failed' instead of hanging to timeout"
    - "Restore poisoned global default model (done during diagnosis)"
  debug_session: .planning/debug/rig-bedrock-model-id.md
  diagnosis: >-
    Single root cause, rig/env-side, no product bug. Rig strategies hardcode
    candidate bedrock/amazon.nova-micro-v1:0, which Bedrock rejects in this
    account/region (ValidationException: on-demand throughput unsupported, needs
    an inference profile). Routing behaved correctly in every log (decision +
    Routed line + both confidences). r3: turn failed at Bedrock so no cost line
    was printed and wait_main_end timed out. r4: main turn failed in <6s so the
    /btw landed on the idle prompt, where idle /btw is by design a normal main
    turn (router.py D-01), hence no 'Side question noted' and no '(btw)' marker.
    r2 log shows a full green flow (confirmation of exit code pending).
    Fix direction: rig strategies must use Bedrock ids invokable here
    (inference-profile form or another cheap id); optionally fail fast in the
    rig on 'Turn failed' for better diagnostics.
