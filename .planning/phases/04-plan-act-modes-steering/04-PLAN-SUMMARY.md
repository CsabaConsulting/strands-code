---
phase: 04-plan-act-modes-steering
plan: 04
subsystem: plan-act-modes-steering
tags: [plan-mode, act-mode, classifier-deny, boundary-steering, two-press-cancel, tracer]
requires: [MODE-01, MODE-02, LOOP-02, LOOP-04]
provides: [read-only-plan, approve-handoff, mode-cycling, steering-hook, cancel-flush, mode-commands]
affects: [07-btw-side-channel]
tech-stack:
  added: []
  patterns: [classifier-deny-mode-flag, explicit-steering-state, raw-readline-input-thread, caller-owned-cancel-event, reply-only-mode-routes]
key-files:
  created:
    - strands_code_cli/mode.py
    - strands_code_cli/steering.py
    - tests/test_mode.py
    - tests/test_steering.py
    - tests/test_plan_cancel.py
  modified:
    - strands_code_cli/policy_gate.py
    - strands_code_cli/main.py
    - strands_code_cli/loop.py
    - strands_code_cli/router.py
    - strands_code_agent/code_agent.py
key-decisions:
  - Classifier-deny (Option B) is the Plan enforcement core, prompt prefix defense-in-depth; single agent, mode flips via setter
  - Approve command is /approve (not /act — collides with /mode act); gated on a pending plan
  - Raw sys.stdin.readline daemon thread for steering input (not a second prompt_toolkit app); gate_open flag keeps keystrokes out of y/n prompts
  - Two-press Ctrl-C with 5 s window and honest copy (request vs confirm, no resume promise); Ctrl-C-in-prompt stays deny-this-tool
  - SteeringState is an explicit object threaded through run_loop, not a module _ACTIVE registry
requirements-completed: [MODE-01, MODE-02, LOOP-02, LOOP-04]
duration: unexecuted (plan only)
completed: 2026-09-25
---

# Phase 04 Plan 04: Plan/Act Modes + Steering Summary

Single plan covering Phase 4: read-only Plan mode enforced by a
classifier-deny flag on the single-HITL spine, explicit `/approve`
handoff to Act, session-sticky `/mode` cycling, anytime steering via a
`BeforeToolCallEvent` cancel_tool hook fed by a raw-readline input
thread, and two-press Ctrl-C cancel with cancel-time flush — tracer
slice first, then parallel waves, all on replay models (no live
Bedrock).

## Accomplishments (planned)

- Tracer proves Plan-deny, hook-before-prompt ordering, steering
  redirect without re-entrancy, SIGINT surfacing, cancel flush, and
  `/mode`+`/approve` routing — observations recorded in test
  docstrings.
- `mode.py` holds session-sticky `ModeState` (default act) plus the
  step-list `PLAN_PREFIX`; router gains reply-only `/mode` and
  `/approve`.
- `PolicyClassifier.set_mode` denies write/edit/shell/python_repl in
  Plan with mode vocabulary only, above the trust_delegated return.
- `steering.py` holds explicit `SteeringState`, the boundary hook, and
  the turn-owned readline reader with gate-open buffering.
- `run_loop` owns per-turn steering lifecycle plus the caller-owned
  cancel event and two-press state machine; cancel flushes the
  session.

## Key decisions

- `/approve` over `/act`; Plan-deny above trust_delegated; deny-this-tool
  for Ctrl-C-in-prompt; 5 s second-press window; in-memory mode only.
- One costly reversibility (D-09 boundary machinery), rest reversible;
  no one-way doors, so no checkpoints.

## Risks carried forward

- Long no-tool model streams delay steering (named UX limit, no
  machinery fix); readline v1 loses line editing on the steering line.
- `python_repl` interior acts still all-or-nothing (now default-denied
  in Plan); programmatic_tool_caller pin stays off.
- Mode vocabulary lock holds — Phase 5/6/7 must not reuse plan/act
  words for policy, diff, or auto modes.

## Scope fenced out

General auto/yolo mode, `/btw` side-channel, model/cost/context
commands, skills/memory, rollback journals, resume-of-cancelled-task
— verification ends with a bleed grep before merge.
