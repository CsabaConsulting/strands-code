# Project Research Summary

**Project:** Strands Code — conversational coding CLI on Strands harness
**Domain:** Conversational agentic coding CLI (Claude Code / Codex CLI class) built on an existing Python agent library (SUBSEQUENT milestone)
**Researched:** 2026-09-23
**Confidence:** HIGH

## Executive Summary

Strands Code is a conversational coding CLI in the Claude Code / Codex CLI class, built as new construction on top of an existing Python agent library (`CodeAgent` + `python_repl`, `Toolkit` bundles, OKF knowledge navigation, Rich rendering). Every serious competitor converges on the same five-layer shape — REPL front-end over command router, SDK-owned agent loop, tool/execution surface, session+memory persistence, rendering/observability tail — and the existing library already owns three of those layers. The recommended approach is therefore harness-first, gaps-only: compose `CodeAgent` from `strands-harness` defaults (`create_harness()` + passthrough kwargs) and build only the genuinely new top band (REPL, slash router, Plan/Act gate, anytime steering, `/btw` side channel, session resume, skills loader, GitHub flow). New CLI stack is Typer + prompt_toolkit + Rich with questionary, PyGithub, httpx, and platformdirs in support; ripgrep/fzf/`gh` stay optional system binaries, never pip deps.

