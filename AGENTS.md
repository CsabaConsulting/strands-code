<!-- GSD:project-start source:PROJECT.md -->

## Project

**Strands Code**

Strands Code is a conversational coding CLI in the spirit of Claude Code and Codex CLI, built on the Strands harness. The user issues a series of asks; the CLI plans tasks and orchestrates subagents and tool calls to fulfill them. Its home turf is software engineering: speccing features, implementing them, writing and executing tests, and working the full GitHub loop — with the agent able to "talk" to source code and do deep research when needed.

**Core Value:** A single ask — spec it, build it, test it, open the PR — completes end to end without the user leaving the conversation.

### Constraints

- **Tech stack**: Python >=3.10, `uv` toolchain, Strands SDK + harness — pad the CLI, don't fork the platform
- **AWS posture**: AWS-optional, never AWS-required; `agentcore` stays an optional extra with lazy imports
- **Compatibility**: no upper pins during the experimental phase; resync upstream deliberately, not continuously

<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->

## Technology Stack

## Languages

- Python >=3.10 - All library code in `strands_code_agent/`, all tests in `tests/`, example in `examples/`
- None - No TypeScript, JavaScript, or other languages detected in the repo

## Runtime

- Python >=3.10 (classifiers cover 3.10–3.13; observed dev interpreter is Python 3.14.7)
- uv
- Lockfile: present (`uv.lock`, ~755 KB, pins `strands-agents 1.57.0`, `strands-harness 0.1.2`, `smolagents 1.26.0`, `boto3 1.43.100`, `pytest 9.1.1`)

## Frameworks

- strands-agents 1.57.0 - Agent runtime; `CodeAgent` subclasses `strands.Agent` (`strands_code_agent/code_agent.py`), `@tool` decorator defines `python_repl` (`strands_code_agent/python_environments/base.py`)
- strands-harness 0.1.2 - CLI direction only (planned `create_harness()` composition per `README.md`); not imported by library code yet
- smolagents 1.26.0 - Sandboxed execution backend; `SandboxedPythonInterpreter` wraps `smolagents.local_python_executor.LocalPythonExecutor` (`strands_code_agent/python_environments/local_sandboxed.py`)
- Jinja2 3.1.6 - System-prompt templating (`CODE_PREAMBLE_TEMPLATE`, `TEMP_DIR_TEMPLATE`, `DOMAIN_SPECIFIC_DOC_TEMPLATE` in `strands_code_agent/code_agent.py`)
- Rich 15.0.0 - Terminal rendering in `CodeAgentCallbackHandler` (`strands_code_agent/callback_handler.py`: `Syntax`, `JSON`, `Markdown`, `Pretty`, `Console`)
- PyYAML 6.0.3 - OKF bundle frontmatter parse/dump (`strands_code_agent/knowledge/bundle.py`, `strands_code_agent/knowledge/pdf_to_okf_bundle.py`)
- pytest >=8 (locked 9.1.1) - Test runner; `integration` marker deselected by default via `[tool.pytest.ini_options]` in `pyproject.toml`
- numpy / pandas / matplotlib / seaborn / scipy (dev dependency group) - Required at test runtime because toolkit wiring tests execute real plotting/analysis code (noted in `pyproject.toml` comment)
- hatchling - Build backend (`[build-system]` in `pyproject.toml`)
- uv 0.9.26 - Sync/install workflow (`uv sync` per `README.md`)
- GitHub Actions `publish.yml` - `pip install build` + `python -m build` on release

## Key Dependencies

- strands-agents >=0.1.0 (locked 1.57.0) - Without it `CodeAgent` and the `python_repl` tool cannot exist
- smolagents >=1.0.0 (locked 1.26.0) - Powers the default `SandboxedPythonInterpreter` (import allowlisting, timeouts)
- Jinja2 >=3.0 - System-prompt assembly; removing it breaks `CodeAgent.__init__`
- Rich >=13.0 - Callback handler rendering only; safe to make optional for headless use
- PyYAML >=6.0 - OKF bundle read/write; required by `strands_code_agent/knowledge/`
- boto3 >=1.35.0 (locked 1.43.100, optional `agentcore` extra) - Only import is `strands_code_agent/python_environments/agentcore.py`; local-only installs never touch it
- botocore (via boto3) - Monkey-patched in `strands_code_agent/solution_user_agent.py` to append `AWSSOLUTION/SO0353/v0.4.0` to User-Agent; imported at package init (`strands_code_agent/__init__.py`)
- pymupdf (`fitz`) - Lazily imported inside `pdf_to_okf_bundle()` (`strands_code_agent/knowledge/pdf_to_okf_bundle.py`); NOT declared in `pyproject.toml`, so `pip install pymupdf` is required manually before PDF conversion (the example documents this)

