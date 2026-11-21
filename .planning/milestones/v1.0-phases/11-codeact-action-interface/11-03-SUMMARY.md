---
phase: 11-codeact-action-interface
plan: "03"
subsystem: cli
tags: [codeact, approval-preview, policy-gate, deny-revise, coherence-pins]

requires:
  - phase: 11-codeact-action-interface/02
    provides: CodeactStint + per-turn swap + both-mode routing + turn_interfaces
provides:
  - Whole-block python_repl Syntax preview through the existing HITL verdict path
  - Deny revise-hint sentence on the policy-rule python_repl refusal
  - Rule-system + switching coherence pins (D-04/D-07/D-16/D-18/D-20)
affects: [codeact-executor, approval-preview, policy-persistence]

actuals:
  tokens: 4065
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns: [whole-block-approval-preview, deny-revise-hint, coherence-pin-tests]

key-files:
  created: [.planning/phases/11-codeact-action-interface/deferred-items.md]
  modified: [strands_code_cli/policy_gate.py, tests/test_policy_gate.py, tests/test_codeact.py]

key-decisions:
  - "Syntax preview replaces the Detail line in place for python_repl only; shell/file prompts stay byte-identical"
  - "Revise hint rides the policy-rule denial only; plan-deny stays byte-identical under the mode-vocabulary lock"
  - "D-07 pins use single-line blocks; the pre-existing multi-line TOML serialise gap is deferred, not fixed (tests-only task scope)"

patterns-established:
  - "Approval preview test double: monkeypatched module console with StringIO + padding-strip normalization (capsys escapes via StdoutProxy)"
  - "Interface-agnostic gate pins: switch a real CodeactState holder, then assert gate behavior unchanged"

requirements-completed: [TOOL-07]

coverage:
  - id: D1
    description: "Code approvals preview the full block with one prompt per code action"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_policy_gate.py#TestCodeactApprovalPreview::test_preview_carries_full_2000_char_block"
        status: pass
      - kind: unit
        ref: "tests/test_policy_gate.py#TestCodeactApprovalPreview::test_single_use_yields_exactly_one_prompt"
        status: pass
      - kind: unit
        ref: "tests/test_policy_gate.py#TestCodeactApprovalPreview::test_dialog_title_keeps_sixty_char_collapse"
        status: pass
    human_judgment: false
  - id: D2
    description: "Denials feed a revise hint back into the live turn"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_policy_gate.py#TestCodeactApprovalPreview::test_deny_carries_revise_hint_with_continue_verdict"
        status: pass
    human_judgment: false
  - id: D3
    description: "Always/Never rules apply to CodeAct approvals through the one policy.toml rule system"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_policy_gate.py#TestCodeactRuleCoherence::test_always_derives_narrow_python_repl_rule"
        status: pass
      - kind: unit
        ref: "tests/test_policy_gate.py#TestCodeactRuleCoherence::test_never_derives_python_repl_deny_rule"
        status: pass
    human_judgment: false
  - id: D4
    description: "python_repl stays plan-denied regardless of interface with mode vocabulary only"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_policy_gate.py#TestCodeactRuleCoherence::test_plan_deny_holds_on_both_interfaces"
        status: pass
    human_judgment: false
  - id: D5
    description: "/cost rows are byte-identical for tool and codeact turns"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactSwitchingCoherence::test_turn_rows_exclude_interface_across_turns"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactSwitchingCoherence::test_cost_report_byte_identical_across_interfaces"
        status: pass
    human_judgment: false
  - id: D6
    description: "Remembered rules and full history carry across interface switches unchanged"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactSwitchingCoherence::test_policy_file_byte_identical_across_switches"
        status: pass
      - kind: unit
        ref: "tests/test_codeact.py#TestCodeactSwitchingCoherence::test_messages_byte_identical_across_switch_with_stint_reset"
        status: pass
    human_judgment: false
  - id: D7
    description: "Full suite green with the approval and coherence changes merged"
    requirement: "TOOL-07"
    verification:
      - kind: unit
        ref: "uv run pytest tests/ -q (1541 passed, 11 deselected)"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-10-15
status: complete
---

# Phase 11 Plan 03: Whole-block approval plus coherence pins Summary

