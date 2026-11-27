---
status: testing
phase: 20-monty-python-vm-for-python-repl-codeact
source: [20-01-SUMMARY.md, 20-02-SUMMARY.md, 20-03-SUMMARY.md, 20-VERIFICATION.md]
started: 2026-11-27T21:44:00Z
updated: 2026-11-27T21:46:00Z
---

# Phase 20 User Acceptance Testing (`SANDBOX-02`)

## Current Test

number: 1
name: Monty Python VM Core (`MontyPythonInterpreter`, Pure-Rust Stdlib, Import Blocking, Limits & Crash/Timeout Recovery) (`D-01`, `D-02`, `D-04`–`D-06`, `D-09`)
expected: `MontyPythonInterpreter` executes Python inside an isolated `pydantic-monty` Rust worker with cross-turn variable persistence, pure-computation stdlib (`math`, `json`, `re`, `collections`, `itertools`, `datetime`, `base64`, `dataclasses`, `typing`) + `ascii` builtin, fail-closed startup when missing/unlaunchable (zero `smolagents` fallback), AST + `os=None` blocking of `os`/`pathlib`/`subprocess`/`__import__`/`importlib`, `256 MiB` memory / `60s` wall / `200` recursion / `4 MiB` stdout caps, and salvage + recovery without leaving the session wedged after crash or limit exhaustion.
awaiting: user response

## Tests

### 1. Monty Python VM Core (`MontyPythonInterpreter`, Pure-Rust Stdlib, Import Blocking, Limits & Crash/Timeout Recovery) (`D-01`, `D-02`, `D-04`–`D-06`, `D-09`)
expected: `MontyPythonInterpreter` executes Python inside an isolated `pydantic-monty` Rust worker with cross-turn variable persistence, pure-computation stdlib (`math`, `json`, `re`, `collections`, `itertools`, `datetime`, `base64`, `dataclasses`, `typing`) + `ascii` builtin, fail-closed startup when missing/unlaunchable (zero `smolagents` fallback), AST + `os=None` blocking of `os`/`pathlib`/`subprocess`/`__import__`/`importlib`, `256 MiB` memory / `60s` wall / `200` recursion / `4 MiB` stdout caps, and salvage + recovery without leaving the session wedged after crash or limit exhaustion.
result: pending
evidence: |
  - Functional probe on `HEAD` `f177e5e`:
    - Stateful execution (`x = 41` -> `x + 1 == 42`), `ascii('é')`, pure-Rust stdlib (`math`, `json`, `re`, `collections`, `itertools`, `datetime`, `base64`, `dataclasses`, `typing`), blocked imports (`os`, `pathlib`, `subprocess`, `__import__`, `importlib`, `posix`, `io`, `socket`, `ctypes`, `builtins`, `inspect`, `gc`, `shutil`, `tempfile`), `exec`/`eval`/`open('/etc/passwd')` refusals, minimal non-leaking `sys`, surrogate replacement, `RecursionError`, `MemoryError` (`2 MiB` cap) + post-OOM recovery (`after_oom 2`), and stdout truncation verified.
  - Adversarial pre-check gaps found on `f177e5e` & fixed in `strands_code_cli/sandbox/monty.py` + `tests/sandbox/test_monty.py`:
    1. `[Code/Reliability Gap]` Added `_is_monty_timeout()` + `_discard_session_unlocked()` + `(REPL state was reset after time limit.)` in `_run_snippet_unlocked()` so `TimeoutError` discards the cumulative-duration session cleanly instead of bricking subsequent turns.
    2. `[Code/Concurrency Gap]` Added `os.access(found, os.X_OK)` + control/surrogate char checks in `_resolve_monty_binary_path()` and entered replacement `Monty()` pool before swapping/closing `_SHARED_POOL` so invalid `binary_path` overrides never tear down healthy shared pools.
    3. `[Minor UX]` Formatted `_StdoutCollector.text` truncation cap dynamically (`4 MiB` vs `<N> bytes`).
  - Re-verified on fix `HEAD` (`Gaps found: None`): `232 passed, 2 deselected` (`tests/sandbox/`, `tests/policy/test_codeact.py`, `tests/loop/test_btw.py`, `tests/entry/test_subagent.py`), all 6 CI gates green, plus live re-probe (`RUN2 -> TimeoutError ... (REPL state was reset after time limit.)`, `RUN3 -> ('recovered', '')`, `CAP128 -> [stdout truncated at 128 bytes]`, `BAD_EXEC -> not executable`, `BAD_CTRL -> control character`, `AFTER_BAD_POOL -> ('still_ok: 77', '')`).

