---
last_mapped_commit: 4a23ae24e72098045e1d04b5328d95967221c4a0
last_mapped_at: 2026-09-22
---
# Codebase Structure

**Analysis Date:** 2026-09-22

## Directory Layout

```
strands-code/
├── strands_code_agent/       # Library package (all runtime code)
│   ├── code_agent.py         # CodeAgent: prompt assembly + python_repl wiring
│   ├── toolkits.py           # Toolkit dataclass + shipped VISUALIZATION/DATA_ANALYSIS presets
│   ├── document_code.py      # Symbol-to-prompt documentation renderer
│   ├── imports.py            # AST import extraction + import-string builder
│   ├── callback_handler.py   # Rich terminal rendering of agent traffic
│   ├── utils.py              # image_to_base64 + Bedrock response metrics
│   ├── solution_user_agent.py# botocore User-Agent side-effect hook (import-only)
│   ├── __init__.py           # Public exports: CodeAgent, Toolkit, AgentCorePythonInterpreter
│   ├── python_environments/  # Execution backends (Strategy behind PythonInterpreter ABC)
│   │   ├── base.py           # ABC + python_repl @tool factory
│   │   ├── local_exec.py     # Unrestricted exec() backend (trusted use)
│   │   ├── local_sandboxed.py# Default allowlisted backend (smolagents executor)
│   │   ├── agentcore.py      # Remote Bedrock AgentCore backend (optional extra)
│   │   └── __init__.py       # Empty (intentionally: import backends by module path)
│   └── knowledge/            # OKF file-bundle knowledge library (standalone-usable)
│       ├── __init__.py       # Exports OKFBundle, Concept, SearchIndex, KeywordSearchIndex, pdf_to_okf_bundle
│       ├── bundle.py         # OKFBundle navigator (lazy load + backlinks + context)
│       ├── concept.py        # Concept dataclass (one .md file)
│       ├── search.py         # SearchIndex ABC + KeywordSearchIndex default
│       └── pdf_to_okf_bundle.py # PDF TOC → bundle converter (lazy pymupdf import)
├── tests/                    # pytest suite mirroring the package (test_<module>.py)
├── examples/
│   └── pdf_to_okf_bundle/    # End-to-end knowledge example (script + README, gitignored outputs)
├── docs/
│   └── competitive-gap-analysis.md  # Product/strategy direction (CLI on strands-harness)
├── .planning/
│   └── codebase/             # GSD codebase maps (this directory)
├── pyproject.toml            # Project metadata, deps, pytest config
├── uv.lock                   # Locked dependencies (uv)
├── README.md                 # Quick start + library essentials + CLI direction
└── LICENSE                   # MIT-0
```

## Directory Purposes

**`strands_code_agent/` (top-level package):**

- Purpose: Entire runtime library; flat composition layer (`CodeAgent`, `Toolkit`, prompt builders, callback, utils).
- Contains: Seven small modules plus `__init__.py`; no subpackages except the two below.
- Key files: `code_agent.py` (start here), `toolkits.py`, `__init__.py` (public surface).

**`strands_code_agent/python_environments/`:**

- Purpose: Swappable code-execution backends behind the `PythonInterpreter` ABC.
- Contains: One ABC/factory module plus one module per backend.
- Key files: `base.py` (read first — the `python_repl` contract), `local_sandboxed.py` (default), `local_exec.py`, `agentcore.py`.

**`strands_code_agent/knowledge/`:**

- Purpose: Self-contained OKF knowledge-bundle library (no dependency on the agent layer).
- Contains: Dataclass, navigator, search backends, PDF converter.
- Key files: `bundle.py` (core API), `concept.py`, `search.py` (extension seam), `pdf_to_okf_bundle.py`.

**`tests/`:**

