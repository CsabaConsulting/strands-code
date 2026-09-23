# Feature Research

**Domain:** Conversational agentic coding CLI (Claude Code / Codex CLI class) built on an existing Python agent library
**Researched:** 2026-09-23
**Confidence:** HIGH (competitor behavior cross-checked across official docs, cheat sheets, and community references; project context from PROJECT.md and docs/competitive-gap-analysis.md)

## Feature Landscape

Context for every entry: this is a SUBSEQUENT milestone. `CodeAgent` + `python_repl`, `Toolkit` bundles, pluggable interpreters, OKF knowledge navigation, Rich rendering + Bedrock metrics, and the `uv` toolchain already exist. The Strands harness supplies sessions, skills loading, memory tiers, context management, effort presets, interventions/HITL, and provider-agnostic models. "Ours to build" below means genuine CLI gap work; "Harness-native" means wire-up + UX only.

### Table Stakes (Users Expect These)

Missing these = users judge the CLI incomplete against Claude Code / Codex CLI and leave.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Conversational task loop (series of asks, plan + execute with tool calls) | The core product: every competitor is a REPL that plans multi-step work and executes it | MEDIUM | Ours to build. Depends on: session wiring, slash registry, tool surface (file/edit/shell). Keep `CodeAgent` as the loop; construct from harness defaults. |
| Plan / Act modes with approval gate between them | Claude Code (`plan` → `default` → `acceptEdits` → `auto` → `dontAsk` → `bypass`), Gemini CLI plan mode, OpenCode `plan` agent all gate writes behind an approved plan | MEDIUM | Ours (UX preset over harness `interventions` + tool/step budgets). Expected behavior: Plan = read-only (no edits, no shell), presents plan, user approves → Act executes. `Shift+Tab`-style cycling is the de-facto UX. PROJECT.md mandates Plan/Act as v1 mode. |
| Permission/approval prompts before edits, shell, network | Claude Code asks before writes/commands by default; Codex has sandbox + approval policies; users distrust agents that mutate silently | MEDIUM | Harness-native primitives (interventions `ask`/`smart`/policy, guardrails) + ours: permissions policy file (deny lists), ask/allow prompts, env scrubbing. Depends on: tool surface. Deny beats allow; never auto-restore elevated permissions on resume. |
| Slash-command registry (`/help /clear /compact /resume /model /cost /context /diff /review /memory` class) | Claude Code ships ~15 built-ins; Codex has `/model /review`; users navigate the whole product through `/` | LOW | Ours to build (thin parser on leading `/` over Strands hooks). No harness-native parser. Depends on: each backing capability. Start with PROJECT.md set: `/model /resume /compact /clear /memory /cost /diff /review` + `/context`. |
| Session resume by ID across runs (`--continue`, `--resume`, picker) | Claude Code: `claude -c`, `claude -r <name>`, `/resume` picker; Codex: `codex exec resume`; session tools (cc-switch) assume resumability | LOW | Harness-native (`SessionManager`, file sessions in `./.agent/sessions`) + ours: `--session-id` routing, named sessions (`/rename`), flush-on-exit, start/end + reclaim policy. PROJECT.md requires resume by UUID. Depends on: session wiring (build first). |
| Context management: `/compact`, `/clear`, `/context` visibility | Long coding sessions overflow context in every competitor; `/compact` (summarize and continue) and `/context` (what is consuming the window) are standard | LOW | Harness-native (truncate ~1500-token tool results, compact at ~85%, prompt caching) + ours: command UX. `/context` is explicitly required by PROJECT.md (context-size visibility command). |
| Cost/token display per session and task (`/cost`, `/usage`) | Claude Code `/cost` + `/usage` (USD + plan remainder); third-party session tools show per-page token/cost; users need spend awareness on metered APIs | LOW | Ours (render Bedrock + provider metrics; existing `CodeAgentCallbackHandler` metrics are the seed) over harness/native tracing. Display only in v1 — no enforcement (PROJECT.md decision). Depends on: task loop + session identity. |
| Manual `/model` switching across providers, mid-session | Claude Code `/model`; Codex `-m` flag + `/model` picker with reasoning levels; multi-provider CLIs switch in-shell; users hit model limits and capability cliffs | MEDIUM | Harness-native providers (Bedrock/Anthropic/OpenAI/Google/Ollama/LiteLLM via provider string) + ours: `/model` picker + config file. Default Bedrock but override-friendly (AWS-optional constraint). No auto-routing in v1. Depends on: provider config. |
| File/shell tool surface + `/diff` viewer | Competitors read/write/edit/shell as first-class tools with diff review; routing everything through `python_repl` feels alien | MEDIUM | Prefer `strands-agents-tools` (`file_read`, shell, editor) + `/diff` viewer. Depends on: permissions/HITL (must land together or tools run ungated). |
| Project memory file (`CLAUDE.md` / `AGENTS.md` class) + `/init`, `/memory` | Every competitor auto-loads repo instructions (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`); `/init` scaffolds it, `/memory` edits it | LOW | Convention + ours: loader honoring existing repo files, `/init` + `/memory` commands. Local markdown default (offline story). Depends on: slash registry. |
| MCP server wiring (`--mcp-config` class) | Claude Code, Codex, Gemini all consume MCP servers as tools; users bring their own integrations (GitHub, Linear, SentryISSION) | LOW | SDK supports MCP servers as tools — wire config + lifecycle only. Depends on: tool surface. |
| Non-interactive / print mode (`-p`, `codex exec` class) for scripts and CI | Codex `exec` is a first-party documented CI feature; Claude Code has `-p` print + piping; without it the CLI cannot compose in pipelines | MEDIUM | Ours: headless runner with explicit pre-set sandbox + approval settings, JSON output. Depends on: task loop, permissions policy. |
| Sandbox execution for shell/code (read-only → workspace-write → full) | Codex OS-enforced sandboxes (Seatbelt/Landlock, network-disabled); Gemini Seatbelt/Docker; users run untrusted agent-generated commands | MEDIUM | Existing `SandboxedPythonInterpreter` + sandbox presets are the seed; promote `imports.py` auto-authorize to explicit policy. Depends on: permissions policy. |
| Interrupt / cancel (Ctrl-C semantics that cancel, not quit) | Long agent runs must be stoppable; Aider/OpenCode distinguish cancel-run from quit-app; users steer by stopping first | LOW | Ours: SIGINT cancels current run, second/double signal quits. Depends on: task loop. Foundation for anytime steering. |
| Subagents (agents-as-tools: delegate, parallelize, isolate side work) | Claude Code `.claude/agents/`, Codex subagents; the `/btw` side-question feature IS a subagent spawn | MEDIUM | Harness-native helper-subagent pattern + ours: spawn/route UX. Depends on: task loop, session identity. Enables `/btw` and parallel exploration. |
| GitHub loop: read issues/PRs, branch, implement, test, open PR | PROJECT.md core value ("single ask → PR") assumes it; Codex has `/review` modes and cloud flow; agentic CLIs live in the PR workflow | MEDIUM | Ours over MCP/API + shell (`gh`). Scope v1: read issues/PRs, branch, implement, test, open PR, issue creation, review comments, CI checks (per PROJECT.md Active). Depends on: tool surface, non-interactive mode. |
| Skills loading from local dirs (`./.agent/skills`) + invoke | Claude Code `AgentSkills`-style on-demand instruction packs keep prompts lean; competitors converge on SKILL.md portability | LOW | Harness-native (`AgentSkills(skills=...)`) + ours: loader wiring. Keep `Toolkit` for code-preamble; add Skills for markdown packs; port 1–2 Toolkits as proof (per gap analysis). Depends on: slash registry (for `/skills` UX). |

### Differentiators (Competitive Advantage)

Not expected, but valued. Align with the Core Value: single ask → spec, build, test, PR without leaving the conversation.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Anytime steering (freeform input injected at next tool-call boundary) | Matches Codex/Muse Code UX the user prefers over command-gated steering; correcting a running agent beats stop-reprompt-restart | MEDIUM | Ours: input queue drained between tool calls, main task undisturbed. Depends on: task loop, interrupt/cancel. PROJECT.md mandates it — treat as near-table-stakes for this product's UX bet. |
| `/btw` side questions via spawned subagent, main task untouched | Ask a question mid-run without polluting main context or derailing the plan; no competitor does this as a first-class escape | LOW | Ours over subagents. Depends on: subagents. Cheap because the primitive already exists. High demo value — good v1 differentiator. |
| Code-generation-first agent (`CodeAgent` + `python_repl`) | Preserved built-in: synthesizes code rather than only calling tools; distinct from plain tool-calling CLIs | LOW (already exists) | Keep and construct from harness defaults (`create_harness(tools=..., instructions=...)` or kwargs splat into `CodeAgent`). No new work; protect in every phase. |
| Declarative domain bundles (`Toolkit` → Skills migration path) | Libraries + preamble + usage guidance as versioned, installable packs; competitors' marketplaces are younger and fragmented | MEDIUM | Keep `Toolkit`; port 1–2 to Skills as proof. Depends on: skills loading. Marketplace commands (`add marketplace`, `install/list/invoke`) are ours on top. |
| Skills marketplace commands (add marketplace, install/list/invoke) | Claude Code has official marketplace (`/plugin`, `claude.com/plugins`); a small curated marketplace makes this CLI extensible without forks | MEDIUM | Ours: registry + installer over local `./.agent/skills` loading underneath. Depends on: skills loading, slash registry. PROJECT.md Active requirement. |
| Grep-first code understanding (agentic grep/READ, no index to maintain) | Zero-infra repo navigation that works offline day one; defers the heavyweight index project without blocking usefulness | LOW | Ours: agentic grep/READ conventions. Explicit PROJECT.md decision (index deferred). Ripgrep-backed; OKF module covers large-document navigation. |
| Tiered memory backends (local markdown → Hindsight → memsearch/Milvus) | Solo/offline default with team and enterprise upgrades behind one `MemoryStore` seam; competitors couple memory to their cloud | MEDIUM | Adapters behind harness `memory={"stores": [...]}`. v1 ships local markdown only; Hindsight opt-in, memsearch enterprise later. Depends on: session wiring, `/memory`. |
| Review flows (`/review` with modes, pre-merge checks via headless runner) | Codex-class `/review`; runs in CI through non-interactive mode so the same reviewer works locally and in automation | MEDIUM | Ours over task loop + GitHub loop. Depends on: GitHub loop, non-interactive mode. P2 polish per gap analysis — candidate single v1 differentiator alongside `/btw`. |
| Fuzzy file/symbol picker (`@`-mention / `/add` class) for prompt context | Competitors' `@`-mention pickers are beloved; terminal fuzzy picker attaches files/symbols without an IDE extension | LOW | Ours; no browser/IDE extension in v1. Depends on: task loop. P2 polish. |
| Effort presets over model params + budgets (fast/thorough class) | Harness `effort="auto|off|minimal|low|medium|high|xhigh|max"` as UX presets; cheaper/faster vs stronger/deeper without manual knob-twiddling | LOW | Harness-native presets + ours: CLI flags/commands. Layer after Plan/Act. Depends on: `/model` switching. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Persistent semantic code index in v1 | "The agent should just know the codebase" | A project of its own (embeddings, incremental updates, staleness); blocks v1 for marginal gain over grep | Grep-first agentic navigation (PROJECT.md Out of Scope); index is its own later phase |
| Enforced token budgets (halt on cost) | Fear of runaway spend | Policy decision with false-positive halts mid-task; display creates trust, enforcement creates support load | Cost display only (`/cost`); halting deferred (PROJECT.md decision) |
| Auto model/effort routing (thinking-budget style) | "Just pick the best model" | Opaque behavior, hard to debug, couples to provider-specific knobs while harness moves fast | Manual `/model` switching first; effort presets as explicit user choice |
| AgentCore as required path | AWS-native teams want one blessed backend | Couples CLI to AWS control plane (IAM, regions, billing); breaks offline/local story | AgentCore stays opt-in backend behind existing seams; local defaults (PROJECT.md constraint: AWS-optional, never AWS-required) |
| IDE extension / browser companion in v1 | "Point at open tabs" | Separate product surface (extension APIs, review, distribution); terminal picker covers the need | Terminal fuzzy file/symbol picker; no IDE extension for v1 (gap analysis §4) |
| Auto-commit / auto-push without approval | Fewer keystrokes | Silent mutation of shared history; conflicts with deny-first permissions posture | Stage + show diff, require explicit approval; non-interactive mode only with pre-set policy in CI |
| Real-time multi-user collaboration | Pairing use cases | Session identity, conflict resolution, presence — a second product | Named resumable sessions + shareable transcripts; one actor per session |
| Custom vector DB / bespoke memory service in v1 | Perceived recall quality | Duplicates tested upstream `MemoryManager`/`MemoryStore` defaults; ops burden | Tiered adapters behind the harness seam; local markdown default |

## Feature Dependencies

```
[Conversational task loop]
    └──requires──> [Session wiring + --session-id]
    └──requires──> [File/shell tool surface]
                       └──requires──> [Permissions policy + approval prompts]
                                           └──requires──> [Sandbox presets]
[Plan / Act modes]
    └──requires──> [Conversational task loop]
    └──requires──> [Permissions policy + approval prompts]
[Anytime steering] ──requires──> [Task loop] + [Interrupt/cancel]
[/btw side questions]
    └──requires──> [Subagents (agents-as-tools)]
                       └──requires──> [Task loop] + [Session identity]
[Skills marketplace commands]
    └──requires──> [Skills loading (./.agent/skills)]
                       └──requires──> [Slash-command registry]
[Memory tiers] ──requires──> [Session wiring] + [/memory command]
[GitHub loop] ──requires──> [Tool surface] + [Non-interactive mode]
[Review flows] ──requires──> [GitHub loop] + [Non-interactive mode]
[Cost display] ──requires──> [Task loop] + [Session identity]
[/model switching] ──requires──> [Provider config]
[Effort presets] ──enhances──> [Plan/Act modes] + [/model switching]
[Fuzzy picker] ──enhances──> [Task loop]

[Enforced budgets] ──conflicts──> [Display-only cost v1] (policy contradiction)
[AgentCore-required] ──conflicts──> [AWS-optional constraint]
[Semantic index v1] ──conflicts──> [Grep-first v1] (competing strategies, same phase)
```

### Dependency Notes

- **Task loop requires session wiring + tool surface:** no loop without resumable state and something to act with; session wiring is build step 1.
- **Tool surface requires permissions/HITL:** tools must land gated or the first release runs ungated edits/shell — ship together.
- **Plan/Act requires permissions primitives:** Plan mode is a read-only intervention policy; reuse the same gating, do not build a parallel system.
- **`/btw` requires subagents:** side questions are subagent spawns by definition; the primitive must exist first.
- **Marketplace requires local skills loading:** distribution without a loader is a dead end; `./.agent/skills` first, registry second.
- **Review flows require GitHub loop + headless runner:** the same reviewer must work interactively and in CI.
- **Conflicts are phasing guards:** index-vs-grep, budgets-vs-display, AgentCore-vs-AWS-optional are decided in PROJECT.md — roadmap must not schedule both sides in v1.

## MVP Definition

### Launch With (v1)

Parity checklist against Claude Code behavior is the acceptance bar (PROJECT.md).

- [ ] Conversational task loop — the product itself
- [ ] Plan / Act modes with approval gate — closest to proven competitor behavior
- [ ] Permissions policy + approval prompts + sandbox presets — unsafe agents do not ship
- [ ] Session wiring + resume by UUID (`--session-id`, `/resume`, flush-on-exit) — continuity is table stakes
- [ ] Slash-command registry with `/model /resume /compact /clear /memory /cost /diff /review /context` — navigability
- [ ] File/shell tool surface + `/diff` — ability to act
- [ ] Cost/token display (no enforcement) — spend trust
- [ ] Manual `/model` switching (Bedrock default, override-friendly) — provider freedom
- [ ] Local skills loading + project memory file (`/init`, `/memory`) — extensibility + repo conventions
- [ ] Anytime steering + `/btw` side questions — the product's stated UX bet over competitors
- [ ] GitHub loop (read issues/PRs, branch, implement, test, open PR) — Core Value: single ask → PR
- [ ] One differentiator to land the story: `/btw` (cheap, high demo value) — plus review flows if capacity allows

### Add After Validation (v1.x)

- [ ] Skills marketplace commands (add/install/list/invoke) — trigger: local skills proven, external demand appears
- [ ] MCP config wiring — trigger: first integration request (GitHub/Linear/Sentry)
- [ ] Non-interactive / headless runner + JSON output — trigger: first CI/scripting user
- [ ] Memory tier 2 (Hindsight opt-in) — trigger: team asks for cross-session recall beyond markdown
- [ ] Fuzzy file/symbol picker — trigger: prompt-context friction reported
- [ ] Effort presets layered over Plan/Act — trigger: users want fast/thorough without manual knobs

### Future Consideration (v2+)

- [ ] Persistent semantic code index — own phase, after grep-first validated (PROJECT.md Out of Scope)
- [ ] Enforced token budgets — policy decision for later, after display data exists
- [ ] Auto model/effort routing — after manual switching patterns are understood
- [ ] Memory tier 3 (memsearch/Milvus enterprise backend) — after team-tier demand
- [ ] IDE companion — after CLI is established

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Task loop | HIGH | MEDIUM | P1 |
| Plan / Act + approval | HIGH | MEDIUM | P1 |
| Permissions + sandbox | HIGH | MEDIUM | P1 |
| Session resume by UUID | HIGH | LOW | P1 |
| Slash registry + core commands | HIGH | LOW | P1 |
| File/shell tools + /diff | HIGH | MEDIUM | P1 |
| Cost display | HIGH | LOW | P1 |
| /model switching | HIGH | MEDIUM | P1 |
| Local skills + memory file | HIGH | LOW | P1 |
| Anytime steering | HIGH | MEDIUM | P1 |
| /btw side questions | HIGH | LOW | P1 |
| GitHub loop | HIGH | MEDIUM | P1 |
| Skills marketplace | MEDIUM | MEDIUM | P2 |
| MCP wiring | MEDIUM | LOW | P2 |
| Non-interactive mode | MEDIUM | MEDIUM | P2 |
| /review flows | MEDIUM | MEDIUM | P2 |
| Fuzzy picker | MEDIUM | LOW | P2 |
| Effort presets | MEDIUM | LOW | P2 |
| Hindsight memory tier | LOW (v1) | MEDIUM | P3 |
| Semantic index | LOW (v1) | HIGH | P3 |
| Enforced budgets | LOW (v1) | MEDIUM | P3 |
| Auto routing | LOW (v1) | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Claude Code | Codex CLI | Our Approach |
|---------|-------------|-----------|--------------|
| Plan/Act modes | `plan → default → acceptEdits → auto → dontAsk → bypassPermissions`; `Shift+Tab` cycling; `--permission-mode` flag | Sandbox (read-only / workspace-write / full) × approval policies; `--ask-for-approval`; `--yolo`/bypass flags | Plan/Act as v1 mode: read-only plan + approval gate, presets over harness interventions; mode cycling UX |
| Steering a running task | Interrupt + reprompt; Esc-interrupt queue in newer versions | Interrupt + reprompt; `codex exec resume` to continue runs | Anytime steering: freeform input injected at next tool-call boundary, task undisturbed (UX bet) |
| Side questions | New session / context-switch | New run | `/btw` escape: spawned subagent answers, main task untouched |
| Skills / plugins | SKILL.md + official marketplace (`/plugin`, `claude.com/plugins`); project + personal scopes | Skills + MCP; `config.toml` layers + `AGENTS.md` | Harness `AgentSkills` (`./.agent/skills`) + marketplace commands; port 1–2 Toolkits as proof; keep `Toolkit` for code-preamble |
| Session resume | `claude -c` / `-r <name>` / `--resume` picker; `/resume`, `/rename`; permissions NOT restored on resume | `codex exec resume`; session continuity in desktop wrappers | Harness `SessionManager` (file default) + `--session-id`, named sessions, flush-on-exit; reclaim policy ours |
| Cost display | `/cost` (tokens + USD), `/usage` (plan remainder), `/stats` | Usage via wrappers (cc-switch syncs Codex logs); reasoning-level picker affects spend | `/cost` per session + task from existing callback metrics + tracing; display only, no v1 budgets |
| Model switching | `/model` mid-session; flags at launch | `-m/--model` flag + `/model` picker with reasoning/effort levels | `/model` picker + config over harness provider strings; Bedrock default, override-friendly; no auto-routing v1 |
| Context visibility | `/compact` (+focus), `/clear`, `/context` grid | Compact/resume in wrappers | Harness truncation + compact-at-~85% + caching; `/compact /clear /context` UX ours |
| Slash commands | ~15 built-ins (`/init /clear /compact /config /cost /context /doctor /memory /model /plan /rename /resume /rewind /status …`) | `/model`, `/review` (+modes), profiles | Thin `/` registry over hooks; v1 set per PROJECT.md, expand toward parity checklist |
| Permissions/sandbox | Graduated permission modes + ML auto classifier + `CLAUDE.md` rules | OS-enforced sandbox (Seatbelt/Landlock, network-disabled) + approvals | Native HITL/guardrails underneath; policy file + prompts + env scrub + sandbox presets ours; deny-first |
| Non-interactive / CI | `-p` print mode + piping | `codex exec` first-party CI runner with pre-set sandbox/approvals | Headless runner with explicit policy + JSON output (v1.x) |
| GitHub workflow | Companion flows + MCP (GitHub/Linear) | `/review` modes, Codex Cloud remote tasks | Full loop in v1 per PROJECT.md: issues/PRs, branch, implement, test, open PR, review comments, CI checks |
| Memory | `CLAUDE.md` + auto memory; session-scoped | `AGENTS.md` + profiles | Tiered: local markdown default → Hindsight opt-in → memsearch/Milvus; one `MemoryStore` seam |
| Context picker | `@`-mention files, `/add`; IDE companions | Workspace context; Codex Cloud diff apply | Terminal fuzzy file/symbol picker (v1.x); no IDE extension v1 |
| Code execution | Bash tool in sandbox | Sandbox + full-auto env | Keep differentiator: `CodeAgent` + `python_repl` with three interpreter backends, constructed from harness defaults |

## Sources

- PROJECT.md and docs/competitive-gap-analysis.md (project context; Tavily pro research on Claude Code, Codex CLI, Muse Code; Strands-native session/memory/model/skills findings)
- Claude Code community references: cheat sheets documenting permission modes (`plan/default/acceptEdits/auto/dontAsk/bypass`), `Shift+Tab` cycling, and the 15-command built-in set (`/cost /context /resume /compact /model /memory /rename /rewind …`); session flags (`-c/--continue`, `-r/--resume`)
- Claude Code plugin/skill references: `/plugin` marketplace flow (`marketplace add`, `owner/repo` installs), `claude.com/plugins` official marketplace, SKILL.md portability notes
- Codex CLI references: sandbox modes (read-only / workspace-write / full access), approval policies, `-m/--model` + `/model` reasoning picker, `codex exec` (+`resume`) non-interactive/CI role, `/review` modes, `config.toml` layers + `AGENTS.md`
- Agent-UX research notes: `Shift+Tab` plan-mode status indicator as expected UX; OpenCode `plan` agent / `plan_enter`→`plan_exit` pattern; Gemini CLI read-only Plan Mode precedent; cancel-vs-quit signal handling (Aider SIGINT-cancels, OpenCode abort endpoint)
- awesome-cli-coding-agents directories (Claude Code / Codex / Gemini / OpenCode / Aider / Pi / Goose landscape; multi-provider in-shell model switching as table stakes)

---
*Feature research for: conversational coding CLI on existing Python agent library (SUBSEQUENT milestone)*
*Researched: 2026-09-23*