## Configuration

- No `.env` files, no `os.environ`/`os.getenv` reads anywhere in `strands_code_agent/` - all tuning is constructor kwargs (`region`, `timeout_seconds`, `tmp_dir`, `toolkits`, `model` via `**kwargs` to `strands.Agent`)
- AWS credentials resolve through the standard boto3 chain (env vars, shared config, IAM role) - implicit, never read directly in code
- `CodeAgent(tmp_dir=True)` creates a per-agent directory via `tempfile.mkdtemp(dir='/tmp')` and advertises it in the system prompt (`strands_code_agent/code_agent.py`)
- `pyproject.toml` - Project metadata, dependencies, optional `agentcore` extra, dev group, pytest config; no `[tool.hatch]` overrides (hatchling defaults)
- `uv.lock` - Pinned dependency tree
- `.github/workflows/publish.yml` - Release-to-PyPI build pipeline (checkout, setup-python 3.11, `python -m build`, `pypa/gh-action-pypi-publish`)
- No `tsconfig.json`, `.nvmrc`, `.python-version`, Dockerfiles, or linter/formatter configs detected

## Platform Requirements

- Python >=3.10 with `uv` (`uv sync` reproduces project-local `.venv`)
- Dev/test extras: `numpy`, `pandas`, `matplotlib`, `seaborn`, `scipy` (test-only runtime needs)
- Optional: `pip install .[agentcore]` + AWS credentials for `AgentCorePythonInterpreter`; `pip install pymupdf` for PDF-to-OKF conversion
- Published as a PyPI library (`strands-code-agent 0.4.0`, `hatchling.build`); consumers embed `CodeAgent` in their own process
- No server, container, or hosting target in this repo; no deployment manifests

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Naming Patterns

- `snake_case.py` for all modules: `code_agent.py`, `callback_handler.py`, `document_code.py`, `local_sandboxed.py`, `local_exec.py`
- Test files mirror the module under test: `test_<module>.py` in `tests/` (e.g. `tests/test_code_agent.py` for `strands_code_agent/code_agent.py`)
- Use `snake_case` for all functions and methods: `get_documentation`, `format_function`, `extract_imports`, `get_import_string`, `execute_code`, `clear_state`, `format_message`
- Private module helpers use a leading underscore: `_parse_frontmatter`, `_extract_links`, `_get_source`, `_make_stream` (test helper in `tests/test_agentcore_python_interpreter.py`), `_make_agent` (test helper in `tests/test_code_agent.py`)
- Private methods on classes use a leading underscore: `PythonInterpreter.get_tool` internals, `OKFBundle._ensure_loaded`, `OKFBundle._search`, `SandboxedPythonInterpreter._init_executor`, `AgentCorePythonInterpreter._ensure_session`, `_run_code`, `_stop_session`, `_build_initialization`
- Use `snake_case` for locals and parameters: `authorized_imports`, `initialization_code`, `domain_specific_code`, `timeout_seconds`, `stdout_label`, `stderr_label`
- Use `UPPER_SNAKE_CASE` for module-level constants: `CODE_AGENT_INSTRUCTIONS` in `strands_code_agent/code_agent.py`, `CODE_PREAMBLE_TEMPLATE`, `TEMP_DIR_TEMPLATE`, `DOMAIN_SPECIFIC_DOC_TEMPLATE`, `DEFAULT_CODE_AGENT_CALLBACK_HANDLER`, `VISUALIZATION_TOOLKIT`, `DATA_ANALYSIS_TOOLKIT` in `strands_code_agent/toolkits.py`, `STDOUT_LABEL`, `STDERR_LABEL` in `strands_code_agent/python_environments/base.py`, `EXTRA_BUILTINS` in `strands_code_agent/python_environments/local_sandboxed.py`, `SOLUTION_UA` in `strands_code_agent/solution_user_agent.py`
- Test-local helper names use leading underscore plus descriptive name: `_sample_func`, `_SampleClass` in `tests/test_code_agent.py`
- Use `PascalCase` for all classes: `CodeAgent` (`strands_code_agent/code_agent.py`), `Toolkit` (`strands_code_agent/toolkits.py`), `PythonInterpreter` (`strands_code_agent/python_environments/base.py`), `SandboxedPythonInterpreter`, `ExecPythonInterpreter`, `AgentCorePythonInterpreter`, `OKFBundle`, `Concept`, `SearchIndex`, `KeywordSearchIndex`, `CodeAgentCallbackHandler`
- Use `PascalCase` for test classes grouping a unit under test: `TestCodeAgentSystemPrompt`, `TestPythonInterpreterExecution`, `TestGetImportString` — one class per behavior area, not per method

