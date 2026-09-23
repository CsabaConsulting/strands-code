---
last_mapped_commit: 4a23ae24e72098045e1d04b5328d95967221c4a0
last_mapped_at: 2026-09-22
---
<!-- refreshed: 2026-09-22 -->

# Architecture

**Analysis Date:** 2026-09-22

## System Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                      Agent / Composition                     │
├──────────────────┬──────────────────┬───────────────────────┤
│   CodeAgent      │     Toolkit      │  CallbackHandler      │
│  `strands_code_agent/code_agent.py` │  `strands_code_agent/toolkits.py` │ `strands_code_agent/callback_handler.py` │
└────────┬─────────┴────────┬─────────┴──────────┬────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                    Execution / Knowledge                     │
│         `strands_code_agent/python_environments/` + `strands_code_agent/knowledge/`  │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│  Store / Output / External                                   │
│  `strands.Agent` (upstream SDK) · Bedrock AgentCore API · OKF markdown bundles on disk · `/tmp` files │
└─────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| CodeAgent | `strands.Agent` subclass; merges toolkits into authorized imports, preamble, system prompt, and `additional_functions`; registers `python_repl` tool | `strands_code_agent/code_agent.py` |
| Toolkit | Dataclass bundling `libraries`, `initialization_code`, `usage_instructions`, `domain_specific_code` for the REPL | `strands_code_agent/toolkits.py` |
| PythonInterpreter (ABC) | `clear_state` / `execute_code` contract plus `get_tool()` that exposes the `python_repl` tool with STDOUT/STDERR observation formatting | `strands_code_agent/python_environments/base.py` |
| ExecPythonInterpreter | Unrestricted in-process `exec()` interpreter with dict state | `strands_code_agent/python_environments/local_exec.py` |
| SandboxedPythonInterpreter | Default interpreter; allowlisted imports + timeout via smolagents `LocalPythonExecutor` | `strands_code_agent/python_environments/local_sandboxed.py` |
| AgentCorePythonInterpreter | Remote Bedrock AgentCore code-interpreter sessions (lazy boto3 session, user-code serialization) | `strands_code_agent/python_environments/agentcore.py` |
| Prompt builders | `get_documentation` (signature + docstring rendering) and `get_import_string` / `extract_imports` (AST-based) feed the system prompt and import allowlist | `strands_code_agent/document_code.py`, `strands_code_agent/imports.py` |
| CodeAgentCallbackHandler | Rich terminal rendering of messages, code tool uses, and tool results | `strands_code_agent/callback_handler.py` |
| OKFBundle | Lazy-loaded, read-optimized navigator over a directory of markdown concepts (`find`/`read`/`children`/`toc`, `expand`, `context`, backlinks) | `strands_code_agent/knowledge/bundle.py` |
| Concept | Atomic knowledge unit dataclass (one `.md` file: id, type, title, body, links) | `strands_code_agent/knowledge/concept.py` |
| SearchIndex / KeywordSearchIndex | ABC plus default AND-with-OR-fallback keyword backend; seam for embedding backends | `strands_code_agent/knowledge/search.py` |
| pdf_to_okf_bundle | PDF TOC-bookmark → OKF bundle converter (pymupdf, lazy import) | `strands_code_agent/knowledge/pdf_to_okf_bundle.py` |
| Solution user-agent hook | Monkeypatches `botocore.session.Session.__init__` to append `AWSSOLUTION/SO0353` tag; imported for side effect on package init | `strands_code_agent/solution_user_agent.py` |
| Helpers | `image_to_base64`, `get_response_metrics` (Bedrock token/cost summary) | `strands_code_agent/utils.py` |

## Pattern Overview

**Overall:** Code-generation-first agent library over the Strands SDK (thin-subclass + tool-injection + prompt-assembly pattern).

**Key Characteristics:**

