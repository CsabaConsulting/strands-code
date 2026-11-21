# Phase 11: CodeAct Action Interface - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-13
**Phase:** 11-codeact-action-interface
**Areas discussed:** Opt-in surface, Approval reconciliation, CodeAct scope, Both-mode meaning, Mid-session switching

---

## Opt-in surface

Q1: How should the user primarily choose the CodeAct interface?

| Option | Description | Selected |
|--------|-------------|----------|
| Slash command | e.g. /codeact toggles the interface for the rest of the session, like other session toggles. Most discoverable. | ✓ |
| Mode cycle | Extend the existing Plan/Act cycle with an interface dimension. Fewer commands, more modal confusion. | |
| Per-ask flag | Choose per ask at send time, e.g. a prefix or flag. Most granular, most friction. | |

**User's choice:** Slash command
**Notes:** "plus there could be optional mode setting if it's fitting and not upset other logic. And there could be session default too to start with"

Q2: Should the tool-calling default reset every session, or remember the last choice?

| Option | Description | Selected |
|--------|-------------|----------|
| Always default | Every new session starts tool-calling; the user opts into CodeAct each time. Matches TOOL-07 literally. | ✓ |
| Remember last choice | Remember the last-used interface across sessions. Convenient but weakens the default guarantee. | |

**User's choice:** Always default
**Notes:** "global config could switch this behavior to 'remember last choice'"

Q3: How should the session-start interface default work?

| Option | Description | Selected |
|--------|-------------|----------|
| Startup flag | A startup flag like --codeact sets the session's starting interface. Explicit, scriptable, no persistence. | ✓ |
| Config key | A config file key sets the session default. Persists but adds config surface. | ✓ |
| First-use sticks | First /codeact use in a session sets the default for the rest of it. Zero new surface. | |

**User's choice:** Free text — "All the three above, startup flag --codeact can work, config key can work too, and also /codeact"
**Notes:** User took startup flag + config key + slash (first-use-sticks not selected)

Q4: Should the mode system also carry the interface choice?

| Option | Description | Selected |
|--------|-------------|----------|
| Fit if natural | If the mode system naturally fits an interface dimension, wire it in; otherwise slash + flag only. | ✓ |
| Leave modes alone | Keep mode logic untouched; slash command and startup flag are the only surfaces. | |

**User's choice:** Fit if natural
**Notes:** None

---

## Approval reconciliation

Q1: What should the deny-first approval gate on for CodeAct actions?

| Option | Description | Selected |
|--------|-------------|----------|
| Approve the code | Show the generated code (like a /diff preview) and approve/deny the whole block before it runs. One prompt per code action. | ✓ |
| Approve each effect | Run the code in a sandbox that pauses for approval when a side effect is attempted. Finer control, interrupts execution. | |
| Risk-based prompt | Static scan of generated code; only prompt when it touches flagged operations (file write, shell, network). | |

**User's choice:** Approve the code — REVISED at wrap-up: whole-block only, no per-effect option
**Notes:** Initially: "Configuration could turn on the second option 'Approve each effect'". Later revised: "it'd be only per whole code block (diff presented), I don't want to complicate things to present approval within some code steps". Final decision is whole-block only.

Q2: When the user denies a CodeAct block, what happens next?

| Option | Description | Selected |
|--------|-------------|----------|
| Agent revises | The agent sees the denial and can revise the code or try a different approach. Keeps the turn alive. | ✓ |
| Skip and stop | The code action is skipped and the turn ends. Simple, matches tool-deny today. | |

**User's choice:** Agent revises
**Notes:** None

Q3: Do remembered Always/Never approval rules apply to CodeAct code blocks?

| Option | Description | Selected |
|--------|-------------|----------|
| Same rules | Always/never rules apply to CodeAct approvals exactly like tool approvals. One rule system. | ✓ |
| Always one-shot | CodeAct approvals are always one-shot; no remembered rules for generated code. Stricter. | |

**User's choice:** Same rules
**Notes:** None

Q4: Where may approval prompts appear relative to orchestration?

| Option | Description | Selected |
|--------|-------------|----------|
| Boundary only | The approval prompt appears at the code-action boundary, between orchestration steps — never nested inside a running tool call. | ✓ |
| Wherever needed | Allow prompts to surface wherever the need arises, even mid-execution. More flexible, risks nested prompts. | |

**User's choice:** Boundary only
**Notes:** None

---

## CodeAct scope

Q1: What can CodeAct-generated code touch?

| Option | Description | Selected |
|--------|-------------|----------|
| Full tool parity | Generated code can call the same file/edit/shell tools as functions. Full parity with tool-calling. | ✓ |
| Compute only | Code runs in the sandbox with compute + stdlib only; file/shell/network stay tool-only. | |
| Narrow then grow | Start with compute + file read; add more surfaces only if this phase calls for it. | |

