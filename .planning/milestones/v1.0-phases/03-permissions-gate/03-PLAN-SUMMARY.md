---
phase: 03-permissions-gate
plan: 03
subsystem: permissions-gate
tags: [human-in-the-loop, toml-policy, deny-first, batch-approval, diff-coordination, tracer]
requires: [TOOL-03]
provides: [policy-store, single-hitl-gate, batch-state, policy-commands, repl-gating]
affects: [04-plan-act-modes]
tech-stack:
  added: []
  patterns: [DiffConfig-persistence-mirror, single-HITL-classifier-plus-ask, turn-scoped-approval-cache, gate-subsumes-approve-each]
key-files:
  created:
    - strands_code_cli/policy.py
    - strands_code_cli/policy_gate.py
    - tests/test_policy.py
    - tests/test_policy_gate.py
  modified:
    - strands_code_cli/main.py
    - strands_code_cli/loop.py
    - strands_code_cli/router.py
    - strands_code_cli/scope.py
    - strands_code_cli/diff_gate.py
    - strands_code_agent/code_agent.py
key-decisions:
  - Exactly one HumanInTheLoop (allowlist + custom classifier + custom ask); "smart"/NL/Cedar ruled out by D-05
  - Repo policy layers over home (union, deny-wins); corrupt fails closed to prompt-all, symlink fails loud
  - Deny rules hard-deny naming the rule; D-04 as per-turn rule-key cache (sequential calls can't pre-list)
  - Gate subsumes approve-each via gate_active flag; /diff apply never re-prompts (router-side write)
  - programmatic_tool_caller pinned-off-or-proven-gated by tracer; python_repl approval is all-or-nothing
requirements-completed: [TOOL-03]
duration: unexecuted (plan only)
completed: 2026-09-25
---

# Phase 03 Plan 03: Permissions Gate Summary

Single plan covering Phase 3: a deny-first approval gate over every side
effect, driven by a deterministic TOML allow/deny policy (home default +
repo layer), enforced through exactly one `HumanInTheLoop` carrying a
custom classifier (TOML matching) and a custom ask (full-detail prompt,
batch cache, remember-me) — tracer slice first, then parallel waves.

## Accomplishments (planned)

- Tracer proves single-HITL construction, live deny-skip-and-continue,
  and the liveness/gating of `web_fetch`/`web_search`/
  `programmatic_tool_caller` (pinned off if its inner calls bypass the gate).
- `policy.py` mirrors `DiffConfig` (platformdirs home, atomic save,
  symlink refusal) in TOML via stdlib `tomllib`; layered home+repo merge;
  pure match engine with deny-wins, `sh -c` normalisation, and
  GET-vs-upload network classification.
- `policy_gate.py` holds the classifier, the `output_context` ask with
  `always`/`never` narrow-rule append, the per-turn `BatchState` cache,
  and the sole HITL builder plus main-agent/turn binders.
- `build_agent` wires `interventions=[...]`; wrappers run `gate_active`
  so approve-each never double-prompts; `/policy show|last` inspect;
  scope confine admits policy-granted roots; `python_repl` prompts with
  code shown; delegated turns prompt unless `trust_delegated` is set.

## Key decisions

- Layered union over home-replace (replacing home would silently drop
  home denies); hard-deny over prompt-on-deny (prompting defeats
  deny-first); turn-cache over time-window batching (unverifiable timing).
- `diff_gate` bool ask untouched (Phase 2 locked); remember-write lives
  in the HITL ask, `evaluate` stays default; no `enable_trust`.
- Zero one-way doors (schema/layering are costly but migratable), so no
  checkpoints.

## Risks carried forward

- `sh -c`/VAR-indirection/exotic-binary evasion accepted per D-14;
  `python_repl` interior acts unconfined (all-or-nothing approval).
- GET-param exfiltration accepted per D-15; host allowlist deferred.
- Shell 120 s upstream timeout still unpinned (02 residual, livelier now).
- `policy.toml` vocabulary frozen — Phase 4 Plan/Act must not reuse it
  (RESEARCH risk 10).

## Scope fenced out

Phase 4 mode system (no plan/act/yolo/auto words in schema), semantic/LLM
classification, host allowlist, natural-language policy — verification
ends with a grep for `smart`, `LLMClassifier`, `cedar`, `enable_trust`,
mode words, `yolo`, `strands_tools` in the diff.
