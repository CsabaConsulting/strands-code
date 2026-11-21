# Phase 1: Session Wiring + REPL Skeleton - Pattern Map

**Mapped:** 2026-09-24
**Files analyzed:** 13 (7 new modules + 1 package init + 1 pyproject edit + 5 tests; 4 test files per RESEARCH structure — `test_cli_exit.py` folded into `test_kill_resume.py` per test map)
**Analogs found:** 11 / 13

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `strands_code_cli/__init__.py` | config (package surface) | request-response (import) | `strands_code_agent/__init__.py` | exact |
| `strands_code_cli/main.py` | controller (entry) | request-response (argv → REPL) | `examples/pdf_to_okf_bundle/agent_with_knowledge.py` (`main()` + `ensure_bundle()`) | role-match |
| `strands_code_cli/loop.py` | controller (REPL loop) | streaming + event-driven | `strands_code_agent/callback_handler.py` (`CodeAgentCallbackHandler.__call__`) | data-flow-match |
| `strands_code_cli/router.py` | middleware (slash dispatch) | request-response | `strands_code_agent/callback_handler.py` (content-kind dispatch `text`/`toolUse`/`toolResult`) | role-match |
| `strands_code_cli/session_index.py` | model + service (sidecar index) | file-I/O + CRUD | `strands_code_agent/knowledge/bundle.py` (`OKFBundle` + `_parse_frontmatter`) | role-match |
| `strands_code_cli/provider_config.py` | config + service | file-I/O (YAML load/save) | `strands_code_agent/knowledge/bundle.py` (`yaml.safe_load` frontmatter) + `strands_code_agent/toolkits.py` (`Toolkit` dataclass) | role-match |
| `strands_code_cli/first_run.py` | service (credential preflight) | request-response (probe → stop) | `strands_code_agent/python_environments/agentcore.py` (lazy boto3, ambient chain) | role-match |
| `pyproject.toml` (console script) | config | build-time | `pyproject.toml` (`[project]` metadata, no script yet) | partial |
| `tests/test_cli_entry.py` | test | request-response | `tests/test_code_agent.py` (`_make_agent` + `TestCodeAgentSystemPrompt`) | role-match |
| `tests/test_session_index.py` | test | file-I/O (CRUD round-trip) | `tests/test_code_agent.py` (toolkit wiring asserts) | role-match |
| `tests/test_session_resume.py` | test | streaming (construct → turn → re-construct) | `tests/test_code_agent.py` (`test_initialization_code_runs`) | role-match |
| `tests/test_kill_resume.py` | test | batch (kill simulation) | `strands_code_agent/python_environments/local_sandboxed.py` (`execute_code` salvage pattern) | data-flow-match |
| `tests/test_first_run.py` | test | request-response (exit code) | `strands_code_agent/document_code.py` (`TypeError`/`ValueError` contract tests) | partial |

All analog paths verified git-tracked (`git ls-files` lists each). No analog is a gitignored mirror; installed SDK/harness sources under `.venv/` are cited as VERIFIED references only, never as copy-from analogs.

## Pattern Assignments

### `strands_code_cli/__init__.py` (config, import surface)

**Analog:** `strands_code_agent/__init__.py`

**Imports pattern** (lines 1-7):

```python
from . import solution_user_agent  # noqa: F401 - registers the AWS Solutions user-agent ID

from strands_code_agent.code_agent import CodeAgent
from strands_code_agent.toolkits import Toolkit
from strands_code_agent.python_environments.agentcore import AgentCorePythonInterpreter

__all__ = ["CodeAgent", "Toolkit", "AgentCorePythonInterpreter"]
```

**Copy:** single public export (`main`), absolute imports rooted at package, `__all__` kept in sync. Per RESEARCH: export `main()` only.

```python
from strands_code_cli.main import main

__all__ = ["main"]
```

---

### `strands_code_cli/main.py` (controller, argv → REPL)

**Analog:** `examples/pdf_to_okf_bundle/agent_with_knowledge.py` (lines 24-41, 74-79)

**Entry + preflight-then-run pattern** (lines 24-40):

```python
def ensure_bundle():
    """Download PDF and build bundle if it doesn't exist yet."""
    if BUNDLE_PATH.exists():
        return
    if not PDF_PATH.exists():
        print("Downloading AgentCore Developer Guide PDF...")
        import urllib.request
        urllib.request.urlretrieve(PDF_URL, PDF_PATH)
    print(f"Converting PDF to OKF bundle...")
    result = pdf_to_okf_bundle(PDF_PATH, BUNDLE_PATH)
    print(f"✓ {result['concepts']} concepts from {result['pages']} pages\n")
```