## Code Style

- No formatter or linter is configured (no `ruff`, `black`, `flake8`, `mypy`, `pylint`, or `isort` config in `pyproject.toml`; no config files at repo root). Match the surrounding file's existing style by hand.
- Observed style: 4-space indentation, double quotes for strings, single quotes accepted inside strings, ~100-120 char lines, blank line between top-level definitions, section banners in tests (`# ---...---` comment blocks).
- Keep imports at the top of the file, one import per line; `from __future__ import annotations` first where present (`strands_code_agent/knowledge/bundle.py`, `strands_code_agent/knowledge/concept.py`, `strands_code_agent/knowledge/search.py`).
- No linting tool is enforced. `pyproject.toml` contains only `[build-system]`, `[project]`, `[project.optional-dependencies]`, `[dependency-groups]`, `[project.urls]`, and `[tool.pytest.ini_options]`.
- The only lint-adjacent convention is `# noqa: F401` on the intentional re-export side-effect import in `strands_code_agent/__init__.py`.

## Import Organization

- None. Use absolute imports rooted at `strands_code_agent` everywhere (e.g. `from strands_code_agent.toolkits import Toolkit`). Do not use relative imports or `sys.path` manipulation.

## Error Handling

- Return `(stdout, stderr)` tuples from interpreters instead of raising: both `SandboxedPythonInterpreter.execute_code` (`strands_code_agent/python_environments/local_sandboxed.py`) and `ExecPythonInterpreter.execute_code` (`strands_code_agent/python_environments/local_exec.py`) catch `Exception` and put `str(e)` in the stderr slot. The `python_repl` tool in `strands_code_agent/python_environments/base.py` then formats the tuple into `STDOUT:` / `STDERR:` observation text, or `"Code executed successfully."` when both are empty.
- Salvage partial output on failure: `SandboxedPythonInterpreter.execute_code` reads `self.executor.state["_print_outputs"]` for print output captured before the exception.
- Raise `TypeError` for wrong input types where the caller is a programmer, not the agent: `PythonInterpreter()` cannot be instantiated (abstract `ABC` with `@abstractmethod` in `strands_code_agent/python_environments/base.py`); `get_documentation` raises `TypeError(f"Expected a function or class, got {type(obj)}")` (`strands_code_agent/document_code.py`).
- Convert low-level introspection failures into actionable `ValueError` with chaining: `_get_source` in `strands_code_agent/python_environments/agentcore.py` catches `(OSError, TypeError)` from `inspect.getsource` and raises `ValueError(... remote execution ...) from e`.
- Fail soft on missing data in read paths: `OKFBundle.read` / `children` (`strands_code_agent/knowledge/bundle.py`) return formatted "not found" strings with suggestions instead of raising; `_parse_frontmatter` returns `({}, text)` when frontmatter is absent; `KeywordSearchIndex.query` returns `[]` for empty queries.
- Log-and-continue only for best-effort cleanup: `AgentCorePythonInterpreter._stop_session` catches `Exception` and calls `logger.warning(...)` so `clear_state` / `close` / `__del__` never raise.

## Logging

- Use module-level `logger = logging.getLogger(__name__)` and `%s`-style args: `logger.info("Started AgentCore session: %s", self._session_id)` (`strands_code_agent/python_environments/agentcore.py`). This is currently the only library module that logs.
- Use `warnings.catch_warnings()` with `simplefilter("ignore")` around noisy third-party introspection, not logging: `SandboxedPythonInterpreter._init_executor` (`strands_code_agent/python_environments/local_sandboxed.py`).
- Use `rich` (`Syntax`, `JSON`, `Markdown`, `Pretty`, `Console`) only in `strands_code_agent/callback_handler.py` for human-facing REPL transcript rendering. Never use `print()` in library code; `print` appears only inside test snippets and example strings executed by the interpreters.
- Do not add new logging to the `python_repl` observation path — agent-visible output flows through the `(stdout, stderr)` tuple and `STDOUT_LABEL` / `STDERR_LABEL` prefixes.

## Comments

