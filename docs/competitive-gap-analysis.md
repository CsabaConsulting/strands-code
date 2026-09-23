# strands-code competitive gap analysis
## Claude Code / Codex CLI / Muse Code vs. sample-strands-code-agent

Goal: turn this fork (`CsabaConsulting/strands-code`, forked from
`aws-samples/sample-strands-code-agent` v0.4.0) into a Claude Code / Codex CLI
competitor built on the Strands harness, while preserving its existing strengths.

Method: (1) repo inventory of `strands_code_agent/` + `tests/` +
`pyproject.toml`; (2) Tavily deep research (`tvly research --model pro`) on
Claude Code, Codex CLI, Muse Code; (3) Tavily deep research on Strands-native
session/memory/model/skills plus memsearch vs Hindsight vs local markdown.
Strategy: use Strands-native features first; only build genuine CLI gaps.

## Terminology: "Strands Harness"

"Strands Harness" is the umbrella monorepo
(`strands-agents/harness-sdk`: Python SDK + TypeScript SDK + docs + supporting
packages), not a separate SDK. The "Strands Agents SDK" is the agent loop
inside it. So "leverage the Harness" = use the Python `strands-agents` package
(+ `strands-agents-tools`) we already depend on, rather than reinventing loop,
session, memory, model, hook, or tracing primitives.

## What to preserve (your 6 built-ins — confirmed)

1. `CodeAgent(Agent)` (`strands_code_agent/code_agent.py:39`, wiring
   `131-149`): auto-registers `python_repl` + assembles system prompt. Keep —
   this is our differentiator (code-generation-first vs plain tool-calling).
2. `Toolkit` (`toolkits.py`): libraries / initialization_code /
   usage_instructions / domain_specific_code aggregated into authorized imports,
   preamble, prompt sections (`code_agent.py:91-115`). Keep as the
   code-preamble mechanism.
3. Pluggable `PythonInterpreter` backends (`local_sandboxed.py`,
   `local_exec.py`, `agentcore.py`; `README.md:123-163`): keep all three.
4. `CodeAgentCallbackHandler` (`callback_handler.py:32-80`, default at
   `code_agent.py:36`): keep terminal rendering.
5. Knowledge/OKF module (`knowledge/bundle.py`, `concept.py`, `search.py`):
   keep for large-document navigation.
6. Solution user-agent registration (`__init__.py:1`): keep housekeeping.

## Strands-native answers to your questions

### 1. Persistent session memory → yes, use Strands native

Strands separates three things (do not conflate them):

- Session management = resume where you left off (full conversation + agent
  state). Built-in: `SessionManager` abstraction, `FileSessionManager` /
  `S3SessionManager` / snapshot managers, default local-file storage; plus
  `AgentCoreMemorySessionManager` (STM conversation persistence + LTM
  strategies for preferences/facts/summaries, with flush/close semantics).
- Conversation management = staying inside the context window during a session.
- Memory (`MemoryManager` + `MemoryStore`) = durable knowledge across sessions.
  Built-in stores include AgentCore Memory store, Bedrock Knowledge Base store,
  Zep store; the manager exposes `search_memory` / `add_memory` tools with
  background extraction (default ~every 5 turns) and a `flush()` API.

Our gap is purely wiring: `CODE_AGENT_INSTRUCTIONS` currently states the
interpreter "resets completely with each new user message". Fix = pass a
`session_manager` (file-based locally, AgentCore in AWS) and a
`memory_manager` into `CodeAgent.__init__` instead of building custom memory.
CLI work remaining (genuinely ours): actor identity + `--session-id` routing,
session start/end + reclaim policies, `flush()` before shutdown, namespace /
writable-store policy, local-dev fallback. No custom vector DB needed for v1.

### 2. Model providers → yes, use Strands native

