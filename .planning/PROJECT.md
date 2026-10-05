# Strands Code

## What This Is

Strands Code is a conversational coding CLI in the spirit of Claude Code and Codex CLI, built on the Strands harness. The user issues a series of asks; the CLI plans tasks and orchestrates subagents and tool calls to fulfill them. Its home turf is software engineering: speccing features, implementing them, writing and executing tests — with the agent able to "talk" to source code and do deep research when needed. (GitHub work rides on general tool competence via `gh`, as in Claude Code — no dedicated loop.)

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
- ✓ Manual `/model` switching across providers (Bedrock, Anthropic, OpenAI, local) — Phase 5 (idle-only swap, switch-first convert, mid-turn refusal, verbatim ARNs)
- ✓ Cost/token display per session and task — Phase 5 (usage line, `/cost`, live price/window almanac; display-only, no enforcement)
- ✓ Context controls `/compact`, `/clear`, `/context` + 80% auto-compact — Phase 5 (pair-atomic, tool pairs never split)
- ✓ Local skills: load from `./.agent/skills`, invoke as `/<name>`, autocomplete + `/skills` manage — Phase 6 (built-ins win collisions, `namespace:skill` prefixes, trailing-text input, typed-name match echo)
- ✓ Repo memory file: dual `STRANDS.md` + `.agent/MEMORY.md` auto-load, `/init` scan-draft, `/memory` curate/approve + NL revise rounds — Phase 6 (.agent wins, curate-by-default, auto-reload, flush on exit)

### Active

- [ ] Conversational task loop: series of user asks planned and executed with subagent + tool orchestration
- ✓ Plan / Act modes with approval between them — Phase 4 (classifier-deny, /approve handoff, session-sticky /mode)
- ✓ Anytime steering: freeform input injected at the next tool-call boundary without disturbing the task — Phase 4 (cancel_tool hook, finish-then-redirect)
- [ ] Strip reasoningContent from restored history for non-reasoning Bedrock models (emerged Phase 4: opus history fails validation on model switch; fresh session is the workaround)
- [ ] Side questions via a `/btw`-style escape answered by a spawned subagent, main task untouched
- [ ] Grep-first code understanding (agentic grep/READ); persistent semantic index deferred
- [x] GitHub flows via general tool competence (no dedicated loop — Claude Code has none either): shell tool + `gh` covers read issues/PRs, branch, implement, test, open PRs, issue creation, review comments, CI checks; small `/review` slash stays a future item
- [ ] Skills marketplace commands: add marketplace, install skills (local load/invoke validated Phase 6)
- [ ] Escape Rich markup in skill-match echo (WR-06 residual: hostile skill descriptions garble/crash the echo line)
- [ ] Session resume by UUID across runs
- [ ] Decision-model routing with manual override kept — Phase 8
- [ ] v1 acceptance bar: phases 1–9 complete. Aim is best Bedrock-first terminal coding CLI, not feature parity with Claude Code (unwinnable surface: IDE, CI app, web, marketplaces)

### Out of Scope

- Persistent semantic code index in v1 — grep-first is enough to start; index is its own later phase
- Enforced token budgets — display only; halting on cost is deferred
- Fully automatic model routing with no override — Phase 8 routing proposes, manual switching + explicit override always win
- AgentCore as a required path — stays an opt-in backend; defaults are local

## Context

- Forked from `aws-samples/sample-strands-code-agent` (library); the CLI is new construction on top. Upstream remote configured for refreshes.
- Direction and competitive analysis: `docs/competitive-gap-analysis.md`. Codebase map: `.planning/codebase/`.
- Strands harness (`strands-harness>=0.1`, locked 0.1.2) adopted for tools, sessions, skills, memory, context management, effort presets. `strands-agents` locked at 1.57.0; both move fast and are flagged Experimental upstream — keep wrappers thin.
- Harness `context_manager` (`auto`/`agentic`/off) and presets cover context handling; `memory={"stores": [...]}` seam covers memory tiers (local markdown → Hindsight → memsearch).
- Full test suite green (`uv run pytest tests/`, 790 passed, 5 deselected); dev group carries the data-science packages the toolkit tests execute.

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
| Token display without budgets | Visibility first; enforcement is a policy decision for later | ✓ Good (Phase 5: display-only + static kill-switch) |
| /memory curates, never edits (NL revise rounds) | Hand-editing inside the CLI rejected; harness proposes, user approves/revises in words (Phase 4 grammar reuse) | ✓ Good |
| D-13 as accept-echo, not inline highlight | Same decision value without prompt_toolkit lexer surgery | ✓ Good |
| Dual memory file, .agent wins, corrupt-tolerant | Root STRANDS.md for interop, owned .agent/MEMORY.md wins; corrupt frontmatter keeps body + note, never crashes | ✓ Good |
| Switch-first convert, mid-turn slash refusal | Convert-then-switch crashed on ARNs; mid-turn /model derailed writes — swap before convert, refuse slash mid-turn | ✓ Good |
| Automatic most-precise-first pricing + provenance | No (a)/(b) source toggle; Price List → OpenRouter → LiteLLM layering with source line | ✓ Good |
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
*Last updated: 2026-10-04 after Phase 6*