The key risks are operational, not architectural: runaway tool loops burning money silently (no turn cap or budget enforcement exists today), context-window blowup degrading quality before it errors, destructive file/git actions with no reversibility, prompt injection via repo content/issues/skills (the CLI's home turf maximizes exposure), session resume silently losing work, Experimental-upstream churn breaking the CLI on routine `uv sync`, and AWS coupling breaking the offline default. All seven have structural mitigations — turn/step budgets + loop circuit-breakers with the loop, staged context management + ingest truncation, deny-first permissions below the model layer, config-write gating + sandboxing, `flush()`-on-exit + kill-and-resume tests, pin-and-gated resync discipline, lazy `boto3` + local defaults — and each maps to a specific roadmap phase so prevention lands with the capability it protects, not as later polish.

## Key Findings

### Recommended Stack

The CLI layer is Typer 0.27.2 (entry point, subcommands, `CliRunner` smoke tests) over a prompt_toolkit 3.0.53 REPL (multiline editing, history, slash/`@` completers, bottom toolbar, anytime-steering input) with Rich 15.0.0 as the shared renderer — the line-streaming REPL matches Claude Code/Codex UX and composes with streaming output, while Textual fullscreen fights it (deferred to an optional later mode). Support: questionary 2.1.1 for one-off confirms/pickers, PyGithub 2.10.0 for the GitHub loop (`GITHUB_TOKEN` contract, `gh` CLI as auth fallback), httpx 0.28.1 for marketplace downloads, platformdirs 4.11.12 for per-user global config. Already owned and never re-decided: `strands-agents` 1.57.0, `strands-harness` 0.1.2, `smolagents`, `Jinja2`, `Rich`, `PyYAML`, `uv`, pytest. See STACK.md for full version table, alternatives, and per-variant behavior (offline, no-token, missing binaries). Details: [STACK.md](./STACK.md).

**Core technologies:**
- Typer 0.27.2: CLI framework (`run`, `resume`, `skills`, `--session-id`) — type-hint-driven help + completion, 2026 consensus successor to raw Click
- prompt_toolkit 3.0.53: interactive REPL — typing-centric interaction, completers, toolbar, steering input at tool-call boundary
- Rich 15.0.0: terminal rendering (Markdown, diffs, Live streaming, cost/context panels) — already owned, zero new deps
- strands-harness 0.1.2 + strands-agents 1.57.0: agent loop, sessions, skills, memory, interventions, effort presets — compose, don't rebuild
- questionary 2.1.1: approval prompts and `/model` picker — rides prompt_toolkit, no renderer conflict
- PyGithub 2.10.0: testable GitHub loop with `gh` fallback — typed, mockable, CI-friendly

### Expected Features

Parity checklist against Claude Code behavior is the v1 acceptance bar. The product itself is the conversational task loop; everything else is gating (Plan/Act, permissions+sandbox), continuity (session resume, slash registry, context commands), action (file/shell tools + `/diff`), trust (cost display, `/model` switching), extensibility (skills + memory file), the stated UX bet (anytime steering + `/btw`), and the Core Value closer (GitHub loop: single ask → PR). Details: [FEATURES.md](./FEATURES.md).

**Must have (table stakes):**
- Conversational task loop — users expect a REPL that plans multi-step work and executes it
- Plan / Act modes with approval gate — read-only plan → approve → act; `Shift+Tab`-style cycling
- Permissions policy + approval prompts + sandbox presets — unsafe agents do not ship; tools land gated or not at all
- Session resume by UUID (`--session-id`, `/resume`, flush-on-exit) — continuity is table stakes
- Slash-command registry (`/model /resume /compact /clear /memory /cost /diff /review /context`) — navigability
- File/shell tool surface + `/diff` viewer — end python_repl-only actuation
- Cost/token display per session and task (display only, no enforcement) — spend trust
- Manual `/model` switching across providers (Bedrock default, override-friendly) — provider freedom
- Local skills loading + project memory file (`/init`, `/memory`) — extensibility + repo conventions
- Anytime steering + `/btw` side questions — the product's UX bet over competitors
- GitHub loop (read issues/PRs, branch, implement, test, open PR) — Core Value delivery

**Should have (competitive):**
- Skills marketplace commands (add/install/list/invoke) — extensibility without forks; trigger: local skills proven
- MCP config wiring — trigger: first integration request
- Non-interactive / headless runner + JSON output — trigger: first CI/scripting user; same reviewer locally and in CI
- `/review` flows with modes — candidate second v1 differentiator alongside `/btw`
- Fuzzy file/symbol picker (`@`-mention class) — trigger: prompt-context friction reported
- Effort presets layered over Plan/Act — trigger: users want fast/thorough without manual knobs

**Defer (v2+):**
- Persistent semantic code index — own phase after grep-first validated (PROJECT.md Out of Scope)
- Enforced token budgets — policy decision after display data exists
- Auto model/effort routing — after manual switching patterns are understood
- Memory tier 3 (memsearch/Milvus enterprise) — after team-tier demand
- IDE companion — after CLI is established

### Architecture Approach

Five-layer shape: conversational CLI band (REPL + router + Plan/Act gate + steering + `/btw`) over SDK-owned agent-loop core (`CodeAgent` from harness defaults + hooks + callback handler), tool/execution surface (`python_repl` + file/shell + subagents-as-tools + OKF + AgentSkills), and session/memory/model/config persistence. New code lives in a separate `strands_code_cli/` package (one module per CLI gap, each mapping 1:1 to a build phase); the library stays importable without CLI deps. Three load-bearing patterns: harness composition with thin passthrough, tool-boundary steering via hooks (never thread-kill), subagents-as-tools with isolated context (side channel never writes main history). Details: [ARCHITECTURE.md](./ARCHITECTURE.md).

**Major components:**
1. REPL + input loop (`loop.py`) — owns the conversation: prompt, streaming render, Ctrl-C/ESC handling; routes and renders only
2. Command router (`router.py`) — leading-`/` dispatch to handlers; everything else goes to the agent as a task
3. Plan/Act mode gate (`modes.py`) — read-only proposal + approval checkpoint; intervention-policy swap, not a second agent
4. Anytime-steering queue (`steering.py`) — freeform input drained at `BeforeToolInvocation` boundary; ESC stops current step only
5. `/btw` side channel (`sidechannel.py`) — isolated child agent + read-only snapshot; renders aside, main history untouched
6. Session/skill/policy/GitHub wiring (`session_cli.py`, `skills_cli.py`, `policy.py`, `github_flow.py`) — harness-native managers underneath, CLI owns routing, lifecycle, UX, and flow

### Critical Pitfalls

Seven critical pitfalls, each mapped to the phase that must prevent it. Full analysis, warning signs, and recovery steps: [PITFALLS.md](./PITFALLS.md).

1. **Runaway tool loops burn money silently** — enforce turn/step budgets at the harness layer (not as model instructions) + loop circuit-breaker (same tool + same args N times → stop and ask); counting/plumbing ships with the loop, hard caps can follow.
2. **Context-window blowup degrades quality before it errors** — staged pressure response (warn → prune → mask → compact), truncate bulky tool results at ingest (~1500 tokens + pointer), `/compact` takes focus and preserves the policy block verbatim; regression test that safety rules survive compaction.
3. **Destructive file/git actions with no reversibility** — deny-first policy enforced below the model layer (credential paths, `rm -rf`, force-push, writes outside tree) that survives allow-all; snapshot every file before edit (`/diff` + `/undo`); push behind explicit approval.
4. **Prompt injection via repo content, issues, and tool output** — structural, not model-hope: untrusted content labeled data-only, config/skill writes gated by approval, sandbox + egress controls, MCP description audits; quarterly red-team test with a planted injection.
5. **Session resume that silently loses work** — `session_manager` + explicit `flush()`-on-exit from the first session phase; keep session / conversation / memory separated per upstream; kill-and-resume (`SIGKILL` → resume → state intact) acceptance test.
6. **Building on Experimental upstream without a churn bulkhead** — lock working versions, deliberate resync with the full 177-test suite + message-shape regression test as gate, thin wrappers with `.get()`-tolerant accessors, add the missing CI test gate.
7. **AWS coupling that breaks the offline default** — lazy `boto3`, local interpreters + file sessions + markdown memory as zero-credential default, every AWS seam config-selected with graceful fallback; offline-install CI job as gate.

## Implications for Roadmap

Based on research, suggested phase structure (follows the ARCHITECTURE.md build order; each step is a shippable CLI increment; harness defaults are config, not phases):

### Phase 1: Session Wiring + REPL Skeleton
**Rationale:** No loop without resumable state; session wiring is build step 1 and unblocks everything stateful.
**Delivers:** `loop.py` + `router.py` skeletons, `session_manager` file-local wiring, `--session-id` routing, flush-on-exit, actor identity, start/end + reclaim policy.
**Addresses:** Session resume by UUID; conversational task loop foundation; slash registry skeleton.
**Avoids:** Session resume loss (Pitfall 5); AWS coupling (Pitfall 7 — choose file-local defaults here).

### Phase 2: File/Edit/Shell Surface + `/diff`
**Rationale:** Ends python_repl-only actuation; gives the agent something real to act with before any gating or modes.
**Delivers:** `strands-agents-tools` file/shell tools alongside `python_repl`, `/diff` viewer, ingest-truncation rule (~1500 tokens + pointer), `ExceptionClassName:`-prefixed errors.
**Addresses:** File/shell tool surface; grep-first code understanding conventions.
**Avoids:** Context blowup via bulky results (Pitfall 2, ingest half); python_repl-only debt trap.

### Phase 3: Permissions/HITL Gate + CI Setup
**Rationale:** Tools must land gated — shipping Phase 2 ungated is a one-incident catastrophe; the CI gate + pin policy must exist before further harness work.
**Delivers:** `policy.py` (deny-first policy file, ask/allow prompts, env scrub, sandbox presets) over `interventions`/`guardrails`; offline-install CI job; pinned-and-gated resync policy; message-shape regression test.
**Addresses:** Permissions + sandbox presets; Plan/Act prerequisite (read-only policy reuse).
**Avoids:** Destructive actions (Pitfall 3); prompt injection structural controls (Pitfall 4, first half); untrusted-code-execution default; upstream churn (Pitfall 6).

### Phase 4: Plan/Act Modes + Anytime Steering
**Rationale:** Mode gate swaps the Phase 3 intervention policy; steering hooks the Phase 2 tool boundary — both depend on 2+3.
**Delivers:** `modes.py` (Plan read-only + approval checkpoint, mode cycling UX), `steering.py` (queue drained at tool-call boundary), ESC-cancels-step semantics.
**Addresses:** Plan / Act modes; anytime steering; interrupt/cancel foundation.
**Avoids:** Thread-kill interruption anti-pattern; noisy-prompt fatigue (smart-intervention tuning).

### Phase 5: `/model` + `/cost` + Context Commands
**Rationale:** Reads session/conversation state from Phase 1; cost counting/plumbing must exist before runaway incidents, even though hard caps stay deferred.
**Delivers:** `/model` picker + provider config (override-friendly), `/cost` reporter over accumulated metrics + per-session usage object, `/compact` (with focus + policy preservation) / `/clear` / `/context-size`, staged context thresholds.
**Addresses:** Manual model switching; cost display; context visibility.
**Avoids:** Runaway loops (Pitfall 1, counting half); context blowup (Pitfall 2, management half).

### Phase 6: Skills Loading + Marketplace
**Rationale:** Distribution without a loader is a dead end — `./.agent/skills` first, registry second.
**Delivers:** `skills_cli.py` (AgentSkills loader + add/install/list/invoke), port of 1–2 Toolkits to Skills as proof, skill provenance + auto-load policy, `/memory` + project memory file (`/init`).
**Addresses:** Local skills + memory file; marketplace commands; Toolkit→Skills proof.
**Avoids:** Prompt injection via skills (Pitfall 4, provenance half); custom-store debt trap.

### Phase 7: Subagents + `/btw` Side Channel
**Rationale:** Needs steering-safe boundaries (Phase 4) + context snapshots (Phase 5); the primitive must exist before the UX.
**Delivers:** `sidechannel.py` (isolated child agent, read-only snapshot, side-panel render), helper-subagent + `todos` checklist, `/btw` escape.
**Addresses:** Subagents; `/btw` side questions (cheap, high demo value — the v1 story).
**Avoids:** Side-channel-writes-history anti-pattern; invisible-subagent UX pitfall (checklist + progress surfacing).

### Phase 8: Memory Tiers
**Rationale:** Layers on session wiring (Phase 1) + `/memory` (Phase 6) behind the same `memory={"stores": [...]}` seam.
**Delivers:** Local markdown default shipped; Hindsight opt-in; memsearch adapter stub; extraction-cadence policy; reclaim/expiry policy.
**Addresses:** Tiered memory backends (v1: local only).
**Avoids:** Custom memory-service debt; unbounded session-file growth.

### Phase 9: GitHub Loop + Polish + Parity
**Rationale:** The same reviewer must work interactively and in CI — requires tools (2), permissions (3), subagents (7); polish lands last when there is something to polish.
**Delivers:** `github_flow.py` (read issues/PRs, branch-per-task worktrees, implement, test, open PR, review comments, CI checks), fuzzy file/symbol pickers, security review, Claude Code parity checklist as acceptance.
**Addresses:** Full GitHub loop (single ask → PR); `/review` flows; non-interactive/headless runner; effort presets.
**Avoids:** Push-without-approval; mega-diff/unreviewable sessions (branch-per-task, `/diff`, commit cadence); issues-as-instructions injection (Pitfall 4, final half).

### Phase Ordering Rationale

- Dependencies flow top-down: session → tools → permissions → modes/steering → model/cost/context → skills → subagents → memory → GitHub/polish. No phase is buildable before its dependencies without rework (FEATURES.md dependency graph).
- Groupings follow the architecture: one module per CLI gap, so phases land as whole files (`session_cli.py`, `policy.py`, `modes.py`…) not cross-cutting edits.
- Pitfall prevention lands with the capability it protects: budgets with the loop, deny-list before push powers, flush with sessions, provenance with skills — never as later polish.

### Research Flags

Phases likely needing deeper research during planning (`$gsd-plan-phase --research-phase <N>`):
- **Phase 3 (Permissions/HITL):** intervention/policy/`.cedar` semantics move fast on Experimental upstream; verify exact flag shapes against the installed harness version at plan time.
- **Phase 7 (Subagents + `/btw`):** helper-subagent + `todos` plugin API and context-snapshot plumbing need version-pinned verification.
- **Phase 8 (Memory tiers):** Hindsight `retain`/`recall`/`reflect` API-key scoping and memsearch billing/ops tradeoffs need fresh verification.
- **Phase 9 (GitHub loop):** PyGithub-vs-`gh` endpoint coverage for review comments + CI checks status; verify any new endpoints at plan time.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Session/REPL):** file sessions + Typer + prompt_toolkit REPL are well-documented, established patterns.
- **Phase 2 (File/shell tools):** `strands-agents-tools` adoption is a documented swap, not research.
- **Phase 5 (Model/cost/context):** provider-string switching and cost-metric rendering follow existing callback-handler seeds.
- **Phase 6 (Skills loading):** `AgentSkills` local loading convention is settled; marketplace is thin registry work.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All CLI versions verified against PyPI JSON API 2026-09-23; locked Strands versions confirmed latest; harness-first direction corroborated by gap analysis + codebase map |
| Features | HIGH | Competitor behavior cross-checked across official docs, cheat sheets, and community references; scoped against PROJECT.md Active/Out-of-Scope |
| Architecture | HIGH for Strands composition / MEDIUM for competitor internals | Harness composition from official SDK/harness/session docs + PyPI; competitor internals from public docs and cheatsheets, not source |
| Pitfalls | HIGH for CLI-generic modes / MEDIUM for Strands churn details | Empirical bug study + documented cost/inject incidents for generic modes; upstream lifecycle docs + locked versions for churn specifics |