- Explain *why* a non-obvious workaround exists, not what the code does: `# smolagents' LocalPythonExecutor introspects all attributes ... via getattr(), which triggers DeprecationWarnings` (`strands_code_agent/python_environments/local_sandboxed.py`); `# Python builtins that smolagents' executor doesn't allow-list by default` above `EXTRA_BUILTINS`; `# Salvage any print output captured before the error`.
- Mark test intent with Given/When-free one-liners only where the assertion is not self-evident: `# Should still have a working REPL`, `# extra_tool + python_repl`, `# SandboxedPythonInterpreter always includes EXTRA_BUILTINS`.
- Do not add narrative or design-deliberation comments; keep comments to one or two lines.
- Use triple-double-quoted docstrings on every public module-adjacent function, class, and method. First line is an imperative summary; longer units add `Args:` / `Returns:` sections in plain text (not Sphinx or Google style strictly).
- Document the agent-tool contract in the tool docstring itself: `python_repl(code: str) -> str` in `strands_code_agent/python_environments/base.py` documents `code` as "The Python code to execute".
- Keep `Toolkit` field docs in the class docstring (`strands_code_agent/toolkits.py`) and interpreter session semantics in the class docstring (`AgentCorePythonInterpreter`); mirror that pattern for new public classes.

## Function Design

## Module Design

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

## System Overview