**Agent construction pattern** (lines 40-61):

```python
    agent = CodeAgent(
        system_prompt=(
            "You are a technical assistant with access to the Amazon Bedrock AgentCore "
            ...
        ),
        toolkits=[
            Toolkit(
                initialization_code=(
                    f'from strands_code_agent.knowledge import OKFBundle\n'
                    f'agentcore_docs = OKFBundle("{BUNDLE_PATH}")'
                ),
                domain_specific_code=[OKFBundle],
            )
        ],
    )
```

**Copy:** `main()` does preflight (`first_run.py` gate) → resolve session id (picker / `--session-id` / fresh UUID) → build agent via `create_harness()` (NOT bare `CodeAgent(...)` — RESEARCH Pattern 1) → hand off to `loop.py`. Typer option `--session-id` replaces the hardcoded `questions` list (lines 63-79: `for q in questions: response = agent(q)`).

**Error handling:** D-05 stop-with-pointer = preflight failure exits non-zero *before* any session/config creation (RESEARCH Pitfall 5). No analog for Typer `app`/`CliRunner` exists in-repo — use RESEARCH Stack pattern (`typer>=0.9`, no upper pin, `uv add`).

---

### `strands_code_cli/loop.py` (controller, streaming + event-driven)

**Analog:** `strands_code_agent/callback_handler.py` (lines 32-55)

**Side-effect-only render loop** (lines 32-55):

```python
class CodeAgentCallbackHandler:
    def __init__(self, code_tools=None, output_prefix="STDOUT:", format_text=True, **kwargs) -> None:
        self.console = Console()
        if code_tools is None:
            code_tools = {
                'python_repl': 'python'
            }
        ...
    def __call__(self, **kwargs: Any) -> None:
        if 'message' not in kwargs:
            return

        message = kwargs['message']
        role = message['role']
        for content_item in  message['content']:
            if 'text' in content_item:
                self.console.print(f"\n[{role.title()}]", end=" ")
                self.console.print(self.format_text(content_item['text'].strip()), end="\n\n")
```

**Imports pattern** (lines 1-8):

```python
from typing import Any
import ast

from rich.syntax import Syntax
from rich.json import JSON
from rich.markdown import Markdown
from rich.pretty import Pretty
from rich.console import Console
```

**Copy:** loop owns the single `Console` (via existing handler, not a second renderer), runs the agent turn synchronously with the prompt suspended (`patch_stdout` per RESEARCH Pitfall 6), handles Ctrl-C (line-cancel) / Ctrl-D (clean exit + explicit save). Reuse `DEFAULT_CODE_AGENT_CALLBACK_HANDLER` as the render path — AGENTS.md: `rich` only in callback-handler/REPL-render path, never `print()` in library code.

---

### `strands_code_cli/router.py` (middleware, request-response)

**Analog:** `strands_code_agent/callback_handler.py` (lines 52-80) — kind-based dispatch

**Dispatch pattern** (lines 52-80):

```python
        for content_item in  message['content']:
            if 'text' in content_item:
                ...
            if 'toolUse' in content_item:
                tool_use = content_item['toolUse']
                name = tool_use['name']
                self.console.print(f"\n[Tool] {name}")
                if name in self.code_tools:
                    language = self.code_tools[name]
                    syntax = Syntax(tool_use['input']['code'], language)
                    self.console.print(syntax)
                else:
                    for var, value in tool_use['input'].items():
                        self.console.print(f"\t- {var}: {value}")

            if 'toolResult' in content_item:
                ...
```

**Copy:** same shape — leading-`"/"` check, then `if cmd == "/resume" / "/rename" / "/exit"` branches, else fall through to agent turn. Unknown slash input → usage hint (mirrors the `else` generic key/value branch above). Keep the stub minimal: `/resume /rename /exit` only; `/model` is Phase 5 scope (D-06).

---

### `strands_code_cli/session_index.py` (model + service, file-I/O + CRUD)

**Analog:** `strands_code_agent/knowledge/bundle.py` (lines 19-28, 55-78)

**Defensive file-read pattern** (lines 19-28):

```python
def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter + markdown body from text."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n")
    return fm, body
```

**Lazy model pattern** (lines 55-78):

```python
class OKFBundle:
    def __init__(self, root: str | Path, search_index: SearchIndex | None = None) -> None:
        self.root = Path(root).resolve()
        self._concepts: dict[str, Concept] | None = None
        ...
    def _ensure_loaded(self) -> None:
        if self._concepts is not None:
            return
        self._concepts = {}
```

