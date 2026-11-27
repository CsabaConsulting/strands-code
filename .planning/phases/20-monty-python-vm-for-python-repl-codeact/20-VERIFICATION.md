---
phase: "20"
name: "Monty Python VM for python_repl & CodeAct"
status: passed
verified: "2026-11-27"
requirement: SANDBOX-02
score: 11/11
---

# Phase 20 Verification (`SANDBOX-02`)

**Result:** **PASS (`11/11` locked decisions `D-01`–`D-11`, `9/9` threats `T-20-01`–`T-20-09`, `6/6` CI gates)**

## Locked Decision Verification (`D-01`–`D-11`)

| Decision | Requirement | Implementation & Evidence | Status |
| :--- | :--- | :--- | :--- |
| `D-01` | Core `pydantic-monty` dependency (no upper pin); keep `smolagents` only for `strands_code_agent/` | `pyproject.toml`, `uv.lock`, `tests/conftest.py` (`MONTY_BIN` scrub); `uv lock --check` (`Resolved 142 packages`) | ✅ PASS |
| `D-02` | Fail closed when `pydantic-monty` or `monty` worker binary is missing/unlaunchable | `strands_code_cli/sandbox/monty.py` `_ensure_session_unlocked()` returns descriptive `STDERR` without fallback; zero `SandboxedPythonInterpreter` in `strands_code_cli/*.py` | ✅ PASS |
| `D-03` | Migrate all 3 CLI `python_repl` peer sites uniformly | `strands_code_cli/entry/main.py`, `strands_code_cli/policy/codeact.py` (`CodeactStint`), `strands_code_cli/loop/btw.py` (`fresh_tools_for_delegate` used by `/btw` & `entry/subagent.py`) | ✅ PASS |
| `D-04` | Pure-computation Rust stdlib (`os=None`), explicitly blocking `os`, `pathlib`, `subprocess`, `__import__`, `importlib` | `strands_code_cli/sandbox/monty.py` AST `_check_denied_imports()` + `os=None` runtime + `tests/sandbox/test_monty.py` + `tests/policy/test_codeact.py` | ✅ PASS |
| `D-05` | Resource caps (`256 MiB`, `60s`, recursion `200`, `4 MiB` stdout cap) | `MONTY_MAX_MEMORY_BYTES`, `MONTY_MAX_DURATION_SECS`, `MONTY_MAX_RECURSION_DEPTH`, `MONTY_MAX_STDOUT_BYTES` (`_StdoutCollector`) in `strands_code_cli/sandbox/monty.py` | ✅ PASS |
| `D-06` | `MontyCrashedError` salvages pre-crash stdout, replaces dead worker session, and notes state reset | `MontyPythonInterpreter.execute_code()` catches `MontyCrashedError` and resets `_session`; tested live with infinite loop under crash pool in `tests/sandbox/test_monty.py` | ✅ PASS |
| `D-07` | Phase 19.1 symlink / `O_NOFOLLOW | O_NONBLOCK` / `atomic_write_text` / sensitive-read / protected-path floor in CodeAct callbacks | `strands_code_cli/policy/codeact.py` `_prepare_codeact_path()`, `_read_regular_file_utf8()`, `codeact_read`, `codeact_write`, `codeact_edit` + `test_phase191_symlink_fifo_sensitive_protected_and_policy_deny_floor` | ✅ PASS |
| `D-08` | Non-interactive active `PolicyConfig` `[[deny]]` enforcement (fail-closed on symlinked repo policy) | `_load_codeact_policy()` + `codeact_read`/`write`/`edit`/`shell` in `strands_code_cli/policy/codeact.py` + `tests/policy/test_codeact.py` | ✅ PASS |
| `D-09` | Lazy shared `Monty()` pool with per-interpreter sessions & deterministic teardown | `_get_shared_pool`, `shutdown_shared_pool`, `close_repl_tool`, `close_agent_repls`, `atexit`, `_close_loop_session`, `_teardown_btw_agent`, `CodeactStint.close()`, `_wrap_subagent_cleanup` | ✅ PASS |
| `D-10` | Discover canonical `monty` binary realpath and grant `[agent.filesystem].exec` in Strands Box | `_valid_monty_candidate()` / `_resolve_monty_binary()` / `resolve_runtime_paths()` in `strands_code_cli/sandbox/box.py` + `TestMontyBinaryBoxGrant` + live `strands-box 0.3.1` `_assert_box_run_monty()` | ✅ PASS |
| `D-11` | Keep Strands Box `[tool.python]` / `python:execute` omitted and document architecture & evaluation | `render_box_toml()` / `render_policy_dw()` omit `[tool.python]` / `python:execute`; `docs/QUICKSTART.md` (`## Monty Python VM (python_repl & CodeAct)`) | ✅ PASS |