- `CodeAgent` does not orchestrate tool chains; it gives the model one primary action interface (`python_repl`) and injects domain capability as importable Python symbols.
- Toolkits are declarative capability bundles: allowlist entries, startup preamble, prompt guidance, and documented callables are merged at construction time (`strands_code_agent/code_agent.py:87-137`).
- Execution backends are swappable behind the `PythonInterpreter` ABC via the `python_interpreter_class` constructor argument; the knowledge subsystem is an independent, dependency-light library consumable either directly or inside a toolkit.

## Layers

**Agent / composition:**

- Purpose: Owns the public API (`CodeAgent`, `Toolkit`) and builds the agent: system prompt assembly, import authorization, REPL tool registration.
- Location: `strands_code_agent/code_agent.py`, `strands_code_agent/toolkits.py`, `strands_code_agent/__init__.py`
- Contains: Prompt templates (`CODE_AGENT_INSTRUCTIONS`, `CODE_PREAMBLE_TEMPLATE`, `TEMP_DIR_TEMPLATE`, `DOMAIN_SPECIFIC_DOC_TEMPLATE`), toolkit merge logic, `tools=[python_repl]` wiring.
- Depends on: Execution layer (interpreters), prompt-builder helpers, upstream `strands.Agent`.
- Used by: Consumer scripts such as `examples/pdf_to_okf_bundle/agent_with_knowledge.py`; downstream CLI (planned, not yet implemented).

**Execution:**

- Purpose: Runs model-generated Python and returns STDOUT/STDERR observations; controls isolation (unrestricted vs allowlisted vs remote).
- Location: `strands_code_agent/python_environments/`
- Contains: `PythonInterpreter` ABC plus three implementations (`local_exec.py`, `local_sandboxed.py`, `agentcore.py`).
- Depends on: `smolagents` (sandboxed), `boto3` (AgentCore, optional extra), `strands.tool` decorator for tool exposure.
- Used by: `CodeAgent` only (constructed in `code_agent.py:131-138`).

**Knowledge:**

- Purpose: File-based knowledge navigation (OKF bundles) usable standalone or injected into the REPL as domain symbols.
- Location: `strands_code_agent/knowledge/`
- Contains: `Concept` dataclass, `OKFBundle` navigator, `SearchIndex` ABC + keyword backend, PDF converter.
- Depends on: `pyyaml` (frontmatter parse); `pymupdf` lazily inside `pdf_to_okf_bundle` only.
- Used by: Consumer code directly, or via `Toolkit(domain_specific_code=[OKFBundle], initialization_code=...)` as shown in `examples/pdf_to_okf_bundle/agent_with_knowledge.py`.

**Presentation / observability:**

- Purpose: Human-facing terminal output and cost telemetry; no control-flow role.
- Location: `strands_code_agent/callback_handler.py`, `strands_code_agent/utils.py`
- Contains: Rich-based message/code/result rendering; `get_response_metrics` token/cost helper; `image_to_base64`.
- Depends on: `rich`.
- Used by: `CodeAgent` default `callback_handler`; example scripts.

## Data Flow

### Primary Request Path

1. Construct agent — toolkits merged into `authorized_imports`, `initialization_code`, `usage_instructions`, `domain_specific_code`; system prompt assembled from templates; `python_repl` tool registered (`strands_code_agent/code_agent.py:87-149`).
2. Model turn — `strands.Agent` loop emits `python_repl(code)` tool uses; each call runs `PythonInterpreter.execute_code` and returns `STDOUT:...` / `STDERR:...` observation text (`strands_code_agent/python_environments/base.py:24-42`).
3. Execution — default `SandboxedPythonInterpreter` runs code in `LocalPythonExecutor` with allowlisted imports and timeout; stdout salvaged from executor state on error (`strands_code_agent/python_environments/local_sandboxed.py:39-49`).
4. Rendering — `CodeAgentCallbackHandler.__call__` prints messages with syntax-highlighted code blocks and formatted tool results (`strands_code_agent/callback_handler.py:46-80`).

### Knowledge Navigation Flow

