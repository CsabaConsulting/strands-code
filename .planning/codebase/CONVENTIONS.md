---
last_mapped_commit: 4a23ae24e72098045e1d04b5328d95967221c4a0
last_mapped_at: 2026-09-22
---
# Coding Conventions

**Analysis Date:** 2026-09-22

## Naming Patterns

**Files:**

- `snake_case.py` for all modules: `code_agent.py`, `callback_handler.py`, `document_code.py`, `local_sandboxed.py`, `local_exec.py`
- Test files mirror the module under test: `test_<module>.py` in `tests/` (e.g. `tests/test_code_agent.py` for `strands_code_agent/code_agent.py`)

**Functions:**

- Use `snake_case` for all functions and methods: `get_documentation`, `format_function`, `extract_imports`, `get_import_string`, `execute_code`, `clear_state`, `format_message`
- Private module helpers use a leading underscore: `_parse_frontmatter`, `_extract_links`, `_get_source`, `_make_stream` (test helper in `tests/test_agentcore_python_interpreter.py`), `_make_agent` (test helper in `tests/test_code_agent.py`)
- Private methods on classes use a leading underscore: `PythonInterpreter.get_tool` internals, `OKFBundle._ensure_loaded`, `OKFBundle._search`, `SandboxedPythonInterpreter._init_executor`, `AgentCorePythonInterpreter._ensure_session`, `_run_code`, `_stop_session`, `_build_initialization`

**Variables:**

- Use `snake_case` for locals and parameters: `authorized_imports`, `initialization_code`, `domain_specific_code`, `timeout_seconds`, `stdout_label`, `stderr_label`
- Use `UPPER_SNAKE_CASE` for module-level constants: `CODE_AGENT_INSTRUCTIONS` in `strands_code_agent/code_agent.py`, `CODE_PREAMBLE_TEMPLATE`, `TEMP_DIR_TEMPLATE`, `DOMAIN_SPECIFIC_DOC_TEMPLATE`, `DEFAULT_CODE_AGENT_CALLBACK_HANDLER`, `VISUALIZATION_TOOLKIT`, `DATA_ANALYSIS_TOOLKIT` in `strands_code_agent/toolkits.py`, `STDOUT_LABEL`, `STDERR_LABEL` in `strands_code_agent/python_environments/base.py`, `EXTRA_BUILTINS` in `strands_code_agent/python_environments/local_sandboxed.py`, `SOLUTION_UA` in `strands_code_agent/solution_user_agent.py`
- Test-local helper names use leading underscore plus descriptive name: `_sample_func`, `_SampleClass` in `tests/test_code_agent.py`

**Types:**

- Use `PascalCase` for all classes: `CodeAgent` (`strands_code_agent/code_agent.py`), `Toolkit` (`strands_code_agent/toolkits.py`), `PythonInterpreter` (`strands_code_agent/python_environments/base.py`), `SandboxedPythonInterpreter`, `ExecPythonInterpreter`, `AgentCorePythonInterpreter`, `OKFBundle`, `Concept`, `SearchIndex`, `KeywordSearchIndex`, `CodeAgentCallbackHandler`
- Use `PascalCase` for test classes grouping a unit under test: `TestCodeAgentSystemPrompt`, `TestPythonInterpreterExecution`, `TestGetImportString` — one class per behavior area, not per method

## Code Style

**Formatting:**

- No formatter or linter is configured (no `ruff`, `black`, `flake8`, `mypy`, `pylint`, or `isort` config in `pyproject.toml`; no config files at repo root). Match the surrounding file's existing style by hand.
- Observed style: 4-space indentation, double quotes for strings, single quotes accepted inside strings, ~100-120 char lines, blank line between top-level definitions, section banners in tests (`# ---...---` comment blocks).
- Keep imports at the top of the file, one import per line; `from __future__ import annotations` first where present (`strands_code_agent/knowledge/bundle.py`, `strands_code_agent/knowledge/concept.py`, `strands_code_agent/knowledge/search.py`).

