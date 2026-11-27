---
phase: 20-monty-python-vm-for-python-repl-codeact
plan: "01"
subsystem: sandbox-monty-vm
tags: [pydantic-monty, rust-vm, resource-limits, crash-recovery, pool, conftest]
requires: []
provides:
  - pyproject.toml core dependency pydantic-monty (no upper pin) + MONTY_BIN scrub in tests/conftest.py
  - strands_code_cli/sandbox/monty.py (MontyPythonInterpreter implementing PythonInterpreter)
  - Wave 0 tests/sandbox/test_monty.py (stateful VM, stdlib/import denial, limits, MontyCrashedError salvage, concurrency)
affects: [20-02, 20-03]
tech-stack:
  added: [pydantic-monty>=0.0.23 (direct dep)]
  patterns:
    - Process-wide lazy shared Monty() pool with per-interpreter isolated checked-out sessions and atexit teardown
    - AST pre-execution denied-import gate (os, pathlib, subprocess, __import__, importlib) + os=None VM isolation
key-files:
  created:
    - strands_code_cli/sandbox/monty.py
    - tests/sandbox/test_monty.py
  modified:
    - pyproject.toml
    - tests/conftest.py
decisions:
  - Used live pydantic_monty 0.0.23 ResourceLimits(max_memory, max_duration_secs, max_recursion_depth) and explicit AST import blocking for os/pathlib/subprocess alongside os=None (because os=None allows bare import os without raising unless AST-blocked).
  - Kept MontyPythonInterpreter session checkout lazy in _ensure_session_unlocked() so missing pydantic_monty or missing MONTY_BIN fails closed in execute_code() without falling back to smolagents or crashing agent construction.
metrics:
  completed: 2026-11-27
---

# Plan 20-01 Summary: `pydantic-monty` Packaging, `MontyPythonInterpreter` & Wave 0 Tests

Delivered Wave 1 (`SANDBOX-02` tracer):
- **Core packaging (`D-01`):** Added `pydantic-monty` directly to `[project.dependencies]` in `pyproject.toml`, verified lock/sync (`142 packages`), and added `"MONTY_BIN"` to `tests/conftest.py` `_PROVIDER_ENV_VARS`.
- **Crash-isolated Rust VM (`D-02`, `D-04`, `D-05`, `D-06`, `D-09`):** Built `strands_code_cli/sandbox/monty.py` (`MontyPythonInterpreter`) with stateful `feed_run` sessions, pure-Rust stdlib (`math`, `json`, `re`, `collections`, `datetime`, `base64`, `dataclasses`, `typing`) + `ascii` builtin parity, AST + `os=None` denial of `os`/`pathlib`/`subprocess`, `256 MiB` memory / `60s` duration / `200` recursion / `4 MiB` stdout caps, fail-closed startup, real `MontyCrashedError` pre-crash stdout salvage + session replacement + state-reset notice, thread-safe lazy shared pool, and `close()` / `clear_state()` / `close_repl_tool()` / `close_agent_repls()` / `atexit` cleanup.
- **Wave 0 suite & gates:** `tests/sandbox/test_monty.py` (`7 passed` in `2.40s`), `uv lock --check`, `ruff format --check`, `ruff check`, `xenon --max-absolute C`, `lint-imports` (`47 files`), and empty `git diff ee42ea2 -- strands_code_agent/`.