1. Build or open bundle — `pdf_to_okf_bundle(pdf, dir)` writes one `.md` concept per PDF TOC section, or `OKFBundle(path)` opens an existing directory.
2. Lazy load — first access scans `*.md` (skipping `index.md`/`log.md`), parses YAML frontmatter, extracts internal markdown links into `Concept.links`, builds the backlink index and search index (`strands_code_agent/knowledge/bundle.py:76-110`).
3. Navigate — `find(query)` → `read(concept_id)` → `children(concept_id)` / `expand` / `context`, or `toc()` fallback; used either by direct calls or by the agent when the bundle object is injected via a toolkit.

### Remote Execution Flow (AgentCore)

1. Lazy session — first `execute_code` creates a boto3 `bedrock-agentcore` client and starts a code-interpreter session (`strands_code_agent/python_environments/agentcore.py:98-109`).
2. Invoke — each call sends `invoke_code_interpreter(executeCode, {language, code})` and concatenates streamed `stdout`/`stderr` (`strands_code_agent/python_environments/agentcore.py:115-130`).
3. Teardown — `clear_state()` / `close()` stops the remote session; `__del__` best-effort stops it (`strands_code_agent/python_environments/agentcore.py:132-151`).

**State Management:**

- REPL state persists across tool calls within one interpreter lifetime but `CodeAgent` documents reset between user messages; `clear_state()` re-runs the preamble (local) or drops the remote session (AgentCore).
- `OKFBundle` caches concepts/backlinks/search index after first load per instance (`_ensure_loaded` guard); no cross-instance cache.
- Per-agent `tmp_dir` created under `/tmp` when `tmp_dir=True` and advertised in the system prompt (`strands_code_agent/code_agent.py:118-120`).

## Key Abstractions

**CodeAgent (Agent subclass):**

- Purpose: Single public entry point that turns declarative toolkits into a capable coding agent.
- Examples: `strands_code_agent/code_agent.py`, `examples/pdf_to_okf_bundle/agent_with_knowledge.py`
- Pattern: Constructor-assembled system prompt + tool injection; extra behavior via `tools=[...]` and Strands `**kwargs` (model, etc.).

**Toolkit (dataclass):**

- Purpose: The unit of domain capability: allowlist + preamble + prompt guidance + documented symbols.
- Examples: `strands_code_agent/toolkits.py` (`VISUALIZATION_TOOLKIT`, `DATA_ANALYSIS_TOOLKIT`)
- Pattern: Plain data merged by `CodeAgent.__init__`; `domain_specific_code` symbols are auto-imported (`get_import_string`) and auto-documented (`get_documentation`) into the prompt.

**PythonInterpreter (ABC + `get_tool`):**

- Purpose: Uniform execution seam: `execute_code(code) -> (stdout, stderr)` plus Strands `@tool`-wrapped `python_repl`.
- Examples: `strands_code_agent/python_environments/base.py`, `local_exec.py`, `local_sandboxed.py`, `agentcore.py`
- Pattern: Strategy — `CodeAgent(python_interpreter_class=...)` selects the backend; `python_interpreter_kwargs` forwarded.

**OKFBundle + Concept + SearchIndex:**

- Purpose: Filesystem-backed, read-optimized knowledge graph with a pluggable search backend.
- Examples: `strands_code_agent/knowledge/bundle.py`, `concept.py`, `search.py`
- Pattern: Lazy index build; `SearchIndex` ABC lets consumers substitute embedding search without touching navigation code.

## Entry Points

**Library import (`CodeAgent`, `Toolkit`, `AgentCorePythonInterpreter`):**

- Location: `strands_code_agent/__init__.py`
- Triggers: Any consumer `import` (also executes `solution_user_agent` side effect).
- Responsibilities: Public surface; keep `__all__` in sync when adding top-level exports.

**`CodeAgent(...)` constructor call:**

- Location: `strands_code_agent/code_agent.py:77-149`
- Triggers: Consumer code (e.g. `agent = CodeAgent(toolkits=[...])` then `agent("...")` via `strands.Agent.__call__`).
- Responsibilities: Toolkit merge, prompt assembly, interpreter construction, tool registration.

**Knowledge scripts (`OKFBundle`, `pdf_to_okf_bundle`):**