The SDK is provider-agnostic: same agent code runs against Bedrock (default),
Nova, Anthropic, OpenAI (+Responses API), Google, Cohere, Mistral, LlamaAPI,
LiteLLM, Ollama, SageMaker, Writer, Crusoe, Fireworks, OpenRouter, Nebius, OVH,
plus community vLLM / xAI / SGLang / MLX / NVIDIA NIM and custom providers
(`pip install 'strands-agents[bedrock|anthropic|openai|...]'`; switch provider
class, no agent rewrite). The earlier "HAS NONE" note was overstated: the SDK
has it, `CodeAgent` just never exposes it (model only via `**kwargs`).
Fix = `/model` picker + config file selecting the provider class/credentials,
defaulting to Bedrock; subagent-model override later. Effort: S/M, all CLI UX.

### 3. Skills / slash commands / modes / effort → Skills native, commands are ours

- Skills ARE native: `AgentSkills(skills="./skills/")` plugin gives on-demand
  domain instructions without bloating the system prompt (takes a tool call to
  activate). Keep `Toolkit` for code-preamble config; add `AgentSkills` for
  markdown instruction packs (this is the skill/plugin story you want).
- Slash commands are NOT native: no built-in slash parser. Build a thin
  command registry + parser (leading `/`) on top of Strands hooks
  (`AgentInitialized`, `MessageAdded`, memory hook providers). Start with
  `/model /resume /compact /clear /memory /cost /diff /review`.
- Modes/effort are NOT native as UX, but primitives exist: turn limits, token
  budgets, cancellation, stop reasons, streaming. Implement effort modes as CLI
  presets over model params + tool/step budgets (e.g. fast = cheaper model,
  fewer steps; thorough = stronger model, higher budgets).

### 4. "IDE picker" — what it is

In competitors it is just a context selector: fuzzy file/line picker
(`@`-mention files, `/add`), sometimes a Chrome/VS Code companion that points
the agent at open tabs. For our CLI the equivalent is a terminal fuzzy picker
for files/symbols to attach to the prompt — no browser or IDE extension
required for v1.

### 5. Security — half native, half ours

Native: guardrails, Human-in-the-Loop approval modes (CLI/web/custom),
AgentCore session isolation + CloudWatch observability, HiddenLayer
prompt-injection integration, tracing (OpenTelemetry). Ours to build:
permissions policy file (`deny` lists, `blockReadsOutsideDirs`), env scrubbing,
ask/allow prompts before edits/network, sandbox presets around the existing
`SandboxedPythonInterpreter` allowlist. Your `imports.py` auto-authorize +
sandbox timeout is the right seed — promote it to an explicit policy.

### 6. Agentic memory options (memsearch / Hindsight / markdown)

All three plug into `MemoryManager`/`MemoryStore` or plain `@tool` tools —
none replaces Strands memory; they are store choices:

- Simple markdown (OpenClaw-style, e.g. Memweave pattern: markdown + SQLite
  FTS5/BM25 ± local embeddings): 0.5–2 days, zero infra, full data residency,
  strong lexical recall for filenames/literals. Best default for solo/local and
  offline. Implement as a local `MemoryStore` adapter.
- Hindsight (`hindsight-strands`, MIT + Cloud pay-as-you-go): `retain` /
  `recall` / `reflect` tools, TEMPR fusion (semantic + BM25 + graph +
  temporal), `hindsight-coding-agents` auto-ingests repo/git history. ~1 day
  install, 2–4 days for git auto-ingest. Best for small/medium teams wanting
  temporal reasoning ("what changed recently") with minimal glue. Watch API-key
  scoping/RBAC on older tiers vs newer bank-scoped keys.
- memsearch (Zilliz, markdown source of truth + Milvus hybrid dense+BM25+RRF,
  CLI + Python API): 1–2 day prototype, 3–5 days production. Best for
  high-QPS/multi-tenant production needing RBAC, namespaces, CMK,
  data-residency and Zilliz Cloud scaling. Costs: self-host ops or per-vector/CU
  billing.