**Linting:**

- No linting tool is enforced. `pyproject.toml` contains only `[build-system]`, `[project]`, `[project.optional-dependencies]`, `[dependency-groups]`, `[project.urls]`, and `[tool.pytest.ini_options]`.
- The only lint-adjacent convention is `# noqa: F401` on the intentional re-export side-effect import in `strands_code_agent/__init__.py`.

## Import Organization

**Order:**

1. Standard library (`tempfile`, `ast`, `inspect`, `io`, `re`, `logging`, `dataclasses`, `pathlib`, `collections`, `typing`, `contextlib`, `warnings`)
2. Third-party (`strands`, `jinja2`, `rich`, `smolagents`, `boto3`, `botocore`, `yaml`, `pytest`, `unittest.mock`)
3. First-party (`strands_code_agent.document_code`, `strands_code_agent.python_environments.*`, `strands_code_agent.toolkits`, `strands_code_agent.callback_handler`)

Example from `strands_code_agent/code_agent.py`:

```python
import tempfile

from strands import Agent
from jinja2 import Template

from strands_code_agent.document_code import get_documentation
from strands_code_agent.python_environments.local_sandboxed import SandboxedPythonInterpreter
from strands_code_agent.imports import get_import_string, extract_imports
from strands_code_agent.callback_handler import CodeAgentCallbackHandler
```

**Path Aliases:**

- None. Use absolute imports rooted at `strands_code_agent` everywhere (e.g. `from strands_code_agent.toolkits import Toolkit`). Do not use relative imports or `sys.path` manipulation.

## Error Handling

**Patterns:**

- Return `(stdout, stderr)` tuples from interpreters instead of raising: both `SandboxedPythonInterpreter.execute_code` (`strands_code_agent/python_environments/local_sandboxed.py`) and `ExecPythonInterpreter.execute_code` (`strands_code_agent/python_environments/local_exec.py`) catch `Exception` and put `str(e)` in the stderr slot. The `python_repl` tool in `strands_code_agent/python_environments/base.py` then formats the tuple into `STDOUT:` / `STDERR:` observation text, or `"Code executed successfully."` when both are empty.
- Salvage partial output on failure: `SandboxedPythonInterpreter.execute_code` reads `self.executor.state["_print_outputs"]` for print output captured before the exception.
- Raise `TypeError` for wrong input types where the caller is a programmer, not the agent: `PythonInterpreter()` cannot be instantiated (abstract `ABC` with `@abstractmethod` in `strands_code_agent/python_environments/base.py`); `get_documentation` raises `TypeError(f"Expected a function or class, got {type(obj)}")` (`strands_code_agent/document_code.py`).
- Convert low-level introspection failures into actionable `ValueError` with chaining: `_get_source` in `strands_code_agent/python_environments/agentcore.py` catches `(OSError, TypeError)` from `inspect.getsource` and raises `ValueError(... remote execution ...) from e`.
- Fail soft on missing data in read paths: `OKFBundle.read` / `children` (`strands_code_agent/knowledge/bundle.py`) return formatted "not found" strings with suggestions instead of raising; `_parse_frontmatter` returns `({}, text)` when frontmatter is absent; `KeywordSearchIndex.query` returns `[]` for empty queries.
- Log-and-continue only for best-effort cleanup: `AgentCorePythonInterpreter._stop_session` catches `Exception` and calls `logger.warning(...)` so `clear_state` / `close` / `__del__` never raise.

## Logging

**Framework:** `logging` (stdlib) in library/server code; `rich.console.Console` only in the interactive display layer.

**Patterns:**