**Whole-block `python_repl` Syntax preview through the existing HITL verdict path, deny revise-hint with skip-and-continue, and D-04/D-07/D-16/D-18/D-20 coherence pins — classifier, batch, and rule-derivation logic untouched, full suite green.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-10-15T22:22:18Z
- **Completed:** 2026-10-15T22:27:55Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Approval prompts render the complete `python_repl` block as a `rich Syntax` python block in place of the 500-char `Detail` truncation (D-05, T-11-08); the 60-char dialog-title collapse is byte-identical and non-`python_repl` prompts are untouched
- Denied `python_repl` observations carry "Revise the code or try a different approach." with the standard skip-and-continue verdict, so the turn stays alive for revision (D-06)
- One rule system pinned: Always/Never derive the narrow 500-char prefix `Rule(tool="python_repl")` that match by prefix through a fresh batch (D-07, T-11-09)
- Plan gate mode denies `python_repl` on tool and code turns alike with mode vocabulary only and no prompt (D-04 natural fit, zero new mode logic)
- Switching coherence pinned: no `interface` key in turn rows, byte-identical `cost_report` across interfaces (D-16), policy-file bytes unchanged across switches with rules still deciding (D-18), messages length+content identical across switch+stint-reset (D-20)

## Task Commits

Each task was committed atomically:

1. **Task 1: Whole-block preview render plus deny revise hint** - `7a225d9` (feat)
2. **Task 2: Rule-system and switching coherence pins plus phase gate** - `359e4ea` (test)

**Plan metadata:** `docs: complete plan` (this SUMMARY — hash below)

## Files Created/Modified

- `strands_code_cli/policy_gate.py` - `Syntax` import, `REVISE_HINT` constant, whole-block preview branch + revise-hint refusal in `ask` (rendering only)
- `tests/test_policy_gate.py` - `TestCodeactApprovalPreview` (4 tests), `TestCodeactRuleCoherence` (4 tests incl. parametrized plan-deny)
- `tests/test_codeact.py` - `TestCodeactSwitchingCoherence` (4 tests: rows, cost-report, policy-file, messages)
- `.planning/phases/11-codeact-action-interface/deferred-items.md` (NEW) - pre-existing multi-line TOML serialise gap, logged out-of-scope

## Decisions Made

- Syntax preview replaces the `Detail` line in place for `python_repl` only (header first, then full block, then `Risk`): "replacing the truncation" means no duplicated half-preview, and the shell exact-lines test stays green.
- Revise hint rides the policy-rule denial only; plan-deny stays byte-identical under the mode-vocabulary lock (pinned by an absence assertion). The model-facing `CONFIRMATION_FAILED` observation is SDK-built from the classifier reason, which this plan forbids touching — the tested "deny observation" is the gate's refusal line.
- D-07 pins use single-line blocks: multi-line Always/Never exposes the pre-existing `_serialise_rule` no-escape gap (probe-verified tool-agnostic with a multi-line shell rule). Task 2 is explicitly tests-only, so the gap is logged to `deferred-items.md`, not fixed.
- Preview tests patch the module `console` with a StringIO console and strip Syntax width-padding: per-test `capsys` escapes via the StdoutProxy (same-file precedent), and Syntax pads lines to the console width.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `_serialise_rule` writes multi-line commands unescaped, invalidating the whole policy file on the next load (falls back to prompt-all defaults, silently dropping every remembered rule). Probe-verified pre-existing and tool-agnostic — not caused by this plan. Logged to `deferred-items.md` as `status: open` per the scope-boundary protocol; CodeAct makes it load-bearing since code blocks are routinely multi-line.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 11 plans 01–03 are complete: toggle + startup surfaces, stint execution + both-routing, and whole-block approval + coherence pins. TOOL-07 is fully covered; phase is ready for verify/transition.
- Verify-time manual checks carried from 11-01/11-02 coverage (live label line, live `--codeact` start + switch, live stint freshness) still stand; this plan adds no new live-only surface (preview render and hint are unit-pinned).
- Open follow-up (deferred, not blocking): escape multi-line commands in `_serialise_rule` before CodeAct Always/Never sees routine multi-line use.

---
*Phase: 11-codeact-action-interface*
*Completed: 2026-10-15*
