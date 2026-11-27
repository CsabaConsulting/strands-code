---
status: complete
phase: 20-monty-python-vm-for-python-repl-codeact
source: [20-01-SUMMARY.md, 20-02-SUMMARY.md, 20-03-SUMMARY.md, 20-VERIFICATION.md]
started: 2026-11-27T21:44:00Z
updated: 2026-11-27T22:41:00Z
---

# Phase 20 User Acceptance Testing (`SANDBOX-02`)

## Current Test

[testing complete]

## Tests

### 1. Monty Python VM Core (`MontyPythonInterpreter`, Pure-Rust Stdlib, Import Blocking, Limits & Crash/Timeout Recovery) (`D-01`, `D-02`, `D-04`–`D-06`, `D-09`)
expected: `MontyPythonInterpreter` executes Python inside an isolated `pydantic-monty` Rust worker with cross-turn variable persistence, pure-computation stdlib (`math`, `json`, `re`, `collections`, `itertools`, `datetime`, `base64`, `dataclasses`, `typing`) + `ascii` builtin, fail-closed startup when missing/unlaunchable (zero `smolagents` fallback), AST + `os=None` blocking of `os`/`pathlib`/`subprocess`/`__import__`/`importlib`, `256 MiB` memory / `60s` wall / `200` recursion / `4 MiB` stdout caps, and salvage + recovery without leaving the session wedged after crash or limit exhaustion.
result: pass
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
result: pass
evidence: |
  - Functional probe on `HEAD` `ea35d49` (`TEST2_BASE_PROBE_OK` + `ZERO_SMOLAGENTS_CLI`):
    - Zero `SandboxedPythonInterpreter` references across `strands_code_cli/**/*.py`.
    - `main` REPL, `fresh_tools_for_delegate` (`/btw` & `subagent`), and `CodeactStint` all instantiate isolated `MontyPythonInterpreter` instances with independent variable namespaces (`main` vs `delegate` vs `codeact`).
    - `stint.reset()`, `stint.close()`, `close_agent_repls()` (`_python_repl_tool`, `_delegate_repl_tools`, and `registry["python_repl"]`) release sessions cleanly (`_session is None`).
  - Adversarial pre-check gap found on `ea35d49` & fixed in `entry/subagent.py`, `sandbox/monty.py`, `entry/main.py`, `loop/btw.py`, and `tests/entry/test_subagent.py`:
    - `[Code/Lifecycle Gap]` Attached `_close_children()` in `_wrap_subagent_cleanup()`, wired `close_agent_repls()` to invoke `_close_tool_children()` across `registry["subagent"]`, `_subagent_tool`, and `_delegate_repl_tools`, and recorded `_subagent_tool` / `"subagent"` handle in `entry/main.py` and `loop/btw.py` so unresumed pending `subagent` children close deterministically on session or `/btw` teardown.
  - Re-verified on fix `HEAD` (`Gaps found: None`): `PARENT_CLOSED: True`, `PENDING_CHILD_CLOSED: True`, `262 passed, 1 deselected` (`tests/entry/`, `tests/loop/test_btw.py`, `tests/loop/test_loop_cancel.py`, `tests/sandbox/test_monty.py`, `tests/policy/test_codeact.py`), and all 6 CI gates green.

