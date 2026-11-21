# Strands Code

## What This Is

Strands Code is a conversational coding CLI in the spirit of Claude Code and Codex CLI, built on the Strands harness. The user issues a series of asks; the CLI plans tasks and orchestrates subagents and tool calls to fulfill them. Its home turf is software engineering: speccing features, implementing them, writing and executing tests — with the agent able to "talk" to source code and do deep research when needed.

## Core Value

A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.

## Current State

**Shipped `v1.0` (2026-10-16, archived 2026-11-21):** All 12 planned phases (41 plans, 129 tasks) shipped end-to-end under GSD Spec-Driven Development (`strands-harness 0.1.2` + `strands-agents 1.58.1`, gated 10-package CLI architecture, 1,549 tests in [RETROSPECTIVE.md](../docs/initial_build/RETROSPECTIVE.md)).

**Active `v2.0` (initialized 2026-11-21 — Phases 13–19):** Aligning with `strands-py >=1.65`, `harness-py >=0.4.0`, Google AI Gemini (including Google AI Ultra credits), `DecisionModel` routing, deny-first remote skills marketplaces (`SKILL-03`), `strands-agents/box` Linux OS sandboxing, interactive UX (`/help`, `@file`, `/review`), and `strands-agents-evals`. See `.planning/ROADMAP.md` and `.planning/research/SUMMARY.md`.

## Requirements

### Validated

- ✓ Code-generation-first agent (`CodeAgent` + `python_repl`) — existing
- ✓ Declarative domain bundles (`Toolkit`: libraries, preamble, usage guidance, domain symbols) — existing
- ✓ Swappable execution backends (sandboxed default, unrestricted local, remote AgentCore) — existing
- ✓ Rich terminal rendering + Bedrock token/cost metrics — existing
- ✓ Reproducible `uv` toolchain + CI quality gates (`ruff`, `xenon`, `import-linter`) + 1,549-test suite — Phase 12
- ✓ Conversational task loop + file-local session resume by UUID (`--session-id`, `/resume`, `/rename`, `/forget`) — Phase 1
- ✓ File/Edit/Shell surface + grep-first code understanding (`/search`) + `/diff` gated edits — Phase 2
- ✓ Deny-first approval gate (`ApprovalBroker`) + standing TOML `/policy` rules — Phase 3
- ✓ Plan / Act modes with `/approve` handoff + `/mode` cycling + anytime steering + Ctrl-C cancel — Phase 4
- ✓ Manual `/model` switching across providers (Bedrock, Anthropic, OpenAI, local) — Phase 5 (idle-only swap, switch-first convert, mid-turn refusal, verbatim ARNs)
- ✓ Cost/token display per session and task — Phase 5 (usage line, `/cost`, live price/window almanac; display-only, no enforcement)
- ✓ Context controls `/compact`, `/clear`, `/context` + 80% auto-compact — Phase 5 (pair-atomic, tool pairs never split)
- ✓ Local skills: load from `./.agent/skills`, invoke as `/<name>`, autocomplete + `/skills` manage — Phase 6 (built-ins win collisions, `namespace:skill` prefixes, trailing-text input, typed-name match echo)
- ✓ Repo memory file: dual `STRANDS.md` + `.agent/MEMORY.md` auto-load, `/init` scan-draft, `/memory` curate/approve + NL revise rounds — Phase 6 (.agent wins, curate-by-default, auto-reload, flush on exit)
- ✓ Markup-safe transcript: hostile `[...]` content renders literally, never crashes — Phase 6 UAT (print_plain, markup off; supersedes WR-06 escape)
- ✓ Side questions via a `/btw`-style escape answered by a spawned subagent, main task untouched — Phase 7 (parallel side agent, shared tagged deny-first gate, fenced blocks, FIFO queue, Ctrl-C chooser, multiplexed idle delivery)
- ✓ Decision-model routing with manual override kept — Phase 8 (per-ask model + effort selection via OpenRouter/Ollama engines, calibration, chain/preflight/retry)
- ✓ Native TypeSafe Jev decision engine alongside OpenRouter and Ollama — Phase 9 (user-ordered engines, live-ping validate, computed $0.042/1M spend, 20-probe calibration)
- ✓ Provider-reported turn spend for main turns (OpenRouter actuals + Bedrock/offline estimated split) — Phase 10
- ✓ Opt-in CodeAct action interface (`--codeact`, `/codeact`: `tool|code|both`) with whole-block approval — Phase 11
- ✓ Structural review + 10-package CLI breakup + OKF dead-example removal — Phase 12
- ✓ GitHub flows via general tool competence (`gh` + shell covers issues/PRs/CI; small `/review` slash deferred to v2) — covered v1.0