**Overall confidence:** HIGH

### Gaps to Address

- Competitor internals (MEDIUM): reconstructed from docs/cheatsheets, not source — validate UX details (`Shift+Tab` cycling, `/btw` isolation semantics) by testing against the real CLIs during Phase 4/7 planning.
- Harness Experimental churn (MEDIUM): flag names and hook registration shapes may drift between 0.1.x minors — every harness-touching phase must verify exact helper names against the installed version; the Phase 3 message-shape regression test is the standing guard.
- Cost-cap policy (open decision): v1 is display-only per PROJECT.md; the hard-cap follow-up needs a policy decision (default cap level, bypass rules) before enforcement work is scheduled.
- `HARNESS_CONTRACT` export: referenced as a drift-detection aid but not verified — confirm it exists in the installed harness during Phase 3, else drop the reference.

## Sources

### Primary (HIGH confidence)
- PyPI JSON API (`pypi.org/pypi/{typer,prompt_toolkit,rich,PyGithub,questionary,textual,strands-agents,strands-harness,click,pyyaml,platformdirs,httpx}/json`) — all stack versions verified 2026-09-23
- [Strands Harness SDK docs](https://strandsagents.com/docs/user-guide/sdk) — loop + tools/memory/sessions/plugins/interventions composition
- [Strands harness docs](https://strandsagents.com/docs/user-guide/harness) — `create_harness` defaults
- [strands-harness 0.1.2 on PyPI](https://pypi.org/project/strands-harness/0.1.2/) — resumable sessions, plain-`Agent` return
- [Strands session management docs](https://strandsagents.com/docs/user-guide/concepts/agents/session-management) — SessionManager abstraction
- `docs/competitive-gap-analysis.md` + `.planning/codebase/` + `.planning/PROJECT.md` — project context, harness-first direction, v1 scope bars

### Secondary (MEDIUM confidence)
- [Claude Code commands docs](https://code.claude.com/docs/en/commands) — `/resume /branch /btw /clear /compact` semantics
- [Codex CLI cheatsheet](https://shipyard.build/blog/codex-cli-cheat-sheet) — session model, sandbox/approval taxonomy
- Empirical bug study of Claude Code/Codex/Gemini CLI session & state failures (~6%) — [arxiv.org](https://arxiv.org/html/2603.20847)
- Terminal-agent scaffolding (staged context thresholds, session/mode/MCP taxonomy) — [arxiv.org](https://arxiv.org/html/2603.05344v1)
- Runaway-cost incidents and budget-guard patterns — [nexgismo.com](https://www.nexgismo.com/blog/ai-agent-budget-guards-stop-runaway-api-costs), [supra-wall.com](https://www.supra-wall.com/learn/ai-agent-runaway-costs)
- Prompt-injection mitigations (structural) + repo-file/MCP attack cases — [llm-wiki](https://github.com/vietbui1999ru/llm-wiki/blob/HEAD/docs-site/concepts/indirect-prompt-injection.mdx)
- Claude Code permissions model (allow/deny, deny overrides, YOLO-mode risk) — [claude-code-ultimate-guide](https://github.com/florianbruniaux/claude-code-ultimate-guide/blob/HEAD/guide/security/enterprise-governance.md)
- Context hygiene practices (`/clear` boundaries, `/compact` focus, small diffs) — [openhands.dev](https://www.openhands.dev/blog/claude-code-best-practices-agentic-coding), [blink.new](https://blink.new/blog/agentic-coding-best-practices)
- Community consensus 2026: Typer-over-Click for new Python CLIs; prompt_toolkit REPL vs Textual fullscreen; PyGithub + `gh`-fallback — corroborated across multiple sources

### Tertiary (LOW confidence)
- [Strands Python API reference](https://strandsagents.com/docs/api/python) — module surface index only; method details not verified, re-check at plan time
- Strands experimental-feature policy (pin-to-minor guidance) — [FEATURE_LIFECYCLE.md](https://github.com/strands-agents/harness-sdk/blob/HEAD/team/FEATURE_LIFECYCLE.md), [COMPATIBILITY.md](https://github.com/strands-agents/harness-sdk/blob/HEAD/team/COMPATIBILITY.md)

---
*Research completed: 2026-09-23*
*Ready for roadmap: yes*
