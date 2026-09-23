---
last_mapped_commit: 4a23ae24e72098045e1d04b5328d95967221c4a0
last_mapped_at: 2026-09-22
---
# Testing Patterns

**Analysis Date:** 2026-09-22

## Test Framework

**Runner:**

- `pytest>=8` (dev dependency group in `pyproject.toml`)
- Config: `pyproject.toml` (`[tool.pytest.ini_options]` — registers the `integration` marker and sets `addopts = "-m 'not integration'"` so live-AWS tests are deselected by default)

**Assertion Library:**

- Plain `assert` statements (no `unittest.TestCase`, no third-party assertion library)

**Run Commands:**

```bash
uv run pytest              # Run all tests (integration deselected by default)
uv run pytest tests/test_code_agent.py   # Run one file
uv run pytest -m integration   # Run live AWS tests only (requires credentials)
uv run pytest --cov=strands_code_agent   # Coverage (requires pytest-cov, not currently installed)
```

## Test File Organization

**Location:**

- Separate top-level `tests/` directory, mirroring package structure. No co-located tests inside `strands_code_agent/`.

**Naming:**

- `tests/test_<module>.py` per source module: `tests/test_code_agent.py`, `tests/test_toolkits.py`, `tests/test_utils.py`, `tests/test_document_code.py`, `tests/test_sandboxed_python_interpreter.py`, `tests/test_exec_python_interpreter.py`, `tests/test_agentcore_python_interpreter.py`, `tests/test_okf_bundle.py`, `tests/test_readme_examples.py`
- `tests/__init__.py` exists (1 line); test helpers are module-private functions, not shared `conftest.py` (no `conftest.py` exists)

**Structure:**

```
tests/
├── __init__.py
├── test_agentcore_python_interpreter.py   # Remote interpreter (fully mocked boto3)
├── test_code_agent.py                     # Agent wiring (Agent base mocked)
├── test_document_code.py                  # Docstring extraction
├── test_exec_python_interpreter.py         # Unrestricted exec() interpreter
├── test_okf_bundle.py                     # Knowledge-bundle navigation (tmp_path fixture)
├── test_readme_examples.py                # README examples as regression tests
├── test_sandboxed_python_interpreter.py   # Sandboxed interpreter + get_import_string
├── test_toolkits.py                       # Toolkit dataclass + built-ins
└── test_utils.py                          # image_to_base64
```

## Test Structure

**Suite Organization:**

```python

# tests/test_code_agent.py — one class per behavior area, plain test methods

def _make_agent(*, system_prompt=None, tools=None, toolkits=None, tmp_dir=True, **kwargs):
    """Create a CodeAgent with the Strands Agent.__init__ mocked out."""
    with patch("strands_code_agent.code_agent.Agent.__init__", return_value=None):
        return CodeAgent(...)

class TestCodeAgentSystemPrompt:
    def test_includes_base_instructions(self):
        with patch("strands_code_agent.code_agent.Agent.__init__", return_value=None) as mock_init:
            CodeAgent(system_prompt="Be helpful.", tmp_dir=False)
            call_kwargs = mock_init.call_args[1]
            prompt = call_kwargs["system_prompt"]
            assert "Be helpful." in prompt
            assert "code agent" in prompt.lower()
```

**Patterns:**

- Group tests in classes named `Test<Unit><Aspect>` (`TestCodeAgentSystemPrompt`, `TestPythonInterpreterExecution`, `TestToolkitInit`); each class covers one behavior area with focused `test_<behavior>` methods.
- Put reusable construction in module-private helpers (`_make_agent` in `tests/test_code_agent.py`, `_make_stream` in `tests/test_agentcore_python_interpreter.py`) or small local sample types (`_sample_func`, `_SampleClass`, `simple_func`, `SampleClass`, `DataProcessor`, `calculate_roi`).
- Assert on behavior, not internals: check prompt contents (`assert "Be helpful." in prompt`), REPL output (`assert "10" in stdout`), and stderr emptiness (`assert stderr == ""`) rather than call counts — except for session-lifecycle tests that assert `mock_client.start_code_interpreter_session.assert_called_once()`.
- Use `tmp_dir=False` in `CodeAgent` tests unless the test is about temp dirs, to avoid creating `/tmp` directories on every test (`tests/test_code_agent.py`).

## Mocking

**Framework:** `unittest.mock` stdlib (`patch`, `MagicMock`) — no `pytest-mock`, `responses`, or `moto`.

**Patterns:**

```python

# tests/test_code_agent.py — mock the model-dependent base class, exercise real REPL

with patch("strands_code_agent.code_agent.Agent.__init__", return_value=None) as mock_init:
    CodeAgent(system_prompt="Be helpful.", tmp_dir=False)
    prompt = mock_init.call_args[1]["system_prompt"]
    assert "Be helpful." in prompt
```

```python

# tests/test_agentcore_python_interpreter.py — mock boto3, inject fake client

@pytest.fixture
def mock_client():
    client = MagicMock()
    client.start_code_interpreter_session.return_value = {"sessionId": "sess-123"}
    client.invoke_code_interpreter.return_value = _make_stream(stdout="42\n")
    return client

@pytest.fixture
def interpreter(mock_client):
    with patch("boto3.client", return_value=mock_client):
        yield AgentCorePythonInterpreter()
```