### 3. Hardened CodeAct Host Callbacks (`read`/`write`/`edit`/`shell`) & `PolicyConfig` `[[deny]]` Enforcement (`D-07`, `D-08`)
expected: CodeAct host callbacks enforce Phase 19.1 symlink refusal (leaf & intermediate ancestors), `O_NOFOLLOW | O_NONBLOCK` regular-file UTF-8 reads (blocking FIFOs/devices), `atomic_write_text`, sensitive-read refusal (`.env*`, `.ssh/*`, `.aws/*`), protected-path blocks (`.agent/**`, `.git/**`, `STRANDS.md`, `~/.config/strands-code/**`, `~/.config/strands-box/**`), and non-interactive active `PolicyConfig` `[[deny]]` rules (failing closed on symlinked `.agent/policy.toml`), both directly and inside `CodeactStint` VM calls.
result: pass
evidence: |
  - Functional probe on `HEAD` `12d9a28`:
    - Blocked 3-level intermediate symlink `a/b/c/...`, all 12 sensitive/protected write paths (`.env`, `.env.local`, `.envrc`, `.ssh/authorized_keys`, `.aws/credentials`, `.git/config`, `.git/hooks/pre-commit`, `STRANDS.md`, `.agent/policy.toml`, `.agent/routing.yaml`, `.agent/MEMORY.md`, `.agent/skills/evil/SKILL.md`), directory/binary/FIFO/`\x00` targets, non-string VM callback args (`int` / string shell), relative glob/wildcard `[[deny]]` rules on `read`/`write`/`edit`/`shell` (`rm`, `git push`), and `STRANDS_BOX=1` metacharacter quoting (`$(touch pwned); echo hi`).
  - Adversarial pre-check gaps found on `12d9a28` & fixed in `strands_code_cli/policy/codeact.py` + `tests/policy/test_codeact.py`:
    1. `[Code/Security Gap]` Added `_raw_walk_start()` + `_refuse_raw_symlink_traversal()` walking un-collapsed path segments so `a/../outside/...` symlink escapes are blocked before lexical `..` normalization.
    2. `[Code/Bug Gap]` Anchored raw walk and `confine()` against `real_base = realpath(cwd)` so legitimate files inside a symlinked workspace (`ws_link -> ws`) succeed cleanly without false-positive parent symlink refusals.
    3. `[Code/Security Gap]` Added `_codeact_shell_deny_candidates()` in `codeact_shell()` checking full argv, basename head (`/bin/rm` -> `rm`), and `env` wrapper targets (`/usr/bin/env FOO=1 /bin/rm`) against active `PolicyConfig` `[[deny]]` rules.
  - Re-verified on fix `HEAD` (`Gaps found: None`): `359 passed` (`tests/policy/` + `tests/sandbox/test_monty.py`), all 6 CI gates green, plus live re-probe (`1_SYMLINKED_CWD_READ: 'hello\n'`, `2_DOTDOT_SYM_READ: Refusing symlink`, `5_DENY_SHELL_ABSPATH_RM / ENV_RM / SH_RM / GIT_PUSH: Denied by policy`).

### 4. Strands Box `monty` Exec Grant (`[agent.filesystem].exec`) & Omitted `[tool.python]` (`D-10`, `D-11`)
expected: `resolve_runtime_paths()` and `strands-code box init` discover the canonical non-root `monty` binary realpath (`MONTY_BIN` with control-char rejection, `.venv/bin/monty`, `PATH`, `sysconfig` scripts) into `[agent.filesystem].exec` (and non-root parent dir into `read`), refuse `/` and control-char `MONTY_BIN` overrides, and intentionally omit `[tool.python]` / `python:execute`.
result: pass
evidence: |
  - Functional probe on `HEAD` `533e587`:
    - `init_box_config()` resolves custom `MONTY_BIN` into `[agent.filesystem].exec` and parent dir into `[agent.filesystem].read`, refuses symlinked `MONTY_BIN` pointing into `/tmp` (`monty_bin is None`, `/tmp` excluded from `read`), rejects `\n` control chars in `MONTY_BIN`, and intentionally omits `[tool.python]` and `python:execute`.
  - Adversarial pre-check gaps found on `533e587` & fixed in `strands_code_cli/sandbox/box.py`, `strands_code_cli/sandbox/monty.py`, `tests/sandbox/test_box.py`, and `tests/sandbox/test_monty.py`:
    1. `[Code/Runtime Gap]` Forwarded `MONTY_BIN` into `[agent.env]` in `_render_agent_env()` when `env["MONTY_BIN"]` resolved cleanly to `runtime["monty_bin"]` (omitted when unset).
    2. `[Code/Security Gap]` Added `os.access(real, os.X_OK)` in `_valid_monty_candidate()` so non-executable `0o644` files are excluded from `[agent.filesystem].exec`.
    3. `[Code/Security Gap]` Added `unicodedata.category(ch) in ("Cc", "Cf")` to `_reject_control_chars()` (`box.py`) and `_resolve_monty_binary_path()` (`monty.py`), blocking C1 (`\x9b`) and Bidi (`\u202e`) control/format characters.
  - Re-verified on fix `HEAD` (`Gaps found: None`): `48 passed, 1 deselected` (`tests/sandbox/`), all 6 CI gates green, plus live re-probe (`1_AGENT_ENV_HAS_MONTY_BIN: True`, `2_NONEXEC_ACCEPTED: None`, `4_LF/C1/BIDI_REJECTED`).