### Active (`v2.0` — Phases 13–19, see `.planning/REQUIREMENTS.md`)

- [ ] **UPSTREAM-01** (Phase 13): Resync onto `strands-agents >=1.65` & `strands-harness >=0.4`, adapt `InjectedBlock` + `Model.model_info`, retire `#5166`/`#5158` shims, enable `streaming=False` for `_NO_STREAMING_TOOLS`
- [ ] **MODEL-06** (Phase 14): First-class `google/` Gemini (`gemini` extra), Box-compatible provider-aware startup preflight, `reasoningSignature` / `_vendor_family` / `litellm_entry` fixes, AI Studio + Google AI Ultra (\$40–\$100/mo credit) setup docs
- [ ] **UPSTREAM-02** (Phase 15): Migrate `routing/` engine transports onto `strands.decisions.DecisionModel` while preserving `apply_model_action`, `0.62`/`0.04` gate, two-call effort flow & `/cost` actuals
- [ ] **SKILL-03** (Phase 16): Remote skills marketplaces + `./.agent/skills-lock.json` SHA/hash installer into `./.agent/skills-marketplaces/` under deny-first safeguards
- [ ] **SANDBOX-01** (Phase 17): Strands Box (`v0.2.3+`) Linux wrapper workflow (`box.toml` + Dogwood `policy.dw`, 5-provider egress profiles, temporal rule + scoped `D-05` revisit, `STRANDS_BOX=1` `codeact_shell` alignment)
- [ ] **LOOP-06 / TOOL-05 / REVIEW-01** (Phase 18): Isolated UX modules (`/help`, gitignore-confined `@file` / `/file` attachment picker + `"document"` switch conversion, Python-collected read-only `/review`)
- [ ] **EVAL-01** (Phase 19): `strands-agents-evals >=1.10` regression & Crescendo/GOAT/PAIR red-team suite under `scripts/evals/` + `tests/evals/`

### Future (`v2.1+`)

- **SKILL-04**: MCP server config via `create_harness(mcp_servers=...)`
- **LOOP-05**: Non-interactive headless / JSON output mode for scripts and CI
- **TOOL-06**: Export trimmed session content via `/copy`
- **MODE-03 / REVIEW-02**: Fast/thorough effort presets and headless/CI review modes

### Out of Scope

- Persistent semantic code index in v1 — grep-first is enough to start; index is its own later phase
- Enforced token budgets — display only; halting on cost is deferred
- Fully automatic model routing with no override — Phase 8 routing proposes, manual switching + explicit override always win
- AgentCore as a required path — stays an opt-in backend; defaults are local
- Consumer OAuth piggybacking on Gemini CLI / Code Assist — violates Google ToS; personal Google AI Pro/Ultra plans already include monthly Google Developer Program credits ($10–$100/mo) usable via a standard AI Studio API key

## Context

- Forked from `aws-samples/sample-strands-code-agent` (library); the CLI is new construction on top. Upstream remote configured for refreshes (byproduct-only PRs when mutually useful).
- Direction and competitive analysis: `docs/competitive-gap-analysis.md`. Ecosystem v2 brief: `.planning/research/V2-ALIGNMENT.md`. Codebase map: `.planning/codebase/`.
- `v1.0` shipped on `strands-harness 0.1.2` and `strands-agents 1.58.1` (`strands-agents>=0.1.0`, `strands-harness>=0.1`); both are flagged Experimental upstream — keep wrappers thin.
- Harness `context_manager` (`auto`/`agentic`/off) and presets cover context handling; `memory={"stores": [...]}` seam covers memory tiers, with local markdown the only backend (Hindsight and OpenViking evaluated and rejected in Phase 12).
- `pyproject.toml` stays at package version `0.4.0` during `v1.0` archive (pre-v2 SDK convergence).