**Path pattern** (lines 66-67): `self.root = Path(root).resolve()` — accept `str | Path`, resolve once.

**Copy:** sidecar JSON index `{session_id: {title, created_at, updated_at}}` with `pathlib.Path` root, lazy load guard, fail-soft reads (missing/corrupt index → empty, never raise — mirrors fail-soft `read`/`children` per CONVENTIONS). API: `mint()` (`str(uuid.uuid4())`), `list_recent()` (order by `updated_at`), `rename()`, `update_title()`. Never write into snapshot blobs (RESEARCH anti-pattern).

**Naming:** `PascalCase` model class + `snake_case` functions per CONVENTIONS.

---

### `strands_code_cli/provider_config.py` (config + service, file-I/O)

**Analog A (YAML):** `strands_code_agent/knowledge/bundle.py` line 26 — `fm = yaml.safe_load(parts[1]) or {}`. PyYAML already owned (no new dep).

**Analog B (declarative config shape):** `strands_code_agent/toolkits.py` (lines 4-18)

```python
@dataclass
class Toolkit:
    """A toolkit that bundles libraries, initialization code, usage instructions, and domain-specific
    symbols for use by a CodeAgent's Python REPL environment.
    ...
    """
    libraries: list[str] | None = None
    initialization_code: str | None = None
    usage_instructions: str | None = None
    domain_specific_code: list | None = None
```

**Analog C (constructor-kwarg feeding):** `strands_code_agent/code_agent.py` (lines 77-86, 144-149) — config flows through constructor kwargs, `**kwargs` forwarded to `super().__init__`; no `os.environ` reads anywhere in library code (AGENTS.md constraint).

**Copy:** `@dataclass ProviderConfig` (`model: str | None`), `load()`/`save()` with `yaml.safe_load`/`yaml.safe_dump`, schema-validate keys and reject unknowns (ASVS V14 per RESEARCH), config home via `platformdirs.user_config_dir` (no `~/.strands-code` hardcode). The loaded `model` string feeds `create_harness(model=...)` as a constructor kwarg.

---

### `strands_code_cli/first_run.py` (service, request-response)

**Analog:** `strands_code_agent/python_environments/agentcore.py` — lazy boto3, ambient credential chain, log-and-continue cleanup (per ARCHITECTURE: `AgentCorePythonInterpreter` lazy boto3 session; `_stop_session` catches `Exception` → `logger.warning`).

**Supporting analog (logging):** module-level `logger = logging.getLogger(__name__)` with `%s`-style args is the only sanctioned logging pattern (CONVENTIONS; currently only in `agentcore.py`).

**Supporting analog (observation contract):** `strands_code_agent/python_environments/base.py` (lines 6-7, 33-42) — `(stdout, stderr)` tuple formatted with `STDOUT:`/`STDERR:` labels; success-with-empty → `"Code executed successfully."`.

**Copy:** cheap ambient-chain probe (STS `get_caller_identity`, RESEARCH A3) *before* `create_harness()`; on failure print Bedrock setup pointer and exit non-zero with zero side effects (no session dir, no config). Never read credentials directly — ambient boto3 chain only (AGENTS.md).

---

### `pyproject.toml` console-script edit (config, build-time)

**Analog:** `pyproject.toml` lines 1-34 — hatchling backend, `[project]` metadata, floor-only pins (`strands-agents>=0.1.0`, no upper pins per AGENTS.md).

**Copy:** add `[project.scripts] strands-code = "strands_code_cli.main:main"` (or `typer.run` equivalent) plus floor-only deps `typer>=0.9`, `prompt-toolkit>=3.0`, `platformdirs>=4.0` via `uv add` (RESEARCH installation section). No existing console-script analog — this is new surface.

---

### Tests (all five files)

**Analog:** `tests/test_code_agent.py` (lines 1-31)

**Test harness pattern** (lines 22-31):

```python
def _make_agent(*, system_prompt=None, tools=None, toolkits=None, tmp_dir=True, **kwargs):
    """Create a CodeAgent with the Strands Agent.__init__ mocked out."""
    with patch("strands_code_agent.code_agent.Agent.__init__", return_value=None):
        return CodeAgent(
            system_prompt=system_prompt,
            tools=tools,
            toolkits=toolkits,
            tmp_dir=tmp_dir,
            **kwargs,
        )
```

**Grouping pattern:** `class TestCodeAgentSystemPrompt:` / `class TestCodeAgentToolkitWiring:` — one class per behavior area; section banners (`# ---...---`); Given/When-free one-liners only where non-obvious.

