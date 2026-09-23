---
last_mapped_commit: 4a23ae24e72098045e1d04b5328d95967221c4a0
last_mapped_at: 2026-09-22
---
# Technology Stack

**Analysis Date:** 2026-09-22

## Languages

**Primary:**

- Python >=3.10 - All library code in `strands_code_agent/`, all tests in `tests/`, example in `examples/`

**Secondary:**

- None - No TypeScript, JavaScript, or other languages detected in the repo

## Runtime

**Environment:**

- Python >=3.10 (classifiers cover 3.10–3.13; observed dev interpreter is Python 3.14.7)

**Package Manager:**

- uv
- Lockfile: present (`uv.lock`, ~755 KB, pins `strands-agents 1.57.0`, `strands-harness 0.1.2`, `smolagents 1.26.0`, `boto3 1.43.100`, `pytest 9.1.1`)

## Frameworks

**Core:**

- strands-agents 1.57.0 - Agent runtime; `CodeAgent` subclasses `strands.Agent` (`strands_code_agent/code_agent.py`), `@tool` decorator defines `python_repl` (`strands_code_agent/python_environments/base.py`)
- strands-harness 0.1.2 - CLI direction only (planned `create_harness()` composition per `README.md`); not imported by library code yet
- smolagents 1.26.0 - Sandboxed execution backend; `SandboxedPythonInterpreter` wraps `smolagents.local_python_executor.LocalPythonExecutor` (`strands_code_agent/python_environments/local_sandboxed.py`)
- Jinja2 3.1.6 - System-prompt templating (`CODE_PREAMBLE_TEMPLATE`, `TEMP_DIR_TEMPLATE`, `DOMAIN_SPECIFIC_DOC_TEMPLATE` in `strands_code_agent/code_agent.py`)
- Rich 15.0.0 - Terminal rendering in `CodeAgentCallbackHandler` (`strands_code_agent/callback_handler.py`: `Syntax`, `JSON`, `Markdown`, `Pretty`, `Console`)
- PyYAML 6.0.3 - OKF bundle frontmatter parse/dump (`strands_code_agent/knowledge/bundle.py`, `strands_code_agent/knowledge/pdf_to_okf_bundle.py`)

**Testing:**

- pytest >=8 (locked 9.1.1) - Test runner; `integration` marker deselected by default via `[tool.pytest.ini_options]` in `pyproject.toml`
- numpy / pandas / matplotlib / seaborn / scipy (dev dependency group) - Required at test runtime because toolkit wiring tests execute real plotting/analysis code (noted in `pyproject.toml` comment)

**Build/Dev:**

- hatchling - Build backend (`[build-system]` in `pyproject.toml`)
- uv 0.9.26 - Sync/install workflow (`uv sync` per `README.md`)
- GitHub Actions `publish.yml` - `pip install build` + `python -m build` on release

## Key Dependencies

**Critical:**

- strands-agents >=0.1.0 (locked 1.57.0) - Without it `CodeAgent` and the `python_repl` tool cannot exist
- smolagents >=1.0.0 (locked 1.26.0) - Powers the default `SandboxedPythonInterpreter` (import allowlisting, timeouts)
- Jinja2 >=3.0 - System-prompt assembly; removing it breaks `CodeAgent.__init__`
- Rich >=13.0 - Callback handler rendering only; safe to make optional for headless use
- PyYAML >=6.0 - OKF bundle read/write; required by `strands_code_agent/knowledge/`

**Infrastructure:**

- boto3 >=1.35.0 (locked 1.43.100, optional `agentcore` extra) - Only import is `strands_code_agent/python_environments/agentcore.py`; local-only installs never touch it
- botocore (via boto3) - Monkey-patched in `strands_code_agent/solution_user_agent.py` to append `AWSSOLUTION/SO0353/v0.4.0` to User-Agent; imported at package init (`strands_code_agent/__init__.py`)
- pymupdf (`fitz`) - Lazily imported inside `pdf_to_okf_bundle()` (`strands_code_agent/knowledge/pdf_to_okf_bundle.py`); NOT declared in `pyproject.toml`, so `pip install pymupdf` is required manually before PDF conversion (the example documents this)

## Configuration

**Environment:**

- No `.env` files, no `os.environ`/`os.getenv` reads anywhere in `strands_code_agent/` - all tuning is constructor kwargs (`region`, `timeout_seconds`, `tmp_dir`, `toolkits`, `model` via `**kwargs` to `strands.Agent`)
- AWS credentials resolve through the standard boto3 chain (env vars, shared config, IAM role) - implicit, never read directly in code
- `CodeAgent(tmp_dir=True)` creates a per-agent directory via `tempfile.mkdtemp(dir='/tmp')` and advertises it in the system prompt (`strands_code_agent/code_agent.py`)

**Build:**

- `pyproject.toml` - Project metadata, dependencies, optional `agentcore` extra, dev group, pytest config; no `[tool.hatch]` overrides (hatchling defaults)
- `uv.lock` - Pinned dependency tree
- `.github/workflows/publish.yml` - Release-to-PyPI build pipeline (checkout, setup-python 3.11, `python -m build`, `pypa/gh-action-pypi-publish`)
- No `tsconfig.json`, `.nvmrc`, `.python-version`, Dockerfiles, or linter/formatter configs detected

## Platform Requirements

**Development:**

- Python >=3.10 with `uv` (`uv sync` reproduces project-local `.venv`)
- Dev/test extras: `numpy`, `pandas`, `matplotlib`, `seaborn`, `scipy` (test-only runtime needs)
- Optional: `pip install .[agentcore]` + AWS credentials for `AgentCorePythonInterpreter`; `pip install pymupdf` for PDF-to-OKF conversion

**Production:**

- Published as a PyPI library (`strands-code-agent 0.4.0`, `hatchling.build`); consumers embed `CodeAgent` in their own process
- No server, container, or hosting target in this repo; no deployment manifests

---

*Stack analysis: 2026-09-22*
