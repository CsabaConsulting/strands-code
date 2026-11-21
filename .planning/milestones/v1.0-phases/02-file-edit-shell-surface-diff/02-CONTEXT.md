# Phase 2: File/Edit/Shell Surface + /diff - Context

**Gathered:** 2026-09-24
**Status:** Ready for planning

## Phase Boundary

The agent gains hands: first-class file and shell actuation plus reviewable changes. In scope: wiring strands-agents-tools, the `/diff` review gate with a user-selectable mode, shell with a default directory scope, and grep for agent and user. Out of scope: permissions enforcement (Phase 3), modes (Phase 4), persistent indexes (later phase).

## Implementation Decisions

### Tool provenance
- **D-01:** File and shell capabilities come from `strands-agents-tools` wired into the harness, not from extending `python_repl`.
- **D-02:** The full surface lands in this phase: read, write/edit, and shell together.
- **D-03:** The agent MUST keep source-code write ability at least for the local folder and subfolders. Writes may flow through the dedicated file tools rather than generated Python; `python_repl`'s exact remaining role is the planner's call.

### /diff semantics
- **D-04:** The user selects the diff mode: approve-each, on-demand, or auto. Granularity follows the mode: per-hunk when careful, whole-change normally, no gate in auto. Mode-switch mechanics are the planner's call.
- **D-05:** A general auto/yolo mode covering ALL tool calls is explicitly out of scope — mode-system territory, likely Phase 4.

### Shell scope
- **D-06:** Full shell from day one; Phase 3 gates the dangerous parts.
- **D-07:** Default filesystem scope is cwd + subdirs + `/tmp`. Expansion beyond that (e.g. sibling repos) is permission-gated — **Reversibility:** costly — the default scope shapes every tool sandbox and the Phase 3 policy file; widening later re-opens reviewed decisions.

### Grep UX
- **D-08:** Both: the agent greps on its own during tasks, and the user gets an explicit `/search` command.
- **D-09:** Lexical grep plus on-the-fly symbol navigation (definitions/references); no embeddings, persistent index stays deferred.

### the agent's Discretion
- `python_repl`'s exact remaining role alongside the new tools (D-03).
- Diff mode-switch mechanics (command vs config) and per-hunk UI shape (D-04).

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project definition
- `.planning/PROJECT.md` — product vision, core value, constraints
- `.planning/REQUIREMENTS.md` — TOOL-01, TOOL-02, TOOL-04 (this phase); all other REQ-IDs belong elsewhere
- `.planning/ROADMAP.md` — Phase 2 goal, success criteria, dependencies
- `.planning/research/SUMMARY.md` — Implications for Roadmap: Phase 2 slice (prefer strands-tools, `/diff` viewer); pitfall review (runaway loops, destructive actions — Phase 3 owns enforcement)

### Prior phase (locked)
- `.planning/phases/01-session-wiring-repl-skeleton/01-CONTEXT.md` — harness-first, straight-to-REPL, `output_context` raw stdout (all turn output flows through it), Bedrock-or-stop entry

### Codebase orientation
- `.planning/codebase/ARCHITECTURE.md` — agent/composition vs execution layers; where tool wiring connects
- `.planning/codebase/STACK.md` — `strands-agents` 1.57.0, `strands-harness` 0.1.2, `uv` toolchain, pytest gate
- `strands_code_cli/` — current CLI surface (loop, router, session_index); new tools compose here

## Existing Code Insights

### Reusable Assets
- `SandboxedPythonInterpreter` (`strands_code_agent/python_environments/local_sandboxed.py`): allowlist + timeout pattern for the tool sandbox conversation
- `SessionIndex` (`strands_code_cli/session_index.py`): sidecar-JSON pattern if `/diff` needs pending-change state
- `output_context` (`strands_code_cli/output.py`): all turn output must flow through raw stdout

### Established Patterns
- Constructor-kwarg configuration: tool options arrive via constructors, not env sniffing
- Sidecar JSON for derived state, snapshots stay SDK-owned

### Integration Points
- `create_harness(tools=[...])` in `strands_code_cli/main.py:build_agent`: new tools register here
- `dispatch` in `strands_code_cli/router.py`: `/diff` and `/search` route here

## Specific Ideas

No specific requirements — open to standard approaches. Claude Code's diff/grep UX is the reference model.

## Deferred Ideas

- General auto/yolo mode covering all tool calls — mode-system territory, likely Phase 4.

---

*Phase: 2-File/Edit/Shell Surface + /diff*
*Context gathered: 2026-09-24*