- Use module-level `logger = logging.getLogger(__name__)` and `%s`-style args: `logger.info("Started AgentCore session: %s", self._session_id)` (`strands_code_agent/python_environments/agentcore.py`). This is currently the only library module that logs.
- Use `warnings.catch_warnings()` with `simplefilter("ignore")` around noisy third-party introspection, not logging: `SandboxedPythonInterpreter._init_executor` (`strands_code_agent/python_environments/local_sandboxed.py`).
- Use `rich` (`Syntax`, `JSON`, `Markdown`, `Pretty`, `Console`) only in `strands_code_agent/callback_handler.py` for human-facing REPL transcript rendering. Never use `print()` in library code; `print` appears only inside test snippets and example strings executed by the interpreters.
- Do not add new logging to the `python_repl` observation path — agent-visible output flows through the `(stdout, stderr)` tuple and `STDOUT_LABEL` / `STDERR_LABEL` prefixes.

## Comments

**When to Comment:**

- Explain *why* a non-obvious workaround exists, not what the code does: `# smolagents' LocalPythonExecutor introspects all attributes ... via getattr(), which triggers DeprecationWarnings` (`strands_code_agent/python_environments/local_sandboxed.py`); `# Python builtins that smolagents' executor doesn't allow-list by default` above `EXTRA_BUILTINS`; `# Salvage any print output captured before the error`.
- Mark test intent with Given/When-free one-liners only where the assertion is not self-evident: `# Should still have a working REPL`, `# extra_tool + python_repl`, `# SandboxedPythonInterpreter always includes EXTRA_BUILTINS`.
- Do not add narrative or design-deliberation comments; keep comments to one or two lines.

**Docstrings:**

- Use triple-double-quoted docstrings on every public module-adjacent function, class, and method. First line is an imperative summary; longer units add `Args:` / `Returns:` sections in plain text (not Sphinx or Google style strictly).
- Document the agent-tool contract in the tool docstring itself: `python_repl(code: str) -> str` in `strands_code_agent/python_environments/base.py` documents `code` as "The Python code to execute".
- Keep `Toolkit` field docs in the class docstring (`strands_code_agent/toolkits.py`) and interpreter session semantics in the class docstring (`AgentCorePythonInterpreter`); mirror that pattern for new public classes.

## Function Design

**Size:** Keep functions small and single-purpose (most are under ~30 lines). The largest units are `CodeAgent.__init__` (~60 lines, prompt assembly + REPL wiring in `strands_code_agent/code_agent.py`) and `OKFBundle._ensure_loaded` (~35 lines). Split when a function mixes prompt/config assembly with execution.

**Parameters:** Use keyword-friendly signatures with `None` defaults for optional wiring (`system_prompt: str | None = None`, `tools: list | None = None`, `toolkits: list | None = None`), then normalize `None` to a working default inside the body (`tools = [python_repl_tool]`, `**(python_interpreter_kwargs or {})`). Pass timeouts and labels explicitly through each interpreter constructor (`timeout_seconds=60` default in `PythonInterpreter`, `180` default in `CodeAgent`).

**Return Values:** Return tuples for dual-channel results (`execute_code` returns `tuple[str, str]`), formatted strings for agent-facing reads (`OKFBundle.read` / `find` / `children` / `toc` return `str`), and `str` observations from the `@tool`-decorated `python_repl`. Return empty string / empty list for "nothing to report" (`get_import_string([]) == ""`, `extract_imports` returns `set()` on `SyntaxError`).

## Module Design

**Exports:** Define one primary class or small function group per module and re-export the public surface from `strands_code_agent/__init__.py` with an explicit `__all__ = ["CodeAgent", "Toolkit", "AgentCorePythonInterpreter"]`. Keep subpackage `__init__.py` files minimal (`strands_code_agent/python_environments/__init__.py` is empty; `strands_code_agent/knowledge/__init__.py` re-exports `OKFBundle`, `Concept`, search backends).

**Barrel Files:** `strands_code_agent/__init__.py` is the only barrel file. Import public names from it in examples and tests where possible (`from strands_code_agent import CodeAgent, Toolkit`). Do not create new barrel files; import new modules via their canonical path (`strands_code_agent.<subpackage>.<module>`).

---

*Convention analysis: 2026-09-22*
