# Phase 20: Monty Python VM for `python_repl` & CodeAct - Research

**Researched:** 2026-11-27
**Scope:** `SANDBOX-02` (`pydantic-monty` Rust VM for `python_repl` & `CodeactStint`, Phase 19.1 CodeAct callback security parity, deterministic worker-pool teardown, `box.py` `monty` exec grant + live `strands-box 0.3.1` verification)
**Locked Decisions:** [20-CONTEXT.md](file:///home/csaba/repos/AWS/strands-code/.planning/phases/20-monty-python-vm-for-python-repl-codeact/20-CONTEXT.md) (`D-01`–`D-11`)

---

## §1 `pydantic-monty` Architecture & Verification Seam

- **Packaging (`D-01`):** `pydantic-monty` is a metapackage combining `pydantic-monty-client` (`import pydantic_monty`) and `pydantic-monty-runtime` (distributing compiled Rust `monty` CLI/worker binary wheels into `.venv/bin/monty` across Linux `x86_64`/`aarch64`, macOS, and Windows on Python `>=3.11`).
  - Matches our Phase 19.2 `requires-python = ">=3.11"` floor in [pyproject.toml](file:///home/csaba/repos/AWS/strands-code/pyproject.toml#L11).
  - Kept in `[project.dependencies]` alongside `httpx`, leaving `[project.optional-dependencies]` strictly for third-party model-provider SDKs (`D-01`).
  - `smolagents>=1.24.0` remains in `[project.dependencies]` solely for the untouched upstream `strands_code_agent/` package (`D-24`).
- **Binary resolution order in `pydantic-monty`:**
  1. Explicit `Monty(binary_path=...)`
  2. `MONTY_BIN` environment variable
  3. Active Python environment's scripts directory (`.venv/bin/monty`)
  4. `PATH`
- **Execution & crash isolation API:**
  - `Monty()` spawns/manages a pool of worker subprocesses; `pool.checkout(limits=ResourceLimits(...))` checks out a persistent stateful REPL session (`feed_run`, `external_lookup`, `print_callback`).
  - `ResourceLimits`: enforces `max_memory` (`256 * 1024 * 1024`), `max_feed_duration_secs` (`60`), and `max_recursion_depth` (`200`) (`D-05`).
  - `MontyCrashedError`: raised when the worker subprocess aborts (OOM, hard timeout, segfault); pool automatically discards the broken worker so the CLI host process stays unharmed (`D-06`).
  - **Wave 1 Task 1 verification seam:** Before finalizing `MontyPythonInterpreter` kwargs, Wave 1 Task 1 runs `uv lock` + `uv sync --all-extras` (outside sandbox once for PyPI wheel fetch) and inspects the live installed `pydantic_monty` / `pydantic_monty_runtime` module signatures in `.venv/bin/python` (exact class/field names for `Monty`, `ResourceLimits`, `MontyCrashedError`, `external_lookup`, `print_callback`, and binary discovery helper).

---

## §2 Codebase Audit & Live `radon cc` Complexity Inventory (`HEAD` = `684baa4`)

### 2.1 Three CLI `python_repl` Peer Sites (`D-03`)

| Site | File & Line | Current Backend | Current Imports / Functions | Target Backend |
| :--- | :--- | :--- | :--- | :--- |
| Main tool-turn REPL | `strands_code_cli/entry/main.py:237` | `SandboxedPythonInterpreter("", authorized_imports=set())` | `set()` / none | `MontyPythonInterpreter` (`D-04` pure stdlib + denied `os`/`pathlib`/`subprocess`) |
| CodeAct stint | `strands_code_cli/policy/codeact.py:306` (`CodeactStint`) | `SandboxedPythonInterpreter("", authorized_imports=CODEACT_AUTHORIZED_IMPORTS, additional_functions={read, write, edit, shell}, timeout_seconds=60)` | `{"math"}` / `codeact_read`, `codeact_write`, `codeact_edit`, `codeact_shell` | `MontyPythonInterpreter` (`D-04` pure stdlib + hardened `read`/`write`/`edit`/`shell` host callbacks) |
| `/btw` & `subagent` delegate REPL | `strands_code_cli/loop/btw.py:438` (`fresh_tools_for_delegate`), called at `loop/btw.py:507` & `entry/subagent.py:73` | `SandboxedPythonInterpreter("", authorized_imports=set()).get_tool()` | `set()` / none | Fresh isolated `MontyPythonInterpreter` session (`D-03`, `D-09`) |

*(Upstream library `strands_code_agent/code_agent.py:141` stays on `SandboxedPythonInterpreter` and remains byte-pristine per `D-24`.)*

### 2.2 Worker Pool Lifecycle & Teardown Seams (`D-09`)

- `strands_code_cli/policy/codeact.py:284-334`: `CodeactStint` currently lazily builds `_interpreter`, resets via `_interpreter.clear_state()`, and has no `close()` method.
- `strands_code_cli/loop/core.py:2582-2628`: `_close_loop_session()` tears down `btw`, `session_pump`, `agent`, `flush_memory`, and `live_btw_agent`, but does **not** close `stint` or `agent`'s main `python_repl` interpreter.
- `strands_code_cli/loop/btw.py` (`_teardown_btw_agent`) & `strands_code_cli/entry/subagent.py` (child completion `finally` / delegate tool registry): need deterministic closing of delegate `python_repl` sessions so checked-out sessions are released immediately on delegate exit without waiting for GC.
- Attaching `_interpreter = self` onto the `@tool` function returned by `MontyPythonInterpreter.get_tool()` lets `close_repl_tool(tool)` / `close_agent_repls(agent)` close main, `/btw`, and `subagent` sessions uniformly without editing `strands_code_agent/python_environments/base.py` (`D-24`).

### 2.3 CodeAct Host Callback Security Gaps (`D-07`, `D-08`)

Currently `strands_code_cli/policy/codeact.py:156-282` has **5 security gaps** relative to Phase 19.1:
1. `codeact_read`, `codeact_write`, `codeact_edit` only call `confine(resolve(path, cwd), cwd)` — they do **not** call `refuse_symlink` / `refuse_symlink_under_roots` and read/write with `Path.read_text()` / `Path.write_text()` instead of `O_NOFOLLOW` / `atomic_write_text(..., mode=None)`.
2. `codeact_read` does **not** check `_is_sensitive_read_path()` (`.env*`, `~/.ssh/*`, `~/.aws/*`, `*.pem`/`*.key`).
3. `codeact_write` & `codeact_edit` do **not** check `_is_protected_skills_or_config_path()` (`.agent/**`, `.git/**`, `STRANDS.md`, `~/.config/strands-code/**`, `~/.cache/strands-code/**`, `~/.config/strands-box/**`, `~/.local/share/strands-box/**`) or `_is_sensitive_read_path()` on `edit`.
4. None of `codeact_read`, `codeact_write`, `codeact_edit`, or `codeact_shell` evaluate active `PolicyConfig` `[[deny]]` rules (`PolicyConfig.load(repo_path=base / ".agent" / "policy.toml")` + `decide(...)`), allowing dynamically constructed arguments in an approved CodeAct block to bypass `[[deny]]` rules or symlinked repo policies.
5. `codeact_write` calls `target.parent.mkdir(parents=True, exist_ok=True)` without checking parent/ancestor symlinks first.

### 2.4 Strands Box `box.py` Grant Seam (`D-10`, `D-11`)

- `strands_code_cli/sandbox/box.py:536-612` (`resolve_runtime_paths`): resolves `py_real`, `strands-code`, `lib-dynload`, and `site-packages` into `exec_paths`, and `git`/`pytest`/`rg`/`ruff`/`uv` into `[tool.*]`, but does **not** resolve the `pydantic-monty-runtime` `monty` executable for `[agent.filesystem].exec`.
- Under `STRANDS_BOX=1`, if `monty` is installed outside the exact directories already in `exec` (e.g., inside `.venv/bin/monty` or `site-packages/pydantic_monty_runtime/bin/monty` or `~/.local/bin/monty`), `monty` binary execution fails with `EACCES` unless its canonical realpath is added to `[agent.filesystem].exec` (and its parent dir to `read` if outside `.venv` and non-root).
- `[tool.python]` / `python:execute` remain intentionally omitted from generated `box.toml`/`policy.dw` (`D-11`) and documented in `docs/QUICKSTART.md`.

### 2.5 Live `radon cc` Complexity Check (`xenon --max-absolute C`, `CC <= 20`)

Measured on `HEAD` `684baa4`:
- `entry/main.py`: `model_for_config` (`C 18`), `build_agent` (`C 15`), `_root` (`C 15`)
- `policy/codeact.py`: `codeact_shell` (`C 11`)
- `loop/btw.py`: `fork_btw_history` (`C 13`), `_fork_message_content` (`C 11`)
- `loop/core.py`: `run_loop` (`C 18`), `_route_side_spawn` (`C 18`), `_close_loop_session` (`<= B`)
- `entry/subagent.py`: `_select_child_tools` (`C 13`), `_resolve_child_model` (`C 13`)
- `sandbox/box.py`: `_render_agent_env` (`C 17`), `resolve_runtime_paths` (`C 11`)

Keeping new logic in `sandbox/monty.py` and small single-purpose helpers (`_prepare_codeact_path`, `close_repl_tool`, `_resolve_monty_binary`) keeps every function comfortably `<= C 15`.

---

## §3 Existing Test Migration & Invariant Inventory

- **Untouched upstream agent tests (`D-24`):** `tests/agent/test_code_agent.py`, `tests/agent/test_sandboxed_python_interpreter.py`, `tests/agent/test_readme_examples.py` continue exercising `SandboxedPythonInterpreter` against `strands_code_agent/`.
- **Tests migrating to Monty behavior:**
  - `tests/policy/test_codeact.py:664-698`: update `test_allowlist_pinned_to_math` -> verify `MontyPythonInterpreter` instance, `json`/`re`/`math` support (`D-04`), and explicit fail-closed denial of `import os`, `import pathlib`, `import subprocess`. Expand callback security tests (`D-07`, `D-08`) and `CodeactStint.close()` tests (`D-09`).
  - `tests/loop/test_btw.py:1554-1608` & `tests/entry/test_subagent.py:91-150`: accept `MontyPythonInterpreter` / `SandboxedPythonInterpreter` inputs safely in `fresh_tools_for_delegate` while verifying the returned delegate tool uses an isolated `MontyPythonInterpreter` session and tears down cleanly.
  - `tests/cost/test_cost_context.py`, `tests/entry/test_session_resume.py`, `tests/model/test_model_switch.py`, `tests/session/test_kill_resume.py`: harness helper fixtures importing `SandboxedPythonInterpreter` directly can stay or switch cleanly as needed without affecting contract assertions.
  - `tests/conftest.py`: add `"MONTY_BIN"` to `_PROVIDER_ENV_VARS` so ambient host `MONTY_BIN` never leaks into non-integration unit tests.
- **Static CI gates:** `ruff format --check`, `ruff check`, `xenon --max-absolute C`, `lint-imports` (`sandbox/monty.py` is a leaf module, never imports `entry.main`), `uv lock --check`, restricted-module check (zero `os.environ`/`os.getenv` in `entry/main.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, `model/model_switch.py`, `cost/cost_context.py`), and `git diff ee42ea2 -- strands_code_agent/` empty.