## Constraints

- **Tech stack**: Python >=3.10, `uv` toolchain, Strands SDK + harness — pad the CLI, don't fork the platform (no TypeScript dependency)
- **AWS posture**: AWS-optional, never AWS-required; `agentcore` stays an optional extra with lazy imports
- **Compatibility**: no upper pins during the experimental phase; resync upstream deliberately, not continuously

## Key Decisions

| Decision | Rationale | Outcome |
|---|---|---|
| Harness-first, gaps-only | Rebuilding sessions/memory/skills/context would duplicate tested upstream defaults | ✓ Good (v1.0) |
| Keep this fork, depend on the monorepo | Fork is the product differentiator; monorepo is the platform | ✓ Good |
| Grep-first code understanding | Persistent index is a project of its own; agentic grep ships sooner | ✓ Good (v1.0) |
| Plan/Act as the v1 mode | Closest to proven competitor behavior; effort presets can layer on later | ✓ Good (v1.0) |
| Anytime-steering + subagent side questions | Matches Codex/Muse Code UX the user prefers over command-gated steering | ✓ Good (v1.0) |
| Token display without budgets | Visibility first; enforcement is a policy decision for later | ✓ Good (Phase 5: display-only + static kill-switch) |
| /memory curates, never edits (NL revise rounds) | Hand-editing inside the CLI rejected; harness proposes, user approves/revises in words (Phase 4 grammar reuse) | ✓ Good |
| D-13 as accept-echo, not inline highlight | Same decision value without prompt_toolkit lexer surgery | ✓ Good |
| Dual memory file, .agent wins, corrupt-tolerant | Root STRANDS.md for interop, owned .agent/MEMORY.md wins; corrupt frontmatter keeps body + note, never crashes | ✓ Good |
| Switch-first convert, mid-turn slash refusal | Convert-then-switch crashed on ARNs; mid-turn /model derailed writes — swap before convert, refuse slash mid-turn | ✓ Good |
| Automatic most-precise-first pricing + provenance | No (a)/(b) source toggle; Price List → OpenRouter → LiteLLM layering with source line | ✓ Good |
| Approval prompts served on main thread (ApprovalBroker) | SDK invokes ask in its event-loop worker, where stdin reads park on Ctrl-C and asyncio.run cannot nest; worker aborts via TurnCancelled | ✓ Good |
| Denials never cover batch signatures | Deny-marked-covered let model retries execute silently in-turn (fail-open); only approvals cover, denials re-prompt | ✓ Good |
| Owned AgentSkills + refresh-on-reload | Harness registry is load-once; CLI reload left it stale and models refused reloaded skills — owned instance refreshed first, both-stale-or-both-fresh | ✓ Good (live-verified) |
| Markup-safe printing, markup off | Dynamic transcript text through Rich markup parsing crashed sessions (WR-06 class); print_plain renders verbatim, styling via kwarg | ✓ Good |
| Explicit invocation frames skill trust | Absolute untrusted marker made models refuse invoked skills; invocation is the trust signal, distrust scoped to embedded third-party directives, gate stays hard control | ✓ Good (live-verified) |
| Side channel shares the main deny-first gate (tagged [main]/[btw]) | Separate gates would double-prompt and split batch coverage; tags from event.agent identity keep attribution on every prompt | ✓ Good (live-verified, Phase 7) |
| Side agent via create_harness rebuild, not agents-as-tools | Helper-agent pattern couldn't share gate/model/memory; rebuild over stashed kwargs + forked history keeps one policy surface | ✓ Good (Phase 7) |
| D-14 append-back: side exchange lands in main history at boundary | One conversation matches the user mental model; fences + /btw identity preserve attribution | ✓ Good (live-verified, Phase 7) |
| User-ordered decision engines, native-first when keyed | Fixed priority couldn't express key-absent fallback; ordered list + live-ping validate keeps setup honest | ✓ Good (Phase 9) |
| Native spend computed code-side at published rate | Native usage carries no cost field; input×$0.042/1M with a computed-rate marker beats silent $0 | ✓ Good (Phase 9) |

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
*Last updated: 2026-11-21 — Milestone v2.0 initialized*
