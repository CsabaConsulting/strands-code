---
status: complete
phase: 06-skills-memory-file
source: [06-UAT-round2.md]
round: 3
started: 2026-10-05T09:00:00Z
updated: 2026-10-05T09:30:00Z
---

## Current Test

[testing complete — round 3: 1 passed, 1 issue, 0 pending]

## Tests

### 1. Markup-safe reply
expected: /[/] replies Unknown command '/[/]' plus usage, rendered literally, session survives
result: pass

### 2. Reloaded skill trusted
expected: New skill created mid-session, after /skills reload the model sees it in its skills tool and follows it (no 'no such skill exists' refusal)
result: issue
reported: "Model confirmed 'greeter2 is a legitimate available skill in my system' (registry refresh works) but still refused to follow it, citing the untrusted marker plus memory-stored refusal principles ('user values critical thinking over blind obedience')"
severity: major
note: "Registry half PASSED. Remaining refusal is a trust-framing defect (new gap G-6-R3-2). Side observation: /skills now shows a literal backslash ('test \\[/] markup') — the round-1 escape() calls are redundant under print_plain and must be reverted (cosmetic, fold into fix round)."

## Summary

total: 2
passed: 1
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- gap_id: G-6-R3-2
  truth: "An explicitly invoked skill is followed as the task"
  status: fixed
  reason: "User reported: model acknowledges the reloaded skill as legitimate but refuses to follow it, citing the untrusted-content marker and memory-stored refusal principles"
  severity: major
  test: 2
  root_cause: "The composed prompt led with an absolute untrusted marker ('verify before acting') with no notion of explicit user invocation, so a diligent model verified and refused the very task the user chose. Round-2 refusal rationalizations were also memorialized as user preferences, so memory actively instructed refusal (contained to /tmp/uattest memory; user to clean before retest)."
  fix: "Composed prompt reframed around explicit invocation (user chose this skill; follow it; do not re-check the skills tool) with distrust scoped to embedded third-party directives contradicting the task. T-06-02 updated: marker softened by user approval, deny-first gate remains the hard control. Proven by updated routing assertions. LIVE-VERIFIED 2026-10-05: after memory wipe, /local:greeter2 complied ('Hello there, friend!') with the model articulating the explicit-invocation distinction. Redundant escape() calls reverted (print_plain renders verbatim)."
  artifacts: []
  missing: []