Recommendation: tiered — (a) ship local markdown/file-session default now
(zero deps, matches CLI offline story); (b) offer Hindsight as opt-in team
memory (`pip install hindsight-strands`, bank per repo); (c) offer
memsearch/Milvus as the enterprise backend. All behind the same
`MemoryStore` interface so users switch without agent rewrites.

## Revised recommendation: adopt `strands-harness`, don't go lower level

Correction to the analysis above: `strands-agents` (PyPI v1.56, source
`strands-py/` in the `strands-agents/harness-sdk` monorepo) is the low-level
SDK — loop plus primitives. `strands-harness` (PyPI v0.1.1, source
`harness-py/` in the same monorepo) is the higher-level, batteries-included
agent built on top of it: `create_harness()` composes model loop, tools,
just-in-time context, sessions, hooks, and memory into tested defaults with a
tuned system prompt, and returns a plain `strands.Agent` (every default
overridable). Going lower level (raw SDK primitives) is the wrong direction
for our feature list — it means rebuilding what the harness already ships:

- File/shell tools (`read`/`write`/`edit`, shell, web, `programmatic_tool_caller`
  sandbox) — replaces "route everything through `python_repl`" (P0-1).
- Sessions on by default (`./.agent/sessions`, resume by id) + long-term memory
  distilled to markdown (`./.agent/memory`) (P0-5).
- Skills loading (`./.agent/skills`) + `todos`/`environment` plugins + helper
  subagent with checklist (P1: skills, subagents).
- Context management (truncate bulky tool results ~1500 tokens, compact at
  ~85%, offload to storage, prompt caching) + `effort="auto|off|minimal|low|
  medium|high|xhigh|max"` presets (P1 context, effort modes).
- `interventions="ask"|"smart"|policy|.cedar` tool-call gating (security P0-6).
- `mcp_servers`, `builtin_tools` pinning, background-task policy, model
  `"provider/name"` strings across Bedrock/Anthropic/OpenAI/Google/Ollama/LiteLLM
  (P0-4, P0-7). A `strands` CLI (`@strands-agents/cli`) wraps the same agent —
  useful reference for our CLI UX.

Architecture: keep `CodeAgent(Agent)` subclass as the differentiator, but
construct it from harness defaults instead of a bare `Agent` — e.g. pass our
`python_repl` tool, Toolkit preamble/instructions, and OKF hooks through
`create_harness(tools=..., instructions=..., plugins=..., memory=...,
session=...)`, or build kwargs via `harness_agent_kwargs_from_config()` and
splat into `CodeAgent(...)`. Dependencies stay loose on purpose (experimental
phase, harness moving fast): `strands-agents>=0.1.0` unchanged,
`strands-harness>=0.1` added with no upper pin (see `pyproject.toml`).

Lean-vs-configurable, per the harness configuration reference: `create_harness`
takes string flags for the common case (`context_manager="auto"|"agentic"|False`,
`memory=True|{dir, stores}|False`, `effort`, `caching`, `interventions`,
`session`, `skills`) — that is the lean path. Anything deeper is a passthrough:
unnamed kwargs go straight to the `Agent` constructor, so `memory_manager=...`
overrides `memory`, a custom `ContextManager` (built-in modes, presets like
`proactive_summarization`/`large_tool_offloading`/`overflow_protection`/
`stale_tool_cleanup`, or fully custom strategies) overrides `context_manager`,
and `memory={"stores": [...]}` swaps the backend while keeping harness policy.
The harness also exports its building blocks (`resolve_memory`,
`build_system_prompt`, `resolve_interventions`, `HARNESS_CONTRACT`) for
compose-with-SDK. Note the whole context-management surface is flagged
Experimental upstream, so expect churn and keep our wrapper thin. Genuinely-ours
work shrinks to: slash-command registry, permissions policy UX, fuzzy file
picker, `/model`/`/cost`/`/review` commands, memory-tier backends (Hindsight /
memsearch adapters), and the code-first REPL/Toolkit/OKF layer itself.