### 2. All 3 CLI `python_repl` Peer Sites Migrated & Deterministic Worker Teardown (`D-02`, `D-03`, `D-09`)
expected: Main REPL (`entry/main.py`), `CodeactStint` (`policy/codeact.py`), and `/btw` + `subagent` delegates (`loop/btw.py`, `entry/subagent.py`) all run `MontyPythonInterpreter` with isolated worker state and deterministic teardown (`_close_loop_session`, `_teardown_btw_agent`, `CodeactStint.close()`, `_wrap_subagent_cleanup`, `atexit`), with zero `SandboxedPythonInterpreter` remaining in `strands_code_cli/`.
result: pending

### 3. Hardened CodeAct Host Callbacks (`read`/`write`/`edit`/`shell`) & `PolicyConfig` `[[deny]]` Enforcement (`D-07`, `D-08`)
expected: CodeAct host callbacks enforce Phase 19.1 symlink refusal (leaf & intermediate ancestors), `O_NOFOLLOW | O_NONBLOCK` regular-file UTF-8 reads (blocking FIFOs/devices), `atomic_write_text`, sensitive-read refusal (`.env*`, `.ssh/*`, `.aws/*`), protected-path blocks (`.agent/**`, `.git/**`, `STRANDS.md`, `~/.config/strands-code/**`, `~/.config/strands-box/**`), and non-interactive active `PolicyConfig` `[[deny]]` rules (failing closed on symlinked `.agent/policy.toml`), both directly and inside `CodeactStint` VM calls.
result: pending

### 4. Strands Box `monty` Exec Grant (`[agent.filesystem].exec`) & Omitted `[tool.python]` (`D-10`, `D-11`)
expected: `resolve_runtime_paths()` and `strands-code box init` discover the canonical non-root `monty` binary realpath (`MONTY_BIN` with control-char rejection, `.venv/bin/monty`, `PATH`, `sysconfig` scripts) into `[agent.filesystem].exec` (and non-root parent dir into `read`), refuse `/` and control-char `MONTY_BIN` overrides, and intentionally omit `[tool.python]` / `python:execute`.
result: pending

### 5. Live `strands-box 0.3.1` (`CLONE_NEWUSER`) Execution of `MontyPythonInterpreter` (`D-10`)
expected: Inside a live Strands Box `CLONE_NEWUSER` container using generated `box.toml` / `policy.dw`, Python executes `MontyPythonInterpreter` (`import math, json; print(json.dumps({"r": math.isqrt(144)}))` -> `{"r": 12}`) cleanly with zero `EACCES`, Dogwood policy refusal, or missing-binary errors.
result: pending

### 6. Documentation (`docs/QUICKSTART.md`), Full Test Suite, Rig Contracts & All 6 CI Gates (`D-11`, `D-24`)
expected: `docs/QUICKSTART.md` (`## Monty Python VM (python_repl & CodeAct)`) accurately documents stdlib/limits/crash salvage/CodeAct callbacks/Box `monty` exec grant and the `[tool.python]` evaluation; `tests/rig/` (`44/44`), full non-integration suite + loopback stub, `@pytest.mark.integration` live Box+Monty probe, restricted-module grep, `uv lock --check`, `ruff format --check`, `ruff check`, `xenon --max-absolute C`, `lint-imports`, and empty `git diff ee42ea2 -- strands_code_agent/` all pass on `HEAD`.
result: pending

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0

## Gaps

None open so far — Test 1 adversarial findings (`monty.py` cumulative `TimeoutError` session reset, `_resolve_monty_binary_path()` `os.X_OK`/control-char validation + non-destructive `_get_shared_pool()` swap, and dynamic truncation cap label) fixed and re-verified on `HEAD`.
