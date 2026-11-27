---
phase: 20-monty-python-vm-for-python-repl-codeact
plan: "02"
subsystem: cli-repl-and-codeact
tags: [monty, python-repl, codeact, btw, subagent, policy, symlinks]
requires:
  - "20-01"
provides:
  - All 3 CLI python_repl peer sites (entry/main.py, policy/codeact.py, loop/btw.py + entry/subagent.py) migrated to MontyPythonInterpreter
  - Deterministic VM teardown in _close_loop_session, _teardown_btw_agent, CodeactStint.close(), and _wrap_subagent_cleanup
  - Phase 19.1 symlink/O_NOFOLLOW/atomic_write_text/sensitive-read/protected-path floor and active PolicyConfig [[deny]] enforcement in CodeAct callbacks
affects: [20-03]
tech-stack:
  added: []
  patterns:
    - CodeAct host callbacks enforce Phase 19.1 path safety + non-interactive active PolicyConfig [[deny]] rules (fail-closed on symlinked repo policy)
    - Delegate and child agent REPL tracking via _python_repl_tool and _delegate_repl_tools with identity-tracked subagent stream cleanup
key-files:
  created: []
  modified:
    - strands_code_cli/sandbox/monty.py
    - strands_code_cli/entry/main.py
    - strands_code_cli/loop/btw.py
    - strands_code_cli/entry/subagent.py
    - strands_code_cli/loop/core.py
    - strands_code_cli/policy/codeact.py
    - uv.lock
    - tests/policy/test_codeact.py
    - tests/loop/test_btw.py
    - tests/entry/test_subagent.py
    - tests/loop/test_loop_cancel.py
decisions:
  - Tracked active pending subagent child objects by id(child) in _wrap_subagent_cleanup so interrupted child doubles remain alive until resumed while finished children release checked-out Monty workers immediately.
  - Verified Phase 19.1 sensitive-read parity against _is_sensitive_read_path (.env, .env.local, .ssh/*, .aws/*) alongside protected paths, FIFOs, symlinks, and active [[deny]] rules across direct callbacks and CodeactStint VM calls.
metrics:
  completed: 2026-11-27
---

# Plan 20-02 Summary: Migrate All CLI `python_repl` Sites & Harden CodeAct

Delivered Wave 2 (`SANDBOX-02` CLI wiring & CodeAct host hardening):
- **All 3 CLI `python_repl` peer sites migrated (`D-02`, `D-03`, `D-09`):**
  - Replaced `SandboxedPythonInterpreter` with `MontyPythonInterpreter` in `strands_code_cli/entry/main.py`, `strands_code_cli/policy/codeact.py` (`CodeactStint`), and `strands_code_cli/loop/btw.py` (`fresh_tools_for_delegate`, covering `/btw` and `strands_code_cli/entry/subagent.py`), leaving zero `SandboxedPythonInterpreter` references across `strands_code_cli/`.
  - Added deterministic worker teardown hooks (`_close_loop_session` closing main `agent` REPLs + `CodeactStint.close()`, `_teardown_btw_agent`, and `_wrap_subagent_cleanup`).
- **Hardened CodeAct host callbacks (`D-07`, `D-08`):**
  - Backported Phase 19.1 symlink refusal, `O_NOFOLLOW | O_NONBLOCK` regular-file UTF-8 reads, `atomic_write_text`, sensitive-read refusal (`.env*`, `.ssh/*`, `.aws/*`), and protected-path blocks into `codeact_read`, `codeact_write`, and `codeact_edit`.
  - Added non-interactive active `PolicyConfig` `[[deny]]` enforcement (failing closed on symlinked `.agent/policy.toml`) across `codeact_read`, `codeact_write`, `codeact_edit`, and `codeact_shell`.
- **Verification:** `tests/policy/ tests/loop/ tests/entry/ tests/dispatch/test_cli_entry.py tests/sandbox/test_monty.py` (`681 passed, 1 deselected`), `uv lock --check`, `ruff format --check`, `ruff check`, `xenon --max-absolute C`, `lint-imports` (`47 files, 147 deps, 1 kept / 0 broken`), and empty `git diff ee42ea2 -- strands_code_agent/`.