- Purpose: pytest suite, one `test_<subject>.py` per unit plus README/example coverage.
- Contains: `test_code_agent.py`, `test_toolkits.py`, `test_exec_python_interpreter.py`, `test_sandboxed_python_interpreter.py`, `test_agentcore_python_interpreter.py`, `test_document_code.py`, `test_okf_bundle.py`, `test_readme_examples.py`, `test_utils.py`.
- Key files: `test_code_agent.py` (agent assembly contract), `test_okf_bundle.py` (knowledge API contract).

**`examples/pdf_to_okf_bundle/`:**

- Purpose: Runnable end-to-end pattern for bundle-backed agents (download PDF → convert → query with `CodeAgent`).
- Contains: `agent_with_knowledge.py`, `README.md`; generated PDF/bundle outputs are runtime artifacts, not committed.
- Key files: `agent_with_knowledge.py` (canonical `Toolkit(domain_specific_code=[OKFBundle], initialization_code=...)` usage).

**`docs/`:**

- Purpose: Strategy and direction notes, not API docs.
- Contains: `competitive-gap-analysis.md` (harness-first directives, CLI surface, memory tiers).

**`.planning/codebase/`:**

- Purpose: GSD-generated codebase maps for planners/executors.
- Contains: `ARCHITECTURE.md`, `STRUCTURE.md` (this file), plus tech/quality/concerns docs from sibling mappers.
- Generated: Yes (by GSD mappers). Committed: Yes.

## Key File Locations

**Entry Points:**

- `strands_code_agent/__init__.py`: Public imports (`CodeAgent`, `Toolkit`, `AgentCorePythonInterpreter`); triggers `solution_user_agent` side effect.
- `strands_code_agent/code_agent.py`: `CodeAgent(...)` constructor — the only agent entry point (no CLI/`__main__`/console script exists yet).
- `strands_code_agent/knowledge/__init__.py`: Knowledge entry point (`OKFBundle`, `pdf_to_okf_bundle`, search backends).
- `examples/pdf_to_okf_bundle/agent_with_knowledge.py`: Runnable composition example; copy its toolkit pattern for bundle-backed agents.

**Configuration:**

- `pyproject.toml`: Package metadata, runtime deps (`strands-agents`, `strands-harness`, `smolagents`, `jinja2`, `rich`, `pyyaml`), `agentcore` extra (`boto3`), dev group (pytest, numpy/pandas/matplotlib/seaborn/scipy for toolkit tests), pytest `addopts` deselecting `integration` markers.
- `uv.lock`: Pinned dependency tree for `uv sync`.
- `.gitignore`: Standard Python ignores plus example artifacts (`bedrock_agentcore_guide.pdf`, `agentcore_bundle/`).

**Core Logic:**

- `strands_code_agent/code_agent.py`: Toolkit merge + system-prompt assembly + interpreter construction + tool registration.
- `strands_code_agent/python_environments/base.py`: `PythonInterpreter` ABC and the `python_repl` tool definition — read before touching any backend.
- `strands_code_agent/knowledge/bundle.py`: `OKFBundle` navigation API (`find`/`read`/`children`/`toc`, `expand`, `context`, backlinks).
- `strands_code_agent/toolkits.py`: `Toolkit` dataclass and the two shipped presets.

**Testing:**

- `tests/test_code_agent.py`: Agent construction, prompt assembly, toolkit merging.
- `tests/test_sandboxed_python_interpreter.py` / `tests/test_exec_python_interpreter.py`: Local backend behavior.
- `tests/test_agentcore_python_interpreter.py`: Remote backend (live tests need AWS creds + `agentcore` extra).
- `tests/test_okf_bundle.py`: Knowledge navigation contract.
- `tests/test_readme_examples.py`: README snippets stay runnable.

## Naming Conventions

**Files:**

- Modules: `snake_case.py` mirroring the exported symbol (`code_agent.py` → `CodeAgent`, `toolkits.py` → `Toolkit`, `concept.py` → `Concept`, `bundle.py` → `OKFBundle`).
- Tests: `tests/test_<module_subject>.py` (e.g. `test_code_agent.py`, `test_okf_bundle.py`, `test_sandboxed_python_interpreter.py`).
- Knowledge concepts: `<slug>.md` with YAML frontmatter; `index.md` / `log.md` reserved and skipped by the loader.

