---
phase: 20-monty-python-vm-for-python-repl-codeact
plan: "03"
subsystem: sandbox-box-and-docs
tags: [strands-box, monty, exec-grant, quickstart, integration-test, ci-gates]
requires:
  - "20-01"
  - "20-02"
provides:
  - Canonical non-root monty binary discovery (_resolve_monty_binary) feeding [agent.filesystem].exec and [agent.filesystem].read in sandbox/box.py
  - Intentionally omitted [tool.python] / Dogwood python:execute with documented evaluation in docs/QUICKSTART.md
  - Offline TestMontyBinaryBoxGrant unit suite and live strands-box 0.3.1 (CLONE_NEWUSER) MontyPythonInterpreter execution check
  - Complete Phase 20 verification across all 6 CI gates, tests/rig/, full non-integration suite, loopback stub, and live Box+Monty run
affects: [21-01, 22-01, 23-01]
tech-stack:
  added: []
  patterns:
    - Canonical realpath exec-binary resolution (MONTY_BIN override with control-char rejection, .venv/bin/monty, PATH, sysconfig scripts, and non-root parent guard)
key-files:
  created:
    - .planning/phases/20-monty-python-vm-for-python-repl-codeact/20-03-SUMMARY.md
    - .planning/phases/20-monty-python-vm-for-python-repl-codeact/20-VERIFICATION.md
  modified:
    - strands_code_cli/sandbox/box.py
    - tests/sandbox/test_box.py
    - docs/QUICKSTART.md
    - .planning/phases/20-monty-python-vm-for-python-repl-codeact/20-VALIDATION.md
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md
    - .planning/STATE.md
decisions:
  - Kept embedded Strands Box [tool.python] and Dogwood python:execute omitted from box.toml and policy.dw because strands-code's python_repl and CodeAct run directly inside pydantic-monty Rust worker processes with workspace-scoped host callbacks, needing only [agent.filesystem].exec on the canonical monty binary.
metrics:
  completed: 2026-11-27
---

# Plan 20-03 Summary: Strands Box `monty` Exec Grant, Live Box+Monty Integration, Docs & Full CI Verification

Delivered Wave 3 (`SANDBOX-02` Strands Box alignment, docs, and verification):
- **Box `monty` binary grant (`D-10`, `D-11`):** Added `_valid_monty_candidate()` and `_resolve_monty_binary()` to `strands_code_cli/sandbox/box.py` (`MONTY_BIN` with `_reject_control_chars`, `venv_bin / "monty"`, `shutil.which("monty", path=env_path)`, and `sysconfig.get_path("scripts") / "monty"`, canonicalized with `os.path.realpath` and filtered by `_valid_nonroot_dir`), adding `monty_bin` to `resolve_runtime_paths()["exec"]` (and its parent directory to `"read"` when non-root) while keeping `[tool.python]` / `python:execute` omitted.
- **Offline & live `strands-box 0.3.1` coverage:** Added `TestMontyBinaryBoxGrant` (3 unit tests covering `.venv/bin/monty`, `MONTY_BIN` + control-char/refused-root rejection, and `PATH` fallback) plus `_assert_box_run_monty()` inside `@pytest.mark.integration` `test_host_strands_box_or_dogwood_validates_generated_policy`, verifying real `MontyPythonInterpreter` execution (`import math, json; print(json.dumps({"r": math.isqrt(144)}))` -> `{"r": 12}`) inside `CLONE_NEWUSER` (`1 passed, 30 deselected in 10.50s`).
- **Docs (`D-11`):** Documented `## Monty Python VM (python_repl & CodeAct)` and the Strands Box embedded `[tool.python]` evaluation in `docs/QUICKSTART.md`.
- **Full post-edit verification:** Restricted-module check clean; `uv lock --check`, `ruff format --check` (`137 files`), `ruff check`, `xenon --max-absolute C`, `lint-imports` (`47 files, 147 deps, 1 kept / 0 broken`), empty `git diff ee42ea2 -- strands_code_agent/`, `tests/sandbox/` (`48 passed, 1 deselected`), `tests/rig/` (`44 passed`), full non-integration suite (`2011 passed, 16 deselected`), and standalone loopback stub (`1 passed, 202 deselected`) all green.