**Per-file copy:**
- `test_cli_entry.py` — Typer `CliRunner` no-arg/`--session-id` routing (no in-repo CliRunner analog; mirror the `_make_agent` patch-out-the-base-class shape by invoking the Typer app with runner, asserting routing, not live turns).
- `test_session_index.py` — `tmp_path` fixture, mint/list/rename round-trips; mirror `test_authorized_imports_from_toolkit` assert shape (lines 86-90).
- `test_session_resume.py` — construct → turn → re-construct same id; mirror `test_initialization_code_runs` (lines 92-99: build, `execute_code`, assert output).
- `test_kill_resume.py` — restore without exit flush; salvage-not-raise ethos from `local_sandboxed.py` lines 39-49 (execute catches `Exception`, salvages `_print_outputs` stdout, puts `str(e)` in stderr — assert continuity, never in-flight replay per RESEARCH Pitfall 2).
- `test_first_run.py` — no-creds → non-zero exit + pointer + no session dir; fail-fast contract style of `document_code.py` (`TypeError` for programmer errors).

**Naming:** `tests/test_<module>.py` mirrors module under test (CONVENTIONS).

---

## Shared Patterns

### Absolute imports
**Source:** every library module, e.g. `strands_code_agent/code_agent.py` lines 6-9
**Apply to:** all new `strands_code_cli/` modules

```python
from strands_code_agent.document_code import get_documentation
from strands_code_agent.python_environments.local_sandboxed import SandboxedPythonInterpreter
from strands_code_agent.imports import get_import_string, extract_imports
from strands_code_agent.callback_handler import CodeAgentCallbackHandler
```

No relative imports, no `sys.path` manipulation. New package uses `from strands_code_cli...`.

### Constructor-kwarg configuration
**Source:** `strands_code_agent/code_agent.py` lines 77-86
**Apply to:** `provider_config.py`, agent construction in `main.py`

No `os.environ`/`os.getenv` reads in library code; CLI config file feeds constructors; AWS credentials stay on the ambient boto3 chain.

### Error handling: tuples locally, `ValueError` with chaining at boundaries
**Source:** `strands_code_agent/python_environments/local_sandboxed.py` lines 39-49; `strands_code_agent/python_environments/agentcore.py` (`ValueError(... ) from e`)
**Apply to:** `session_index.py` (fail-soft reads), `provider_config.py` (schema `ValueError`), `first_run.py` (clean stop, no raise)

```python
    def execute_code(self, code):
        stdout, stderr = "", ""
        try:
            result = self.executor(code)
            stdout = result.logs.strip() if result.logs else ""
        except Exception as e:
            # Salvage any print output captured before the error
            if hasattr(self.executor, "state") and "_print_outputs" in self.executor.state:
                stdout = str(self.executor.state["_print_outputs"]).strip()
            stderr = str(e)
        return stdout, stderr
```

### Rich only in render path
**Source:** `strands_code_agent/callback_handler.py` lines 1-9 + AGENTS.md
**Apply to:** `loop.py`, `main.py` picker output

`rich` (`Syntax`, `JSON`, `Markdown`, `Pretty`, `Console`) only in callback-handler/REPL-render path. Never `print()` in library code (allowed in `main.py` entry for the D-05 pointer and in tests/example strings).

### Docstrings + two-line-max comments
**Source:** `strands_code_agent/toolkits.py` lines 5-18; `strands_code_agent/python_environments/base.py` lines 24-42
**Apply to:** all new modules

Triple-double-quoted docstrings on every public class/function with `Args:`/`Returns:` in plain text; comments explain *why*, max two lines, no design deliberation.

### Test conventions
**Source:** `tests/test_code_agent.py` lines 1-31
**Apply to:** all five new test files

`tests/test_<module>.py` mirror naming; `Test<Area>` classes; `_`-prefixed helpers; mock the expensive base (`Agent.__init__` / model calls), execute the real unit.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| (none — full coverage) | — | — | Every Phase 1 file has at least a role-match analog above. Partial-only spots: Typer `app`/`CliRunner` idiom and prompt_toolkit `PromptSession`/`patch_stdout` usage have no in-repo precedent — planner should use RESEARCH.md Standard Stack + Pitfall 6 for those two idioms. |

## Metadata

**Analog search scope:** `strands_code_agent/` (all modules), `tests/`, `examples/pdf_to_okf_bundle/`, `pyproject.toml`, `AGENTS.md` conventions
**Files scanned:** 12 source + 9 tests + 1 example + pyproject
**Pattern extraction date:** 2026-09-24
