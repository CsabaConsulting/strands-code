# Architecture Research

**Domain:** Conversational coding CLI on an agent-loop SDK (Strands)
**Researched:** 2026-09-23
**Confidence:** HIGH for Strands harness composition (official docs + PyPI); MEDIUM for competitor internals (public docs/cheatsheets, not source).

## Standard Architecture

### System Overview

Every serious conversational coding CLI (Claude Code, Codex CLI, and the Strands harness reference CLI) converges on the same five-layer shape: a REPL front-end over a command router, an agent-loop core owned by the SDK, a tool/execution surface, session+memory persistence, and a rendering/observability tail. Our project maps onto this directly — the existing library already owns three of the layers, so the CLI is a new top layer plus wiring, not a rebuild.

```
┌─────────────────────────────────────────────────────────────┐
│                    Conversational CLI layer                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ REPL +   │  │ Command  │  │ Plan/Act │  │ Steering +   │  │
│  │ input    │  │ router   │  │ mode gate│  │ /btw channel │  │
│  │ loop     │  │ (slash)  │  │          │  │              │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
│       │             │             │               │          │
├───────┴─────────────┴─────────────┴───────────────┴──────────┤
│                    Agent-loop core (SDK-owned)               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  CodeAgent(Agent) built from harness defaults:      │    │
│  │  create_harness(tools, instructions, plugins,       │    │
│  │    memory, session, skills, interventions, effort)  │    │
│  │  + hooks (AgentInitialized, MessageAdded,           │    │
│  │    Before/AfterToolInvocation) + callback handler   │    │
│  └─────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│              Tool / execution / knowledge surface            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │python_repl│  │file/shell │  │ subagent │  │ OKF knowledge│  │
│  │+ Toolkits │  │+ MCP tools│  │-as-tool  │  │ + AgentSkills│  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘  │
├─────────────────────────────────────────────────────────────┤
│              Session / memory / model / config               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Session  │  │ Memory   │  │ Model    │  │ Config +     │  │
│  │ managers │  │ manager  │  │ providers│  │ policy files │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

Existing code already fills the middle and bottom-middle: `CodeAgent` + `Toolkit` (composition), `python_environments/` (execution backends), `knowledge/` (OKF navigation), `callback_handler.py` + `utils.py` (presentation). What is genuinely new is the top band (REPL, router, Plan/Act gate, steering injection, `/btw` side channel, session store with UUID resume, skills loader, GitHub flow) plus thin wiring of harness-native session/memory/skills/interventions into `CodeAgent.__init__`.

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| REPL + input loop | Owns the conversation: readline/prompt, streaming render, Ctrl-C/ESC handling, background-task display | Single `cli/loop.py`: `while True: read → route → dispatch`; prompt_toolkit or plain input for v1; never blocks the agent thread on render |
| Command router (slash parser) | Leading-`/` dispatch to handlers; everything else goes to the agent as a task | Thin registry `cli/commands/*.py` (`name → handler`); `/model /resume /compact /clear /memory /cost /diff /review /btw /status`; unknown `/` → usage error, not agent call |
| Plan/Act mode gate | Plan = read-only proposal + approval checkpoint; Act = full tool access | CLI-level flag + approval prompt between modes; implemented as intervention policy swap (`interventions="ask"` in Plan, `"smart"`/policy in Act), not a second agent |
| Anytime-steering injection | Freeform user input lands at the next tool-call boundary without killing the task | Hook on `BeforeToolInvocationEvent` (or message queue checked per event-loop cycle): pending user text appended to conversation before next model step; ESC cancels current step only |
| `/btw` side-question channel | Spawned subagent answers a side question; main task state untouched | agents-as-tools pattern: snapshot read-only context, run child agent, render answer in side panel; never writes to main session history |
| Subagent orchestrator | Main task fans out to helper agents with checklists | Harness built-in helper subagent + `todos` plugin for v1; SDK multiagent (Graph/Swarm) only if task-DAG needs it later |
| Session store + resume | Persist conversation + agent state per UUID; `--session-id` / `/resume` reload | Harness-native `session_manager` (file-based `./.agent/sessions` locally); CLI adds actor identity, `--session-id` routing, start/end + `flush()`-on-exit |
| Skills loader | On-demand markdown instruction packs without bloating the system prompt | Native `AgentSkills(skills="./.agent/skills")` plugin; CLI adds marketplace commands (add/install/list/invoke) + local `./.agent/skills` loading underneath |
| GitHub integration | Read issues/PRs, branch, implement, test, open PRs, comments, CI checks | Plain tool surface (`gh` CLI subprocess or GitHub API tools) + worktree-per-task convention; no SDK primitive — pure CLI tools phase |
| Context/effort controls | Stay in-window (`/compact`, truncate bulky results) + effort presets | Harness `context_manager="auto"` + `effort="minimal…max"` string flags; `/context-size` is a read-only reporter over the conversation manager |
| Permissions/HITL gate | Ask/allow before edits, network, or irreversible actions | Native `interventions="ask"\|"smart"\|policy\|.cedar` + guardrails underneath; CLI owns the policy file (`deny` lists, `blockReadsOutsideDirs`), env scrubbing, and the ask prompt UX |
| Rendering + cost telemetry | Streamed terminal output, token/cost per session and task | Extend existing `CodeAgentCallbackHandler` (Rich) + `get_response_metrics`; `/cost` reads accumulated metrics; no enforced budgets in v1 |

## Recommended Project Structure

```
strands-code/
├── strands_code_agent/       # existing library — keep as-is, extend by wiring
│   ├── code_agent.py         # CodeAgent: add harness kwargs (session/memory/skills/interventions)
│   ├── toolkits.py           # existing Toolkit presets (+ 1-2 ported to Skills as proof)
│   ├── python_environments/  # existing backends — unchanged
│   ├── knowledge/            # existing OKF — unchanged
│   ├── callback_handler.py   # extend: streaming events, cost line
│   └── utils.py              # extend: cost aggregation helpers
├── strands_code_cli/         # NEW top-level package: the conversational layer
│   ├── __main__.py           # `python -m strands_code_cli` entry + arg parsing (--session-id, -p print mode)
│   ├── loop.py               # REPL: read → route → dispatch; signal/ESC handling
│   ├── router.py             # slash-command registry + parser (leading `/`)
│   ├── modes.py              # Plan/Act flag + approval checkpoint + intervention swap
│   ├── steering.py           # anytime-steering queue drained at tool-call boundaries
│   ├── sidechannel.py        # /btw subagent side-question channel
│   ├── session_cli.py        # --session-id routing, start/end, flush-on-exit, actor identity
│   ├── skills_cli.py         # marketplace add/install/list/invoke over AgentSkills
│   ├── github_flow.py        # issue/PR/branch/test/open-PR flow (gh subprocess tools)
│   ├── pickers.py            # fuzzy file/symbol picker for @-mentions and /add (v1: terminal picker)
│   └── policy.py             # permissions policy file load + ask/allow prompts + env scrub
└── .agent/                   # runtime convention (gitignored): sessions/ memory/ skills/
```

### Structure Rationale

- **`strands_code_cli/` separate from `strands_code_agent/`:** the library is the differentiator (code-first REPL/Toolkit/OKF) and stays importable without CLI deps; the CLI is a thin consumer. Mirrors the upstream split (SDK vs harness vs `strands` CLI reference).
- **`loop.py` owns no agent logic:** it routes and renders only. All agent behavior (tools, memory, gating) lives in harness config or SDK hooks — keeps the loop testable with a fake agent.
- **One module per CLI gap:** each file maps 1:1 to a build phase (router → modes → steering → sidechannel → session → skills → github), so phases land as whole files, not cross-cutting edits.
- **Keep wrappers thin around harness:** `code_agent.py` gains passthrough kwargs (`session_manager`, `memory_manager`, `skills`, `interventions`, `effort`) rather than reimplementing them; string-flag config (`memory=True|{dir,stores}|False`, `context_manager="auto"`) is the lean path, full objects only where we override.

## Architectural Patterns

### Pattern 1: Harness composition with passthrough (create_harness + thin subclass)

**What:** Build `CodeAgent` from harness defaults instead of a bare `Agent`: pass our `python_repl` tool, Toolkit preamble/instructions, and OKF hooks through `create_harness(tools=..., instructions=..., plugins=..., memory=..., session=..., skills=...)`, or build kwargs via the harness config helper and splat into `CodeAgent(...)`. Unnamed kwargs fall through to the `Agent` constructor, so `memory_manager=...` overrides `memory` and a custom `ContextManager` overrides `context_manager`. The harness returns a plain `Agent` — no wrapper or hidden abstraction.
**When to use:** Always for this project — it is the decided direction (PROJECT.md "Harness-first, gaps-only").
**Trade-offs:** Pro: tested defaults for sessions, context management, effort presets, skills loading, interventions; con: harness surface is flagged Experimental upstream and moves fast — mitigated by keeping our wrapper thin and depending unpinned (`strands-harness>=0.1`, no upper pin).

**Example:**
```python
# Illustrative composition — exact helper names follow installed harness version
harness_kwargs = build_harness_kwargs(
    tools=[python_repl, file_read, file_write, shell],
    instructions=[CODE_AGENT_INSTRUCTIONS, toolkit_instructions],
    session=session_id_or_config,   # file-based locally
    memory={"stores": [local_markdown_store]},  # swap to Hindsight/memsearch later
    skills="./.agent/skills",
    interventions="ask" if mode == "plan" else "smart",
    effort="medium",
)
agent = CodeAgent(**harness_kwargs)  # CodeAgent stays an Agent subclass
```

### Pattern 2: Tool-boundary steering via hooks (not thread-kill)

**What:** Anytime steering and ESC handling hook the agent event lifecycle (`BeforeToolInvocationEvent` / `MessageAddedEvent` / `AfterToolInvocationEvent`) instead of killing threads. Pending user input sits in a queue the loop drains at the next tool-call boundary; the hook appends it to the conversation so the model sees it as a steering message on its next step. Cancel stops the current step only; the session and task plan survive.
**When to use:** For all mid-run user input (steering text, ESC interrupt, mode switch mid-task).
**Trade-offs:** Pro: no corrupted tool state, no lost session; con: steering latency is one tool call (acceptable and matches Codex/Muse Code UX the user prefers over command-gated steering).

**Example:**
```python
from strands.hooks import BeforeToolInvocationEvent

def steer_at_boundary(event: BeforeToolInvocationEvent) -> None:
    pending = steering_queue.drain()  # freeform input typed while agent runs
    if pending:
        event.agent.messages.append({"role": "user", "content": pending})

agent.add_callback(steer_at_boundary)  # registration shape per SDK hooks docs
```

### Pattern 3: Subagents as tools with isolated context (main + /btw)

**What:** Both main-task delegation and `/btw` side questions use the agents-as-tools pattern: a child agent gets a scoped prompt (and for `/btw`, a read-only context snapshot) and returns a result object. The main session history is never written by the side channel — `/btw` answers render in a side panel. Main-task subagents report back through the `todos`/checklist plugin.
**When to use:** `/btw` for side questions; helper-subagent + checklist for open-ended main-task subtasks; SDK Graph/Swarm only if a real task DAG emerges later.
**Trade-offs:** Pro: isolation is structural (no prompt-leak bugs), matches harness built-in helper agent; con: side channel needs explicit context snapshot plumbing — keep it read-only file/message slices, not full state clone.

## Data Flow

### Request Flow

```
[User keystroke in REPL]
    ↓
[router.py: leading "/"?] ──yes──→ [Command handler] → [session/skills/model/policy action] → [render result]
    ↓ no
[Plan/Act gate: Plan + mutating intent?] ──yes──→ [approval prompt] ──deny──→ [back to REPL]
    ↓ allow / Act mode
[Agent invocation: agent(task)]
    ↓
[SDK event loop: model → tool call → observation → model …]
    ↓                                    ↑
[BeforeTool hook: drain steering queue] ─┘  [ESC: stop current step only]
    ↓
[Callback handler streams text/tool/cost events] → [Rich terminal]
    ↓
[AfterInvocation: session persist + memory extract + metrics accumulate]
```

### State Management

```
[Session store: ./.agent/sessions/<uuid>] ←→ [SessionManager: load on --session-id/resume, flush on exit]
[Memory dir: ./.agent/memory/*.md] ←→ [MemoryManager: search_memory/add_memory tools, background extract ~every 5 turns]
[Agent state: key-value on agent.state] ←→ [Hooks read/write per-event (steering queue pointer, mode flag, cost totals)]
```

Single-threaded synchronous model throughout (matches existing codebase: no threads/asyncio; per-call timeouts bound long runs). Background tasks (if any) are harness-policy-driven, not CLI threads — the loop polls for their completion lines.

### Key Data Flows

1. **Normal ask:** REPL → router (not a command) → Plan/Act gate → `agent(task)` → streamed render → session persist + cost accumulate → REPL.
2. **Anytime steering:** keystrokes during run → `steering_queue` → `BeforeToolInvocation` hook drains → appended as user message → next model step adjusts; task plan object untouched.
3. **Side question (`/btw`):** router → `sidechannel.py` snapshots read-only context → child agent runs → answer renders in side panel; main loop/event state never mutated.
4. **Resume:** `--session-id <uuid>` or `/resume` → `SessionManager` loads messages + state → loop continues; `/compact` summarizes via conversation manager to free context without ending the session.
5. **Skills:** `/skills invoke <name>` or model-triggered `AgentSkills` activation → markdown pack loaded on demand → folded into context for that task only (system prompt stays lean).
6. **GitHub loop:** `/review` or natural ask → read issue/PR tools → branch (worktree) → implement via agent → test via shell tool → open PR → report URL; all as tool calls inside one session.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Solo dev, local (v1 target) | Monolith CLI as drawn. File session manager + local markdown memory. No changes needed. |
| Small team, shared repo | Add Hindsight team-memory store behind the same `memory={"stores": [...]}` seam (per-repo bank); S3 session manager if sessions must roam. CLI code unchanged — config only. |
| High-QPS / multi-tenant / enterprise | Swap to memsearch/Milvus store (RBAC, namespaces, CMK, residency) + S3 sessions + OTel tracing on; consider splitting GitHub flow into a service. Still no CLI rewrite — all behind store/manager seams. |

### Scaling Priorities

1. **First bottleneck:** context window on large repos — fixed by harness context management (bulky-result truncation ~1500 tokens, compact at ~85%, offload to storage) + grep-first code understanding; persistent semantic index explicitly deferred to a later phase.
2. **Second bottleneck:** memory quality across sessions — fixed by moving up the store tiers (markdown → Hindsight → memsearch), never by forking the `MemoryManager` interface.

## Anti-Patterns

### Anti-Pattern 1: Rebuilding SDK primitives in the CLI

**What people do:** Write a custom session store, vector DB, slash-skill engine, or approval framework from scratch.
**Why it's wrong:** Duplicates tested harness defaults (sessions, `MemoryManager`/`MemoryStore`, `AgentSkills`, interventions/HITL) and couples us to maintenance upstream already does.
**Do this instead:** Harness-first, gaps-only: CLI owns router, pickers, policy UX, and GitHub flow; everything else is config + passthrough kwargs. Keep wrappers thin (Experimental surface churns).

### Anti-Pattern 2: Routing all file/shell work through `python_repl`

**What people do:** Keep the v0 pattern where every file read/edit/shell call is model-generated Python.
**Why it's wrong:** Opaque diffs, no tool-call gating per operation, poor `/diff` story, harder permission policy.
**Do this instead:** Prefer `strands-agents-tools` file/shell tools alongside `python_repl`; keep `python_repl` + Toolkits as the code-generation differentiator, not the only actuator. `/diff` views editor-tool operations.

### Anti-Pattern 3: Letting the side channel write to main history

**What people do:** Implement `/btw` as "just another agent call on the same session" for simplicity.
**Why it's wrong:** Side Q&A pollutes the main task context, wastes window, and can derail the plan.
**Do this instead:** Isolated child agent + read-only snapshot; render aside; main session appends nothing (matches Claude Code `/btw` and Codex `/side` semantics).

### Anti-Pattern 4: Thread-kill interruption

**What people do:** Implement ESC/steering by killing the worker thread or dropping the whole run.
**Why it's wrong:** Corrupts in-flight tool state, loses the task plan, forces full restart.
**Do this instead:** Stop-current-step + hook-drained steering queue at the next tool-call boundary (Pattern 2).

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| LLM providers (Bedrock/Anthropic/OpenAI/local) | Native provider classes; `/model` picker switches class + credentials via config file | Harness default model is Bedrock (needs AWS creds) — CLI default must stay override-friendly; AWS-optional always |
| GitHub (issues/PRs/CI) | `gh` CLI subprocess tools or GitHub API tools + worktree-per-task | Ours to build; read-only (read issue/PR, CI checks) before mutating (branch, open PR) |
| Hindsight team memory (opt-in) | `hindsight-strands` `retain`/`recall`/`reflect` tools behind `MemoryStore` seam | Watch API-key scoping on older tiers; git auto-ingest is the extra 2–4 days |
| memsearch/Milvus (enterprise opt-in) | Store adapter behind `memory={"stores": [...]}` | Self-host ops vs per-vector/CU billing decision lives here, not in CLI code |
| MCP servers | SDK MCP-as-tools wiring via `--mcp-config` | CLI only parses config and forwards; no custom MCP framework |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI loop ↔ agent core | `agent(task)` call + callback-handler event stream + hooks registry | Loop never reaches into model internals; all influence via messages, hooks, interventions |
| CLI ↔ session/memory | `SessionManager` / `MemoryManager` interfaces only (file locally, S3/AgentCore opt-in) | CLI adds routing (`--session-id`), lifecycle (flush-on-exit), identity, policy — never storage internals |
| CodeAgent ↔ harness | `create_harness(...)` kwargs + passthrough `**kwargs` to `Agent`; building blocks (`resolve_memory`, `build_system_prompt`, `resolve_interventions`) for deeper swaps | Pin loosely, resync deliberately; do not fork the monorepo |
| Toolkits ↔ Skills | Toolkits stay the code-preamble mechanism; `AgentSkills` is the markdown-instruction mechanism | Port 1–2 Toolkits to Skills as proof, then keep both (not a migration) |

## Suggested Build Order (for roadmap)

Dependencies flow top-down; each step is a shippable CLI increment on the previous one. Genuinely-ours work only — harness defaults are config, not phases.

1. **Session wiring** (no dependencies) — `session_manager` + `--session-id` + flush-on-exit. Removes the "resets each message" limit; unblocks everything stateful. Plus REPL skeleton + router so there is something to attach it to.
2. **File/edit/shell surface + `/diff`** (depends on 1) — `strands-agents-tools` tools + diff viewer. Ends python_repl-only actuation.
3. **Permissions/HITL gate** (depends on 2 — needs real tools to gate) — policy file + ask/allow prompts + env scrub over native interventions/guardrails.
4. **Plan/Act + anytime steering** (depends on 2, 3 — mode gate swaps the intervention policy; steering hooks the tool boundary) — modes flag, approval checkpoint, steering queue + ESC.
5. **`/model` + `/cost` + context commands** (depends on 1 — reads session/conversation state) — provider picker/config, cost reporter over `get_response_metrics`, `/compact /clear /context-size`.
6. **Skills commands** (depends on 1, 5) — `AgentSkills` loader + marketplace add/install/list/invoke; port 1–2 Toolkits as proof.
7. **Subagents + `/btw` side channel** (depends on 4, 5 — needs steering-safe boundaries + context snapshot) — helper subagent + todos checklist + isolated side channel.
8. **Memory tiers** (depends on 1, 6) — local markdown default → Hindsight opt-in → memsearch adapter; `/memory` + extraction-cadence policy.
9. **GitHub loop + polish** (depends on 2, 3, 7) — issue/PR tools, worktree flow, fuzzy pickers, security review, parity checklist vs Claude Code.

## Sources

- [Strands Harness SDK docs](https://strandsagents.com/docs/user-guide/sdk) — loop + tools/memory/sessions/plugins/interventions composition; harness-vs-SDK choice (HIGH)
- [Strands harness docs](https://strandsagents.com/docs/user-guide/harness) — `create_harness` defaults (tools, sessions, memory-to-markdown, skills, context mgmt, effort presets, helper subagent) (HIGH)
- [strands-harness 0.1.2 on PyPI](https://pypi.org/project/strands-harness/0.1.2/) — sessions resumable by id, plain-`Agent` return, overridable defaults (HIGH)
- [Strands session management docs](https://strandsagents.com/docs/user-guide/concepts/agents/session-management) — SessionManager abstraction, File/S3/snapshot managers (HIGH)
- [Strands Python API reference](https://strandsagents.com/docs/api/python) — hooks, interventions, memory, session, plugin, callback-handler module surface (MEDIUM — index page, method details not verified)
- [Claude Code commands docs](https://code.claude.com/docs/en/commands) — `/resume /branch /btw /clear /compact` semantics incl. side-question isolation (MEDIUM)
- [Codex CLI cheatsheet](https://shipyard.build/blog/codex-cli-cheat-sheet) — `/new /resume /fork /compact /side /status` session model (MEDIUM)
- Project context: `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`, `docs/competitive-gap-analysis.md` (HIGH — repo-local)

---
*Architecture research for: conversational coding CLI on Strands agent SDK*
*Researched: 2026-09-23*