**What to Mock:**

- Mock the Strands `Agent.__init__` in every `CodeAgent` test — never instantiate a real agent with a live model (`tests/test_code_agent.py`, `tests/test_readme_examples.py`).
- Mock `boto3.client` in every `AgentCorePythonInterpreter` test and feed canned `start_code_interpreter_session` / `invoke_code_interpreter` responses (`tests/test_agentcore_python_interpreter.py`).
- Set throwaway `__module__` / `__qualname__` attributes on local dummy functions to test import-string generation without creating real modules (`tests/test_sandboxed_python_interpreter.py::TestGetImportString`).

**What NOT to Mock:**

- Do not mock the local interpreters (`SandboxedPythonInterpreter`, `ExecPythonInterpreter`) — execute real code snippets and assert on real stdout/stderr.
- Do not mock the filesystem for bundle tests — build real `.md` files under pytest's `tmp_path` (`tests/test_okf_bundle.py::bundle_dir`).
- Do not mock `Toolkit` construction — use real dataclass instances, including the built-in `VISUALIZATION_TOOLKIT` / `DATA_ANALYSIS_TOOLKIT` with `@pytest.mark.parametrize` (`tests/test_toolkits.py`).

## Fixtures and Factories

**Test Data:**

```python

# tests/test_okf_bundle.py — real markdown bundle under tmp_path

@pytest.fixture
def bundle_dir(tmp_path):
    """Create a minimal OKF bundle for testing."""
    (tmp_path / "datasets").mkdir()
    (tmp_path / "datasets" / "sales.md").write_text(
        "---\n"
        "type: Dataset\n"
        "title: Sales\n"
        "description: All sales-related tables.\n"
        "tags: [sales]\n"
        "timestamp: 2026-05-28T00:00:00Z\n"
        "---\n\n"
        "Contains [orders](/tables/orders.md) and [customers](/tables/customers.md).\n"
    )
    ...
```

**Location:**

- Fixtures live at the top of the test module that uses them (`bundle_dir` in `tests/test_okf_bundle.py`; `mock_client` / `interpreter` in `tests/test_agentcore_python_interpreter.py`). There is no shared `conftest.py` — add a new fixture to the module that needs it, and only promote to `conftest.py` when three or more modules need it.

## Coverage

**Requirements:** None enforced — no `--cov` flag, no `fail-under`, and no coverage service in `.github/workflows/` (the only workflow publishes to PyPI on release).

**View Coverage:**

```bash
uv pip install pytest-cov
uv run pytest --cov=strands_code_agent --cov-report=term-missing
```

## Test Types

**Unit Tests:**

- Scope: single module or class in isolation with external boundaries mocked (model, AWS). Examples: `tests/test_toolkits.py` (dataclass fields, equality, built-in toolkit contents), `tests/test_document_code.py` (signature/docstring rendering, private-method exclusion, `TypeError` on non-callables), `tests/test_utils.py` (base64 roundtrip via real temp files).
- Approach: construct the real object, call one method, assert on the return value or on a captured `mock_init.call_args` kwarg.

**Integration Tests:**

- Scope: real wiring across modules without a live model or live AWS. Examples: `tests/test_code_agent.py` (toolkit → authorized imports → real REPL execution, e.g. `stats.pearsonr` through `scipy.*` wildcards), `tests/test_okf_bundle.py` (markdown files → parse → links → search → formatted read output), `tests/test_readme_examples.py` (every README example as a regression test).
- Mark live-AWS tests with `@pytest.mark.integration` so they are deselected by default (`pyproject.toml` `addopts`). Follow the existing `interpreter`/`mock_client` pattern so new remote tests run offline by default.

**E2E Tests:**

- Not used. No browser, notebook, or deployed-agent harness exists. The closest proxy is `tests/test_readme_examples.py`, which mirrors each README section (`TestReadmeQuickStart`, `TestReadmeToolkitConstruction`, `TestReadmeBuiltinToolkits`) — update it whenever README examples change.

## Common Patterns

**Async Testing:**

```python

# Not used — the codebase is fully synchronous. Do not add asyncio, anyio, or trio

# markers. New interpreter or bundle APIs must stay sync to match execute_code(),

# read(), find(), children(), and toc().

```

**Error Testing:**

```python

# tests/test_exec_python_interpreter.py — errors surface as stderr text, not raises

def test_runtime_error(self):
    interp = ExecPythonInterpreter()
    _, stderr = interp.execute_code("1 / 0")
    assert stderr != ""

# tests/test_document_code.py — programmer errors raise with matchable messages

def test_invalid_input(self):
    with pytest.raises(TypeError, match="Expected a function or class"):
        get_documentation(42)

# tests/test_sandboxed_python_interpreter.py — sandbox denials surface as stderr

def test_unauthorized_import_fails(self):
    interp = SandboxedPythonInterpreter(authorized_imports=[])
    _, stderr = interp.execute_code("import subprocess")
    assert stderr != ""
```

---

*Testing analysis: 2026-09-22*
