# Phase 2: File/Edit/Shell Surface + /diff - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-24
**Phase:** 2-File/Edit/Shell Surface + /diff
**Areas discussed:** Tool provenance, /diff semantics, Shell scope, Grep UX

---

## Tool provenance

| Option | Description | Selected |
|--------|-------------|----------|
| Strands-tools first | Wire file_read/shell/editor from strands-agents-tools; repl stays for computation. | ✓ |
| Extend python_repl | File ops inside the code-first paradigm. | |
| Full surface | Read, write/edit, shell together in this phase. | ✓ |
| Read-first | Reads now, writes after. | |

**User's choice:** Strands-tools first, full surface; repl's exact role to planner
**Notes:** User clarified the agent must keep source-code write ability at least for local folder + subfolders — writes may flow through dedicated tools rather than generated Python.

---

## /diff semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Gate every edit | Each edit pauses at a preview. | |
| On-demand review | Edits apply; /diff reviews accumulated changes. | |
| User-selectable mode | Approve-each, on-demand, or auto — user picks. | ✓ (user-added) |
| Whole change | Apply/discard per edit. | |
| Per-hunk | Accept/reject hunks. | |
| Granularity follows mode | Per-hunk when careful, whole-change normally, none in auto. | ✓ (user-added) |

**User's choice:** Planner decides mechanics; mode is user-selectable, granularity follows mode
**Notes:** User observed auto generalizes beyond diffs to all tool calls (yolo mode) — recorded as deferred cross-phase idea, out of scope.

---

## Shell scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full shell | Any command; Phase 3 gates dangers. | ✓ |
| Curated subset | Read-only now, mutation later. | |
| Cwd + subdirs + /tmp default | Expansion permission-gated. | ✓ (user-added) |

**User's choice:** Full shell; default scope cwd + subdirs + /tmp with permission-gated expansion
**Notes:** User corrected the /tmp exclusion — /tmp is in by default.

---

## Grep UX

| Option | Description | Selected |
|--------|-------------|----------|
| Both | Agent greps; user gets /search. | ✓ |
| Agent-driven only | No user command. | |
| Text + symbols | Lexical + on-the-fly definitions/references, no embeddings. | ✓ |
| Plain text only | Straight ripgrep. | |

**User's choice:** Both, text + symbols
**Notes:** None.

---

## the agent's Discretion

- `python_repl`'s exact remaining role (D-03)
- Diff mode-switch mechanics and per-hunk UI shape (D-04)

## Deferred Ideas

- General auto/yolo mode covering all tool calls — mode-system territory, likely Phase 4.
