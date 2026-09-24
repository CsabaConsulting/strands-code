# Phase 1: Session Wiring + REPL Skeleton - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-23
**Phase:** 1-Session Wiring + REPL Skeleton
**Areas discussed:** Entry experience, Session identity, First-run provider, Kill-resume guarantee

---

## Entry experience

| Option | Description | Selected |
|--------|-------------|----------|
| Straight to REPL | `strands-code` opens the conversation immediately; resume inside via `/resume`. Thinnest Phase 1. | ✓ |
| Subcommands | `run` / `resume` / `skills` entry points. More discoverable, more surface. | |
| You decide | Agent picks during planning. | |

**User's choice:** Straight to REPL; resume picker at launch (`--session-id` still works)
**Notes:** Research had proposed a Typer entry with subcommands; user preferred the thinner straight-to-REPL entry.

---

## Session identity

| Option | Description | Selected |
|--------|-------------|----------|
| UUID + rename | Auto UUIDs; user renames when it matters. | ✓ |
| Named from start | Human name up front. Friendlier picker, more friction. | |
| Auto-title | Model titles from first exchange; user can rename. | ✓ |
| /rename only | UUIDs stay raw until explicit rename. | |

**User's choice:** UUID + rename, with model auto-titles
**Notes:** Zero-effort readable picker was the deciding factor.

---

## First-run provider

| Option | Description | Selected |
|--------|-------------|----------|
| Detect + fallback | No creds: offer local/Ollama or guided Bedrock setup. | |
| Bedrock or stop | Require AWS creds up front with setup pointer. | ✓ |
| Config + /model | Provider in config file; `/model` persists the choice. | ✓ |
| Env only | Provider purely from environment. | |

**User's choice:** Bedrock or stop for first run; config file + `/model` thereafter
**Notes:** User overrode the recommendation and the AWS-optional project constraint for the CLI entry path. Carried into CONTEXT.md (D-05, costly reversibility).

---

## Kill-resume guarantee

| Option | Description | Selected |
|--------|-------------|----------|
| Full state | Transcript + pending tool state + working plan survive SIGKILL. | ✓ |
| Transcript only | History survives; in-flight work restarts. | |
| Every turn | Persist after each completed turn. | ✓ |
| Exit + periodic | Flush on clean exit plus interval. | |

**User's choice:** Full state, persisted every turn
**Notes:** Strongest guarantee; kill loses at most the in-flight turn.

---

## the agent's Discretion

None — the user decided every area directly.

## Deferred Ideas

None — discussion stayed within phase scope.