**Directories:**

- Packages: `snake_case` (`strands_code_agent`, `python_environments`, `knowledge`); test/example dirs plural (`tests/`, `examples/`), docs singular (`docs/`).

**Symbols (follow these when adding code):**

- Classes: `PascalCase` (`CodeAgent`, `Toolkit`, `OKFBundle`, `Concept`, `*PythonInterpreter`, `SearchIndex`).
- Functions/methods: `snake_case` (`get_documentation`, `extract_imports`, `execute_code`, `clear_state`, `pdf_to_okf_bundle`).
- Constants/templates: `UPPER_SNAKE` (`CODE_AGENT_INSTRUCTIONS`, `CODE_PREAMBLE_TEMPLATE`, `STDOUT_LABEL`, `SOLUTION_UA`).
- Private helpers: leading underscore (`_ensure_loaded`, `_parse_frontmatter`, `_build_initialization`, `_stop_session`).

## Where to Add New Code

**New agent capability (libraries + preamble + guidance for the REPL):**

- Primary code: extend `strands_code_agent/toolkits.py` with a new `Toolkit(...)` preset (follow `VISUALIZATION_TOOLKIT` / `DATA_ANALYSIS_TOOLKIT`).
- Wiring: none needed — `CodeAgent` merges any `toolkits=[...]` entry automatically.
- Tests: `tests/test_toolkits.py` (+ `tests/test_code_agent.py` if prompt assembly changes).

**New execution backend:**

- Implementation: new module in `strands_code_agent/python_environments/` subclassing `PythonInterpreter` from `strands_code_agent/python_environments/base.py`; implement `clear_state()` + `execute_code(code) -> tuple[str, str]`.
- Selection: consumers pass it as `CodeAgent(python_interpreter_class=...)`; do not hardcode it into `code_agent.py` (default stays `SandboxedPythonInterpreter`).
- Tests: `tests/test_<backend>_python_interpreter.py`; mark live-service tests `integration` per `pyproject.toml`.

**New prompt/context builder (symbol docs, import logic):**

- Implementation: `strands_code_agent/document_code.py` or `strands_code_agent/imports.py` alongside the existing pure functions; wire into `CodeAgent.__init__` in `strands_code_agent/code_agent.py`.
- Tests: `tests/test_document_code.py` / `tests/test_code_agent.py`.

**New knowledge feature (navigation, search backend, converter):**

- Implementation: `strands_code_agent/knowledge/` — navigation in `bundle.py`, data shape in `concept.py`, alternate ranking by subclassing `SearchIndex` in `search.py`, ingestion helpers beside `pdf_to_okf_bundle.py`.
- Exports: re-export public names from `strands_code_agent/knowledge/__init__.py` and extend `__all__`.
- Tests: `tests/test_okf_bundle.py`; keep the package importable without heavy deps (lazy-import like `fitz`).

**Utilities:**

- Shared helpers: `strands_code_agent/utils.py` (pure, dependency-light functions only).
- Tests: `tests/test_utils.py`.

**Presentation (terminal output):**

- Implementation: `strands_code_agent/callback_handler.py`; keep it side-effect-only (rendering, never control flow).

## Special Directories

**`.venv/`:**

- Purpose: Project-local virtualenv created by `uv sync`.
- Generated: Yes.
- Committed: No.

**`.pytest_cache/`:**

- Purpose: Local pytest run cache.
- Generated: Yes.
- Committed: No.

**`examples/pdf_to_okf_bundle/` outputs (`bedrock_agentcore_guide.pdf`, `agentcore_bundle/`):**

- Purpose: Downloaded source PDF and generated OKF bundle produced by running the example.
- Generated: Yes (at runtime).
- Committed: No (gitignored).

**`.planning/`:**

- Purpose: GSD planning and codebase-map artifacts.
- Generated: Partially (mapper-written docs).
- Committed: Yes.

---

*Structure analysis: 2026-09-22*