**User's choice:** Full tool parity
**Notes:** None

Q2: Which execution backend should CodeAct use?

| Option | Description | Selected |
|--------|-------------|----------|
| Sandboxed local | Reuse the library's SandboxedPythonInterpreter (smolagents allowlist + timeout). Proven, offline-safe. | ✓ |
| Unrestricted exec | Run generated code in-process with no sandbox. Fastest, weakest isolation. | |
| Local + AgentCore option | Offer local sandboxed by default with AgentCore remote as an opt-in backend. | |

**User's choice:** Sandboxed local
**Notes:** None

Q3: Does REPL state persist across code actions in a session?

| Option | Description | Selected |
|--------|-------------|----------|
| REPL persists | Variables and imports persist across code actions within the session, like a REPL. Powerful, state can surprise. | ✓ |
| Fresh each time | Each code action runs fresh; pass state explicitly. Predictable, more verbose. | |

**User's choice:** REPL persists
**Notes:** None

Q4: How should code-action timeouts work?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep defaults | Keep the library defaults (180s agent / 60s interpreter) unless a task needs otherwise. | ✓ |
| User setting | Expose a user-visible timeout setting for code actions. | |

**User's choice:** Keep defaults
**Notes:** None

---

## Both-mode meaning

Q1: What does choosing 'both' interfaces mean concretely?

| Option | Description | Selected |
|--------|-------------|----------|
| User routes per ask | The user picks the interface per ask at send time. Explicit, predictable, no model guessing. | ✓ |
| Model picks per step | The model chooses tool-calling or CodeAct per step within a turn. Flexible, less predictable. | |
| Draft then execute | CodeAct drafts code, tool-calling executes the effects. Fixed pipeline, narrowest. | |

**User's choice:** User routes per ask
**Notes:** None

Q2: Can one turn mix both interfaces, or one interface per turn?

| Option | Description | Selected |
|--------|-------------|----------|
| One per turn | One interface per turn; the turn's interface is fixed when the ask is sent. Simplest coherence story. | ✓ |
| Mix within a turn | A single turn may interleave tool calls and code actions. Most flexible, hardest to follow. | |

**User's choice:** One per turn
**Notes:** None

Q3: Should the transcript show which interface each turn used?

| Option | Description | Selected |
|--------|-------------|----------|
| Label each turn | The transcript labels each turn with the interface used (tool/codeact). Auditable history. | ✓ |
| No labels | No interface labels; turns look the same regardless of interface. Cleaner, less traceable. | |

**User's choice:** Label each turn
**Notes:** None

Q4: Should /cost distinguish CodeAct turns from tool-calling turns?

| Option | Description | Selected |
|--------|-------------|----------|
| Identical rows | /cost rows work identically for both interfaces; no interface column or split. Cost is cost. | ✓ |
| Distinguish turns | /cost distinguishes CodeAct turns from tool turns. More detail, more clutter. | |

**User's choice:** Identical rows
**Notes:** None

---

## Mid-session switching

Q1: What happens to REPL state when switching interfaces mid-session?

| Option | Description | Selected |
|--------|-------------|----------|
| Reset on switch | Switching interfaces resets the REPL; each CodeAct session starts fresh. Predictable, loses scratch state. | ✓ |
| Keep across switch | REPL variables survive interface switches within the session. Convenient, state can surprise. | |

**User's choice:** Reset on switch
**Notes:** None

Q2: Do remembered approval rules survive an interface switch?

| Option | Description | Selected |
|--------|-------------|----------|
| Rules carry over | Remembered Always/Never rules carry across the switch unchanged. One rule system, both interfaces. | ✓ |
| Rules reset | Switching clears remembered rules; the user re-teaches them per interface. Stricter, more friction. | |

**User's choice:** Rules carry over
**Notes:** None

Q3: Can the user switch interfaces mid-turn, or only between asks?

| Option | Description | Selected |
|--------|-------------|----------|
| Next ask only | Interface switches apply at the next ask; a running turn always finishes on its starting interface. | ✓ |
| Mid-turn allowed | Allow switching mid-turn with the turn adapting. Flexible, coherence is hard. | |

**User's choice:** Next ask only
**Notes:** None

Q4: Is conversation history preserved across an interface switch?

| Option | Description | Selected |
|--------|-------------|----------|
| History kept | Full conversation history is preserved across switches; only the action interface changes. | ✓ |
| Fresh context | Switching starts a fresh conversation context. Clean break, loses context. | |

**User's choice:** History kept
**Notes:** None

---

## the agent's Discretion

No "you decide" items — the user answered every question directly.

## Deferred Ideas

- Per-effect sandbox-pausing approvals — considered, explicitly rejected at wrap-up; recorded in CONTEXT.md deferred section to prevent resurrection.