## Repo strategy: keep this fork, depend on the monorepo

Do NOT re-fork from `strands-agents/harness-sdk`. The two repos are different
layers: this fork (~3k lines incl. tests) is the product/differentiator
(CodeAgent code-first loop, Toolkit, sandboxed/AgentCore interpreters, OKF
knowledge, Rich callback) — none of which exists in the monorepo. The monorepo
is the platform (Python + TypeScript SDKs, `harness-py`/`harness-ts` packages,
WASM bridge, docs site, MCP server, `strandly` dev CLI). Forking it means
owning SDK maintenance and cross-language CI, and you would still have to port
the sample's code over. Correct setup: keep this fork as the product repo, add
`strands-harness` as a dependency (and raise `strands-agents` to `>=1.x`), and
treat `strands-cli`/harness sources as read-only reference (sparse checkout,
not a fork). Only fork the monorepo if you need to change SDK loop internals
upstream won't accept — not our case.

## Decoupling principle: AWS-optional, never AWS-required

AgentCore stays an opt-in backend, never the default path. Rationale: AgentCore
(configuration: memory IDs, actor provisioning, IAM, regions, runtime billing)
couples the CLI to AWS control-plane resources, while everything it offers has
a portable equivalent behind the same Strands interface (file/S3 session
managers, `MemoryStore` adapters, local interpreters). Concretely:

- Keep `python_environments/agentcore.py` (already isolated + tested) but
  default to local interpreters; select via config, with lazy `boto3` import
  and graceful fallback when AWS is absent.
- Prefer the harness's local defaults (`./.agent/sessions`, `./.agent/memory`
  markdown) over `AgentCoreMemorySessionManager`; reach AgentCore Memory only
  through the `MemoryStore`/`memory={"stores": [...]}` seam when the user opts in.
- Bedrock remains a first-class *choice* (LLM provider string, KB memory store,
  optional embeddings/rerank) but never load-bearing: embeddings default to
  local (e.g. ONNX via memsearch) and the CLI's default model must be
  override-friendly, since the harness default is Bedrock (needs AWS creds).
  Note the existing `agentcore = ["boto3..."]` optional extra in
  `pyproject.toml` already models this pattern — extend it, don't harden it.

## Revised build order (harness-first, gaps-only)

1. Session wiring: `session_manager` (file locally / AgentCore in AWS) +
   `--session-id` + flush-on-exit. Removes the "resets each message" limit.
2. File/edit/Bash surface: prefer `strands-agents-tools` (`file_read`,
   `shell`, file editor equivalents) + `/diff` viewer over routing everything
   through `python_repl`.
3. Permissions/HITL: policy file + approval prompts + env scrub (native HITL +
   guardrails underneath).
4. `/model` picker + provider config (native providers underneath).
5. Slash registry + `AgentSkills("./skills/")` loader; port 1–2 Toolkits to
   Skills as proof.
6. Memory tiers: local markdown store → Hindsight opt-in → memsearch/Milvus
   adapter; add `/memory /compact /resume` commands + extraction-cadence policy.
7. Subagents (agents-as-tools pattern), context commands, `/cost` +
   tracing/telemetry, then P2 polish (worktree PR flow, pickers,
   security-review).

## P0/P1/P2 detail (unchanged substance, native mapping noted)

- P0: tools+diff (use strands-tools), slash commands (ours), hooks (Strands
  hook framework + our parsers), MCP (SDK supports MCP servers as tools —
  wire `--mcp-config`), session/memory (native managers + our routing),
  permissions (native HITL/guardrails + our policy), models (native providers
  + our picker).
- P1: subagents (agents-as-tools pattern), skills (native `AgentSkills`),
  context commands (ours over conversation/session managers), observability
  (native OTel tracing + our `/cost`/metrics).
- P2: effort presets, worktree PR flow, fuzzy file picker, security-review.