## Threat Mitigation Verification (`T-20-01`–`T-20-09`)

| Threat | Mitigation & Post-Edit Proof | Status |
| :--- | :--- | :--- |
| `T-20-01` | In-process `smolagents` host-memory tampering eliminated across `entry/main.py`, `CodeactStint`, `/btw`, and `subagent`; fail closed without `smolagents` fallback (`tests/sandbox/test_monty.py`) | ✅ CLOSED |
| `T-20-02` | Host filesystem/process access blocked inside VM (`_check_denied_imports` + `os=None`) for `os`, `pathlib`, `subprocess`, `__import__`, `importlib` (`tests/sandbox/test_monty.py`, `tests/policy/test_codeact.py`) | ✅ CLOSED |
| `T-20-03` | Memory/CPU/recursion/stdout exhaustion bounded by `256 MiB`, `60s`, `200`, `4 MiB` (`tests/sandbox/test_monty.py`) | ✅ CLOSED |
| `T-20-04` | `MontyCrashedError` salvages pre-crash `print()` stdout, discards crashed session, and emits reset notice without crashing CLI (`tests/sandbox/test_monty.py`) | ✅ CLOSED |
| `T-20-05` | Symlink escape, FIFO block, `.env*`/`.ssh/*`/`.aws/*` reads, and protected writes blocked in `codeact_read`/`write`/`edit` (`test_phase191_symlink_fifo_sensitive_protected_and_policy_deny_floor`) | ✅ CLOSED |
| `T-20-06` | Active `[[deny]]` rules and symlinked `.agent/policy.toml` fail-closed enforcement verified directly and through `CodeactStint` (`test_phase191_symlink_fifo_sensitive_protected_and_policy_deny_floor`) | ✅ CLOSED |
| `T-20-07` | Cross-turn/cross-agent worker leakage prevented via `_close_loop_session`, `_teardown_btw_agent`, `_wrap_subagent_cleanup`, `CodeactStint.close()`, and `atexit` (`tests/loop/`, `tests/entry/test_subagent.py`) | ✅ CLOSED |
| `T-20-08` | `_resolve_monty_binary()` validates non-control-char `MONTY_BIN` / canonical `realpath` / non-root parent via `_valid_nonroot_dir()` (`TestMontyBinaryBoxGrant`) | ✅ CLOSED |
| `T-20-09` | `[tool.python]` omitted & documented in `docs/QUICKSTART.md`; real `MontyPythonInterpreter` verified inside live `strands-box 0.3.1` (`_assert_box_run_monty`) | ✅ CLOSED |

## Post-Final-Edit Verification Ledger

- **Restricted-module grep (`entry/main.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, `model/model_switch.py`, `cost/cost_context.py`):** zero `os.environ` / `os.getenv`, zero unnegated `budget|enforce|quota|halt`.
- **Upstream boundary (`D-24`):** `git diff ee42ea2 -- strands_code_agent/` is empty.
- **Static CI gates:**
  - `/home/csaba/.local/bin/uv lock --check` -> `Resolved 142 packages in 2ms`
  - `.venv/bin/ruff format --check strands_code_cli tests scripts` -> `137 files already formatted`
  - `.venv/bin/ruff check strands_code_cli tests scripts` -> `All checks passed!`
  - `.venv/bin/xenon --max-absolute C --max-modules C --max-average C strands_code_cli tests scripts` -> passed (`CC <= 20`)
  - `.venv/bin/lint-imports` -> `Analyzed 47 files, 147 dependencies. Contracts: 1 kept, 0 broken.`
- **Test suites (executed after final code/test edit):**
  - `.venv/bin/pytest tests/sandbox/ -rs -q` -> `48 passed, 1 deselected in 2.52s`
  - `.venv/bin/pytest -m integration tests/sandbox/test_box.py -rs -q` (`BypassSandbox: true`, live `strands-box 0.3.1`) -> `1 passed, 30 deselected in 10.50s` (`{"r": 12}` verified inside `CLONE_NEWUSER`)
  - `.venv/bin/pytest tests/rig/ -rs -q` -> `44 passed in 0.13s`
  - `TERM=xterm-256color GITHUB_ACTIONS=true .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -rs -q` -> `2011 passed, 16 deselected in 71.02s`
  - `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -rs -q` (`BypassSandbox: true`) -> `1 passed, 202 deselected in 2.35s`