### 5. Live `strands-box 0.3.1` (`CLONE_NEWUSER`) Execution of `MontyPythonInterpreter` (`D-10`)
expected: Inside a live Strands Box `CLONE_NEWUSER` container using generated `box.toml` / `policy.dw`, Python executes `MontyPythonInterpreter` (`import math, json; print(json.dumps({"r": math.isqrt(144)}))` -> `{"r": 12}`) cleanly with zero `EACCES`, Dogwood policy refusal, or missing-binary errors.
result: pass
evidence: |
  - Functional & live container probe on `HEAD` `80ab751` (`Gaps found: None`):
    - `.venv/bin/pytest -m integration tests/sandbox/test_box.py -rs -q` (`BypassSandbox: true`, live `strands-box 0.3.1`): `1 passed, 30 deselected in 9.58s` (ran real `MontyPythonInterpreter` inside `CLONE_NEWUSER` returning `{"r": 12}`).
    - Live adversarial `CLONE_NEWUSER` probe on `HEAD` `80ab751` with custom external `MONTY_BIN` copied outside `.venv`/`PATH` (`STRANDS_BOX=1`, `MONTY_BIN=<ext>/monty-custom`): `RC: 0`; `CodeactStint` computed `{"r": 12}`, blocked `import os`, refused `read('.env')` (`Refused read: sensitive path '.env'`), refused `read('/etc/passwd')` (outside allowed roots), read `pyproject.toml` (`3712` bytes), and tore down cleanly.

### 6. Documentation (`docs/QUICKSTART.md`), Full Test Suite, Rig Contracts & All 6 CI Gates (`D-11`, `D-24`)
expected: `docs/QUICKSTART.md` (`## Monty Python VM (python_repl & CodeAct)`) accurately documents stdlib/limits/crash salvage/CodeAct callbacks/Box `monty` exec grant and the `[tool.python]` evaluation; `tests/rig/` (`44/44`), full non-integration suite + loopback stub, `@pytest.mark.integration` live Box+Monty probe, restricted-module grep, `uv lock --check`, `ruff format --check`, `ruff check`, `xenon --max-absolute C`, `lint-imports`, and empty `git diff ee42ea2 -- strands_code_agent/` all pass on `HEAD`.
result: pass
evidence: |
  - Functional & full CI verification on `HEAD` `80ab751` (`Gaps found: None`):
    - `docs/QUICKSTART.md` (`## Monty Python VM (python_repl & CodeAct)`, lines 352–386) matches shipped 3-site pool, pure-Rust stdlib + denied imports, `256 MiB`/`60s`/`200`/`4 MiB` limits, crash/timeout salvage + teardown, hardened CodeAct callbacks, Box `monty` exec grant, and omitted `[tool.python]` evaluation.
    - Restricted-module grep clean; zero `SandboxedPythonInterpreter` in `strands_code_cli/**/*.py`.
    - Static CI gates: `uv lock --check` (`142 packages`), `ruff format --check` (`137 files`), `ruff check`, `xenon --max-absolute C --max-modules C --max-average C`, `lint-imports` (`47 files, 147 deps, 1 kept / 0 broken`), and empty `git diff ee42ea2 -- strands_code_agent/`.
    - `tests/rig/`: `44 passed in 0.23s`.
    - Full non-integration suite (`TERM=xterm-256color GITHUB_ACTIONS=true`): `2012 passed, 16 deselected in 73.29s`.
    - Standalone loopback stub (`test_stub_server_systemone_decision_routes`, `BypassSandbox: true`): `1 passed, 202 deselected in 2.25s` (`2013` total default tests).
    - Live `strands-box 0.3.1` integration (`tests/sandbox/test_box.py -m integration`, `BypassSandbox: true`): `1 passed, 30 deselected in 9.58s`.

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

None open — all 10 adversarial pre-check gaps discovered across Tests 1–4 were fixed and re-verified on `HEAD` `80ab751` (commits `ea35d49`, `12d9a28`, `533e587`, `80ab751`).
