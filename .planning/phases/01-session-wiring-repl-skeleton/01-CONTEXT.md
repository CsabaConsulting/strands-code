# Phase 1: Session Wiring + REPL Skeleton - Context

**Gathered:** 2026-09-23
**Status:** Ready for planning

## Phase Boundary

Users can hold a multi-ask conversation with the CLI that survives restarts via session resume. In scope: REPL entry, session identity and storage, first-run provider setup, kill-safe persistence. Out of scope: everything that acts on code (Phase 2+), permissions (Phase 3), modes (Phase 4).

## Implementation Decisions

### Entry experience
- **D-01:** `strands-code` with no arguments opens the REPL conversation immediately; there are no subcommands in Phase 1.
- **D-02:** On launch with existing sessions, show a resume picker (recent sessions + start-new); `--session-id <uuid>` still resumes directly.

### Session identity
- **D-03:** Sessions get auto-generated UUIDs; the user can rename a session when it matters.
- **D-04:** The model auto-titles each session from the first exchange; the user can rename anytime so the picker stays readable with zero effort.

### First-run provider
- **D-05:** First run without AWS credentials stops with a Bedrock setup pointer rather than falling back to local providers — **Reversibility:** costly — an offline-first entry path later would rework launch, session defaults, and the AWS-optional project constraint.
- **D-06:** After first run the provider lives in a config file; `/model` switching is out of scope for this phase (Phase 5) but the config choice must persist for it.

### Kill-resume guarantee
- **D-07:** A resumed session after SIGKILL restores full state: transcript plus pending tool state and working plan, not just history.
- **D-08:** Session state persists after every completed turn, so a kill loses at most the in-flight turn.

### the agent's Discretion
None — the user decided every area directly.

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project definition
- `.planning/PROJECT.md` — product vision, core value, constraints (note: D-05 tightens the AWS-optional constraint for the CLI entry path)
- `.planning/REQUIREMENTS.md` — LOOP-01, SES-01, SES-03 (this phase); all other REQ-IDs belong to later phases
- `.planning/ROADMAP.md` — Phase 1 goal, success criteria, dependencies
- `.planning/research/SUMMARY.md` — Implications for Roadmap: Phase 1 slice; pitfall 5 (lossy resume) mapped to this phase

### Codebase orientation
- `.planning/codebase/ARCHITECTURE.md` — agent/composition vs execution vs knowledge layers; where the CLI layer connects
- `.planning/codebase/STRUCTURE.md` — directory layout; where new CLI code goes
- `.planning/codebase/STACK.md` — `strands-agents` 1.57.0, `strands-harness` 0.1.2, `uv` toolchain, pytest gate

## Existing Code Insights

### Reusable Assets
- `CodeAgent` (`strands_code_agent/code_agent.py`): construct the REPL agent from harness defaults rather than a bare `Agent`
- `CodeAgentCallbackHandler` (`strands_code_agent/callback_handler.py`): Rich rendering seed for REPL output
- Harness `SessionManager` + file sessions (`./.agent/sessions`): the resume primitive, not custom storage

### Established Patterns
- Constructor-kwarg configuration (no env reads in library code): CLI config file should feed constructors, not environment sniffing beyond the AWS credential chain
- `tmp_dir` prompt injection: session-scoped working directories follow the same pattern

### Integration Points
- `create_harness(session=..., memory=...)` passthrough: session wiring composes here; `memory_manager=` overrides when memory tiers land
- `python_interpreter_class` seam: untouched in this phase (execution backends matter from Phase 2)

## Specific Ideas

No specific requirements — open to standard approaches. The user referenced Claude Code (`-c`/`-r`/picker resume semantics) and Codex (freeform anytime input) as UX models during project questioning.

## Deferred Ideas

None — discussion stayed within phase scope.

---

*Phase: 1-Session Wiring + REPL Skeleton*
*Context gathered: 2026-09-23*
