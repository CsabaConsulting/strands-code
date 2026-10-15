# Phase 11: CodeAct Action Interface - Context

**Gathered:** 2026-10-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Per ask or session, the user can choose the action interface: traditional gated tool-calling (default, unchanged), CodeAct code-generation-first, or both. CodeAct executes through the harness sandbox primitive with deny-first approvals gating whole code blocks; tool-calling stays the default and CodeAct is never mandatory. Switching interfaces mid-session keeps history and approvals coherent. In scope: interface selection surfaces, CodeAct execution path with whole-block approval, per-turn interface labeling, mid-session switching coherence. Out of scope: cost budgets/enforcement (locked: display only), per-effect in-execution approval prompts (rejected — whole-block only), fully automatic interface selection with no user choice (locked out).

</domain>

<decisions>
## Implementation Decisions

### Opt-in surface
- **D-01:** `/codeact` slash command is the primary interface switch (session toggle, like other session toggles).
- **D-02:** All three selection surfaces exist: `--codeact` startup flag, a config key, and `/codeact`.
- **D-03:** Every session starts on tool-calling; a global config option may switch the behavior to remember-last-choice. — **Reversibility:** costly — the default posture shapes the turn loop and session-start contract; flipping the default later changes every-session behavior.
- **D-04:** Mode-system integration only if it fits naturally without upsetting other mode logic; otherwise slash + flag + config only.

### Approval reconciliation
- **D-05:** Approvals gate the whole generated code block before execution (diff-like code preview, one prompt per code action). No per-effect prompts inside execution. — **Reversibility:** one-way — the approval-unit contract shapes the executor boundary and the prompt UX; splitting it later breaks the preview/approve interaction users learn.
- **D-06:** On denial, the agent revises: the denial feeds back and the agent can revise the code or try a different approach (the turn stays alive).
- **D-07:** Remembered Always/Never rules apply to CodeAct approvals exactly like tool approvals — one rule system.
- **D-08:** Approval prompts appear at the code-action boundary only, never nested inside a running orchestration step.

### CodeAct scope
- **D-09:** Full tool parity: generated code can call the same file/edit/shell tools as functions.
- **D-10:** Sandboxed local backend — reuse the library's `SandboxedPythonInterpreter` (smolagents allowlist + timeout); offline-safe, no new required backend.
- **D-11:** REPL state (variables, imports) persists across code actions within a CodeAct stint.
- **D-12:** Keep the library timeout defaults (180s agent / 60s interpreter); no user-visible timeout setting this phase.

### Both-mode meaning
- **D-13:** "Both" means the user routes per ask at send time — explicit, no model guessing. — **Reversibility:** costly — user-routed vs model-routed shapes the send path and turn setup; changing it later reworks the ask pipeline.
- **D-14:** One interface per turn; the turn's interface is fixed when the ask is sent (no mixing tool calls and code actions within a turn).
- **D-15:** The transcript labels each turn with the interface used (tool/codeact).
- **D-16:** `/cost` rows are identical for both interfaces — no interface column or split.

### Mid-session switching
- **D-17:** Switching interfaces resets the REPL; each CodeAct stint starts fresh.
- **D-18:** Remembered approval rules carry across switches unchanged.
- **D-19:** Switches apply at the next ask only; a running turn always finishes on its starting interface.
- **D-20:** Full conversation history is preserved across switches; only the action interface changes.

### the agent's Discretion
No "you decide" items — the user answered every question directly. Naming of the config key, exact `/codeact` UX wording, and transcript label format are left to planner/executor judgment within the locked decisions above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and roadmap
- `.planning/REQUIREMENTS.md` — TOOL-07 (opt-in CodeAct reconciled with deny-first approvals; tool-calling default, never mandatory)
- `.planning/ROADMAP.md` — Phase 11 goal, TOOL-07 requirement, 3 success criteria (per-session/per-task choice incl. both; sandbox + deny-first gating; coherent mid-session switching)

### Reusable CodeAct machinery (library)
- `strands_code_agent/code_agent.py` — Existing `python_repl`-first agent: toolkit merge, prompt assembly, tool registration
- `strands_code_agent/python_environments/base.py` — `PythonInterpreter` ABC + `get_tool()` observation contract
- `strands_code_agent/python_environments/local_sandboxed.py` — `SandboxedPythonInterpreter` (smolagents allowlist + timeout) — the D-10 backend

### Prior-phase precedents
- `.planning/phases/07-subagents-btw-side-channel/07-CONTEXT.md` — Escape gesture, subagent scope, main-task isolation (sequencing dependency)
- `.planning/phases/08-model-routing-with-decision-models/08-CONTEXT.md` — Session toggles, manual-wins posture, CodeAct deferred here
- `.planning/phases/04-*/04-CONTEXT.md` — Plan/Act modes + deny-first approval gate (D-04/D-08 integration context)

Note: `.planning/codebase/*.md` maps are stale (2026-09-22, pre-CLI layout) — researcher should verify current `strands_code_cli/` paths directly.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SandboxedPythonInterpreter` (`strands_code_agent/python_environments/local_sandboxed.py`): allowlisted imports + timeout via smolagents — the D-10 execution backend
- `PythonInterpreter.get_tool()` (`strands_code_agent/python_environments/base.py`): `python_repl` tool with STDOUT/STDERR observation formatting — the action interface to surface
- `CodeAgent` prompt assembly (`strands_code_agent/code_agent.py`): preamble/allowlist/system-prompt machinery to reuse for the CLI CodeAct path
- Phase 3 approval gate + Phase 2 `/diff` viewer: the D-05 whole-block preview/approve interaction model
- Phase 4 mode cycle + session toggles: the D-04 optional integration point (only if natural)

### Established Patterns
- Session-sticky toggles with manual user choice always winning (Phases 4/8) — D-01/D-02 follow this
- Deny-first approvals at action boundaries, never nested in orchestration (Phase 3/4) — D-08 follows this
- Display-only cost with identical row shapes (Phases 5/10) — D-16 follows this
- Harness-first execution, AWS-optional offline default — D-10 follows this (local sandbox, no AgentCore requirement)

### Integration Points
- CLI turn loop (`strands_code_cli/loop.py`): per-turn interface selection (D-13/D-14), switch-applies-next-ask (D-19)
- Approval gate: whole-block code preview + approve/deny + revise-on-deny (D-05/D-06/D-07)
- Transcript renderer: per-turn interface labels (D-15)
- Session startup + config: `--codeact` flag, config key, per-session default + global remember-last option (D-02/D-03)
- REPL lifecycle: persist within stint (D-11), reset on switch (D-17)

</code_context>

<specifics>
## Specific Ideas

- User explicitly rejected per-effect in-execution approval prompts after initially allowing them as a config option: "only per whole code block (diff presented), I don't want to complicate things" — keep the approval story to one prompt per code action.
- "Both" was a deliberate concern: user wants explicit user routing, not model-chosen interfaces — predictability over flexibility.

</specifics>

<deferred>
## Deferred Ideas

- Per-effect sandbox-pausing approvals (prompt when generated code attempts a side effect mid-execution) — considered during discussion, explicitly rejected; do not resurrect without re-discussing.
- AgentCore remote execution backend as a CodeAct option — not discussed; local-only this phase.
- Model-picks-interface-per-step ("both" as automatic) — rejected in favor of user routing (D-13).

None of the above belong in Phase 11 scope.

</deferred>

---

*Phase: 11-CodeAct Action Interface*
*Context gathered: 2026-10-13*