```text

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

- `CodeAgent` does not orchestrate tool chains; it gives the model one primary action interface (`python_repl`) and injects domain capability as importable Python symbols.
- Toolkits are declarative capability bundles: allowlist entries, startup preamble, prompt guidance, and documented callables are merged at construction time (`strands_code_agent/code_agent.py:87-137`).
- Execution backends are swappable behind the `PythonInterpreter` ABC via the `python_interpreter_class` constructor argument; the knowledge subsystem is an independent, dependency-light library consumable either directly or inside a toolkit.

## Layers

- Purpose: Owns the public API (`CodeAgent`, `Toolkit`) and builds the agent: system prompt assembly, import authorization, REPL tool registration.
- Location: `strands_code_agent/code_agent.py`, `strands_code_agent/toolkits.py`, `strands_code_agent/__init__.py`
- Contains: Prompt templates (`CODE_AGENT_INSTRUCTIONS`, `CODE_PREAMBLE_TEMPLATE`, `TEMP_DIR_TEMPLATE`, `DOMAIN_SPECIFIC_DOC_TEMPLATE`), toolkit merge logic, `tools=[python_repl]` wiring.
- Depends on: Execution layer (interpreters), prompt-builder helpers, upstream `strands.Agent`.
- Used by: Consumer scripts such as `examples/pdf_to_okf_bundle/agent_with_knowledge.py`; downstream CLI (planned, not yet implemented).
- Purpose: Runs model-generated Python and returns STDOUT/STDERR observations; controls isolation (unrestricted vs allowlisted vs remote).
- Location: `strands_code_agent/python_environments/`
- Contains: `PythonInterpreter` ABC plus three implementations (`local_exec.py`, `local_sandboxed.py`, `agentcore.py`).
- Depends on: `smolagents` (sandboxed), `boto3` (AgentCore, optional extra), `strands.tool` decorator for tool exposure.
- Used by: `CodeAgent` only (constructed in `code_agent.py:131-138`).
- Purpose: File-based knowledge navigation (OKF bundles) usable standalone or injected into the REPL as domain symbols.
- Location: `strands_code_agent/knowledge/`
- Contains: `Concept` dataclass, `OKFBundle` navigator, `SearchIndex` ABC + keyword backend, PDF converter.
- Depends on: `pyyaml` (frontmatter parse); `pymupdf` lazily inside `pdf_to_okf_bundle` only.
- Used by: Consumer code directly, or via `Toolkit(domain_specific_code=[OKFBundle], initialization_code=...)` as shown in `examples/pdf_to_okf_bundle/agent_with_knowledge.py`.
- Purpose: Human-facing terminal output and cost telemetry; no control-flow role.
- Location: `strands_code_agent/callback_handler.py`, `strands_code_agent/utils.py`
- Contains: Rich-based message/code/result rendering; `get_response_metrics` token/cost helper; `image_to_base64`.
- Depends on: `rich`.
- Used by: `CodeAgent` default `callback_handler`; example scripts.

## Data Flow

### Primary Request Path

### Knowledge Navigation Flow

### Remote Execution Flow (AgentCore)

- REPL state persists across tool calls within one interpreter lifetime but `CodeAgent` documents reset between user messages; `clear_state()` re-runs the preamble (local) or drops the remote session (AgentCore).
- `OKFBundle` caches concepts/backlinks/search index after first load per instance (`_ensure_loaded` guard); no cross-instance cache.
- Per-agent `tmp_dir` created under `/tmp` when `tmp_dir=True` and advertised in the system prompt (`strands_code_agent/code_agent.py:118-120`).

## Key Abstractions

- Purpose: Single public entry point that turns declarative toolkits into a capable coding agent.
- Examples: `strands_code_agent/code_agent.py`, `examples/pdf_to_okf_bundle/agent_with_knowledge.py`
- Pattern: Constructor-assembled system prompt + tool injection; extra behavior via `tools=[...]` and Strands `**kwargs` (model, etc.).
- Purpose: The unit of domain capability: allowlist + preamble + prompt guidance + documented symbols.
- Examples: `strands_code_agent/toolkits.py` (`VISUALIZATION_TOOLKIT`, `DATA_ANALYSIS_TOOLKIT`)
- Pattern: Plain data merged by `CodeAgent.__init__`; `domain_specific_code` symbols are auto-imported (`get_import_string`) and auto-documented (`get_documentation`) into the prompt.
- Purpose: Uniform execution seam: `execute_code(code) -> (stdout, stderr)` plus Strands `@tool`-wrapped `python_repl`.
- Examples: `strands_code_agent/python_environments/base.py`, `local_exec.py`, `local_sandboxed.py`, `agentcore.py`
- Pattern: Strategy — `CodeAgent(python_interpreter_class=...)` selects the backend; `python_interpreter_kwargs` forwarded.
- Purpose: Filesystem-backed, read-optimized knowledge graph with a pluggable search backend.
- Examples: `strands_code_agent/knowledge/bundle.py`, `concept.py`, `search.py`
- Pattern: Lazy index build; `SearchIndex` ABC lets consumers substitute embedding search without touching navigation code.

## Entry Points

- Location: `strands_code_agent/__init__.py`
- Triggers: Any consumer `import` (also executes `solution_user_agent` side effect).
- Responsibilities: Public surface; keep `__all__` in sync when adding top-level exports.
- Location: `strands_code_agent/code_agent.py:77-149`
- Triggers: Consumer code (e.g. `agent = CodeAgent(toolkits=[...])` then `agent("...")` via `strands.Agent.__call__`).
- Responsibilities: Toolkit merge, prompt assembly, interpreter construction, tool registration.
- Location: `strands_code_agent/knowledge/__init__.py`, `examples/pdf_to_okf_bundle/agent_with_knowledge.py`
- Triggers: Direct import/use; example run downloads a PDF, converts, and starts a bundle-backed agent.
- Responsibilities: Offline knowledge preparation and runtime navigation.
- There is no `__main__.py`, console-script, or service handler; the README describes the CLI as planned direction layered on `strands-harness`. Do not assume one exists.

## Architectural Constraints

- **Threading:** Single-threaded synchronous model. No threads, asyncio, or workers in this repo; long runs are bounded by per-call `timeout_seconds` (default 180 in `CodeAgent`, 60 in interpreters) and AgentCore `session_timeout_seconds` (default 900).
- **Global state:** `DEFAULT_CODE_AGENT_CALLBACK_HANDLER` module-level singleton shared by all `CodeAgent()` instances that omit `callback_handler` (`strands_code_agent/code_agent.py:36`); `botocore.session.Session.__init__` monkeypatched at import (`strands_code_agent/solution_user_agent.py:18`). `OKFBundle` caches are per-instance only.
- **Circular imports:** None detected. Dependency direction is one-way: `code_agent.py` → interpreters/helpers; `knowledge/bundle.py` → `concept.py` + `search.py`; `python_environments/*` → `base.py`. `TYPE_CHECKING`-only import of `Concept` in `search.py` avoids a runtime cycle.
- **AWS-optional:** `boto3` is an optional `agentcore` extra; `AgentCorePythonInterpreter` is importable from the top level but only usable with credentials. Defaults stay local.

## Anti-Patterns

### Mutating caller-owned `tools` list in place

### Swallowing tracebacks into plain stderr strings

## Error Handling

- Local: `exec()` errors → `str(e)` in stderr (`local_exec.py`); sandbox errors → stderr plus salvaged `_print_outputs` stdout (`local_sandboxed.py:39-49`).
- Remote: session-stop failures only logged as warnings, never raised (`agentcore.py:143-147`); unserializable domain symbols raise `ValueError` with guidance at build time (`agentcore.py:11-20`).
- Prompt builders: `extract_imports` returns empty set on `SyntaxError`; `format_function` falls back to `(...)` signatures (`imports.py:6-22`, `document_code.py:5-21`).

## Cross-Cutting Concerns

<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `$gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `$gsd-debug` for investigation and bug fixing
- `$gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `$gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