- Location: `strands_code_agent/knowledge/__init__.py`, `examples/pdf_to_okf_bundle/agent_with_knowledge.py`
- Triggers: Direct import/use; example run downloads a PDF, converts, and starts a bundle-backed agent.
- Responsibilities: Offline knowledge preparation and runtime navigation.

**No CLI / server entry point:**

- There is no `__main__.py`, console-script, or service handler; the README describes the CLI as planned direction layered on `strands-harness`. Do not assume one exists.

## Architectural Constraints

- **Threading:** Single-threaded synchronous model. No threads, asyncio, or workers in this repo; long runs are bounded by per-call `timeout_seconds` (default 180 in `CodeAgent`, 60 in interpreters) and AgentCore `session_timeout_seconds` (default 900).
- **Global state:** `DEFAULT_CODE_AGENT_CALLBACK_HANDLER` module-level singleton shared by all `CodeAgent()` instances that omit `callback_handler` (`strands_code_agent/code_agent.py:36`); `botocore.session.Session.__init__` monkeypatched at import (`strands_code_agent/solution_user_agent.py:18`). `OKFBundle` caches are per-instance only.
- **Circular imports:** None detected. Dependency direction is one-way: `code_agent.py` → interpreters/helpers; `knowledge/bundle.py` → `concept.py` + `search.py`; `python_environments/*` → `base.py`. `TYPE_CHECKING`-only import of `Concept` in `search.py` avoids a runtime cycle.
- **AWS-optional:** `boto3` is an optional `agentcore` extra; `AgentCorePythonInterpreter` is importable from the top level but only usable with credentials. Defaults stay local.

## Anti-Patterns

### Mutating caller-owned `tools` list in place

**What happens:** `CodeAgent.__init__` calls `tools.append(python_repl_tool)` when the caller passes a list (`strands_code_agent/code_agent.py:139-142`).
**Why it's wrong:** The caller's list is modified as a side effect; reusing it across agents accumulates duplicate entries.
**Do this instead:** Copy callers' lists (`tools = [*tools, python_repl_tool]`). Until fixed, always pass a fresh list or omit `tools`.

### Swallowing tracebacks into plain stderr strings

**What happens:** Both local interpreters catch `Exception` and return only `str(e)` as stderr (`local_exec.py:26-27`, `local_sandboxed.py:44-48`).
**Why it's wrong:** The agent and the developer lose the traceback frames needed to localize errors in generated code.
**Do this instead:** Keep the current observation contract (tests assert on it) and add opt-in full tracebacks, e.g. `traceback.format_exc()` behind a flag on `PythonInterpreter`.

## Error Handling

**Strategy:** Per-execution containment — every `execute_code` catches all exceptions and returns them as `(stdout, stderr)` strings; the tool layer maps empty output to `"Code executed successfully."`.

**Patterns:**

- Local: `exec()` errors → `str(e)` in stderr (`local_exec.py`); sandbox errors → stderr plus salvaged `_print_outputs` stdout (`local_sandboxed.py:39-49`).
- Remote: session-stop failures only logged as warnings, never raised (`agentcore.py:143-147`); unserializable domain symbols raise `ValueError` with guidance at build time (`agentcore.py:11-20`).
- Prompt builders: `extract_imports` returns empty set on `SyntaxError`; `format_function` falls back to `(...)` signatures (`imports.py:6-22`, `document_code.py:5-21`).

## Cross-Cutting Concerns

**Logging:** Standard `logging` only in `agentcore.py` (session start/stop); user-facing output goes through the Rich `CodeAgentCallbackHandler`, not logging.
**Validation:** Import allowlisting (`authorized_imports` + auto-extracted preamble imports) at the interpreter boundary; OKF frontmatter access is permissive (`.get` with defaults, non-list `tags` coerced).
**Authentication:** None in-process. AgentCore relies on ambient AWS credentials via `boto3.client("bedrock-agentcore")`; model credentials are the upstream Strands/harness concern.

---

*Architecture analysis: 2026-09-22*
