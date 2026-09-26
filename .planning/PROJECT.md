# Strands Code

## What This Is

Strands Code is a conversational coding CLI in the spirit of Claude Code and Codex CLI, built on the Strands harness. The user issues a series of asks; the CLI plans tasks and orchestrates subagents and tool calls to fulfill them. Its home turf is software engineering: speccing features, implementing them, writing and executing tests, and working the full GitHub loop — with the agent able to "talk" to source code and do deep research when needed.

## Core Value

A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.

## Requirements

### Validated

- ✓ Code-generation-first agent (`CodeAgent` + `python_repl`) — existing
- ✓ Declarative domain bundles (`Toolkit`: libraries, preamble, usage guidance, domain symbols) — existing
- ✓ Swappable execution backends (sandboxed default, unrestricted local, remote AgentCore) — existing
- ✓ OKF knowledge navigation for large documents (`find`/`read`/`children`/`toc`) — existing
- ✓ Rich terminal rendering + Bedrock token/cost metrics — existing
- ✓ Reproducible `uv` toolchain, 177-test suite green — existing

### Active

- [ ] Conversational task loop: series of user asks planned and executed with subagent + tool orchestration
- ✓ Plan / Act modes with approval between them — Phase 4 (classifier-deny, /approve handoff, session-sticky /mode)
- ✓ Anytime steering: freeform input injected at the next tool-call boundary without disturbing the task — Phase 4 (cancel_tool hook, finish-then-redirect)
- [ ] Strip reasoningContent from restored history for non-reasoning Bedrock models (emerged Phase 4: opus history fails validation on model switch; fresh session is the workaround)
- [ ] Side questions via a `/btw`-style escape answered by a spawned subagent, main task untouched
- [ ] Grep-first code understanding (agentic grep/READ); persistent semantic index deferred
- [ ] Full GitHub loop: read issues/PRs, branch, implement, test, open PRs, plus issue creation, review comments, CI checks
- [ ] Skills marketplace commands: add marketplace, install/list/invoke skills (local `./.agent/skills` loading underneath)
- [ ] Session resume by UUID across runs
- [ ] Cost/token display per session and task (no enforced budgets in v1)
- [ ] Manual `/model` switching across providers (Bedrock, Anthropic, OpenAI, local); auto routing deferred
- [ ] Context-size visibility command
- [ ] Parity checklist against Claude Code behavior as the v1 acceptance bar

### Out of Scope

- Persistent semantic code index in v1 — grep-first is enough to start; index is its own later phase
- Enforced token budgets — display only; halting on cost is deferred
- Auto model/effort routing (thinking-budget style) — manual switching first
- AgentCore as a required path — stays an opt-in backend; defaults are local

## Context

- Forked from `aws-samples/sample-strands-code-agent` (library); the CLI is new construction on top. Upstream remote configured for refreshes.
- Direction and competitive analysis: `docs/competitive-gap-analysis.md`. Codebase map: `.planning/codebase/`.
- Strands harness (`strands-harness>=0.1`, locked 0.1.2) adopted for tools, sessions, skills, memory, context management, effort presets. `strands-agents` locked at 1.57.0; both move fast and are flagged Experimental upstream — keep wrappers thin.
- Harness `context_manager` (`auto`/`agentic`/off) and presets cover context handling; `memory={"stores": [...]}` seam covers memory tiers (local markdown → Hindsight → memsearch).
- Full test suite green (`uv run pytest tests/`, 460 passed); dev group carries the data-science packages the toolkit tests execute.

## Constraints

- **Tech stack**: Python >=3.10, `uv` toolchain, Strands SDK + harness — pad the CLI, don't fork the platform
- **AWS posture**: AWS-optional, never AWS-required; `agentcore` stays an optional extra with lazy imports
- **Compatibility**: no upper pins during the experimental phase; resync upstream deliberately, not continuously

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Harness-first, gaps-only | Rebuilding sessions/memory/skills/context would duplicate tested upstream defaults | — Pending |
| Keep this fork, depend on the monorepo | Fork is the product differentiator; monorepo is the platform | ✓ Good |
| Grep-first code understanding | Persistent index is a project of its own; agentic grep ships sooner | — Pending |
| Plan/Act as the v1 mode | Closest to proven competitor behavior; effort presets can layer on later | — Pending |
| Anytime-steering + subagent side questions | Matches Codex/Muse Code UX the user prefers over command-gated steering | — Pending |
| Token display without budgets | Visibility first; enforcement is a policy decision for later | — Pending |
| Approval prompts served on main thread (ApprovalBroker) | SDK invokes ask in its event-loop worker, where stdin reads park on Ctrl-C and asyncio.run cannot nest; worker aborts via TurnCancelled | ✓ Good |
| Denials never cover batch signatures | Deny-marked-covered let model retries execute silently in-turn (fail-open); only approvals cover, denials re-prompt | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `$gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `$gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-26 after Phase 4*
