---
phase: "20"
slug: "monty-python-vm-for-python-repl-codeact"
status: verified
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-27"
verified: "2026-11-27"
---

# Phase 20 — Validation Strategy

> Per-phase Nyquist validation contract for feedback sampling during Phase 20 execution (`SANDBOX-02`).

---

## Test Infrastructure

| Property | Value |
| :--- | :--- |
| **Framework** | `pytest` (installed in `.venv`) via `/home/csaba/.local/bin/uv run pytest` or `.venv/bin/pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `.venv/bin/pytest tests/sandbox/test_monty.py tests/policy/test_codeact.py tests/sandbox/test_box.py -q` |
| **Full suite command** | `TERM=xterm-256color GITHUB_ACTIONS=true .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -rs -q` + standalone `test_stub_server_systemone_decision_routes` |
| **Static / complexity gates** | `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check`, restricted-module check, empty `git diff ee42ea2 -- strands_code_agent/` |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted verification command (`< 30s`).
- **After every plan wave:** Run wave regression suites + `ruff check` + `ruff format --check` + `xenon --max-absolute C` + `lint-imports`.
- **Before `/gsd-verify-work 20`:** All 6 CI workflow checks + `tests/rig/` + full non-integration suite + standalone loopback stub + `uv sync --locked --all-extras` check + live host `strands-box` Monty integration check must pass cleanly (`strands_code_agent/` diff empty).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Decision / Anchor | Correct / Secure Behavior | Test Type | Automated Command | File Exists | Status |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `20-01-T1` | 01 | 1 | `SANDBOX-02` | `D-01`, `D-02`, `D-04`, `D-05`, `D-06`, `D-09` | `pyproject.toml` (`pydantic-monty` core dep) + `uv.lock`, `tests/conftest.py` `MONTY_BIN` scrub, Wave 0 `tests/sandbox/test_monty.py`, and `sandbox/monty.py` (`MontyPythonInterpreter` stateful sessions, pure-Rust stdlib, blocked `os`/`pathlib`/`subprocess`, `256 MiB`/`60s`/`200`/`4 MiB` limits, fail-closed startup, crash salvage) | unit (TDD RED→GREEN, Wave 0 file) | `/home/csaba/.local/bin/uv lock --check && .venv/bin/pytest tests/sandbox/test_monty.py -q && .venv/bin/ruff check strands_code_cli/sandbox/monty.py tests/conftest.py tests/sandbox/test_monty.py && .venv/bin/xenon --max-absolute C strands_code_cli/sandbox/monty.py tests/sandbox/test_monty.py && .venv/bin/lint-imports && git diff ee42ea2 -- strands_code_agent/` | ✅ | ✅ green |
| `20-01-T2` | 01 | 1 | `SANDBOX-02` | `D-04`–`D-06`, `D-09` | Concurrent multi-thread isolated sessions, real infinite-loop timeout `MontyCrashedError` salvage + recovery, `clear_state()`/`close()`/`shutdown_shared_pool()`, `__import__`/`importlib` denials, and `4 MiB` stdout truncation | unit (concurrency + limits) | `.venv/bin/pytest tests/sandbox/test_monty.py -rs -q && .venv/bin/ruff format --check strands_code_cli/sandbox/monty.py tests/sandbox/test_monty.py && .venv/bin/ruff check strands_code_cli/sandbox/monty.py tests/sandbox/test_monty.py && .venv/bin/xenon --max-absolute C strands_code_cli/sandbox/monty.py tests/sandbox/test_monty.py && .venv/bin/lint-imports` | ✅ | ✅ green |
| `20-02-T1` | 02 | 2 | `SANDBOX-02` | `D-03`, `D-09` | Migrate main REPL (`entry/main.py:237`), `CodeactStint` (`policy/codeact.py:306`), and delegate REPL (`loop/btw.py:438`, `entry/subagent.py:73`) to `MontyPythonInterpreter`; zero `SandboxedPythonInterpreter` in `strands_code_cli/`; deterministic teardown in `_close_loop_session`, `_teardown_btw_agent`, `CodeactStint.close`, subagent cleanup | unit + lifecycle (TDD) | `.venv/bin/pytest tests/loop/test_btw.py tests/entry/test_subagent.py tests/entry/test_session_resume.py tests/dispatch/test_cli_entry.py -rs -q && test -z "$(git grep -n SandboxedPythonInterpreter strands_code_cli/)" && .venv/bin/ruff check strands_code_cli tests && .venv/bin/xenon --max-absolute C strands_code_cli tests && .venv/bin/lint-imports` | ✅ | ✅ green |
| `20-02-T2` | 02 | 2 | `SANDBOX-02` | `D-04`, `D-07`, `D-08` | Phase 19.1 symlink/`O_NOFOLLOW`/`atomic_write_text`/sensitive-read/protected-path floor + non-interactive `PolicyConfig` `[[deny]]` enforcement (fail-closed on symlinked repo policy) inside `codeact_read`/`write`/`edit`/`shell`, plus updated `test_codeact.py` | security + unit (TDD) | `.venv/bin/pytest tests/policy/ -rs -q && .venv/bin/ruff format --check strands_code_cli/policy/codeact.py tests/policy/test_codeact.py && .venv/bin/ruff check strands_code_cli/policy/codeact.py tests/policy/test_codeact.py && .venv/bin/xenon --max-absolute C strands_code_cli/policy/codeact.py tests/policy/test_codeact.py && .venv/bin/lint-imports` | ✅ | ✅ green |
| `20-03-T1` | 03 | 3 | `SANDBOX-02` | `D-10`, `D-11` | `_resolve_monty_binary()` in `sandbox/box.py` (`MONTY_BIN`, `.venv/bin/monty`, package path, `PATH`, control-char/root checks) granting `[agent.filesystem].exec` (omitting `[tool.python]`) + live `strands-box 0.3.1` Monty test | unit + Box contract (TDD) | `.venv/bin/pytest tests/sandbox/ -rs -q && .venv/bin/ruff check strands_code_cli/sandbox/box.py tests/sandbox/test_box.py && .venv/bin/xenon --max-absolute C strands_code_cli/sandbox/box.py tests/sandbox/test_box.py && .venv/bin/lint-imports` | ✅ | ✅ green |
| `20-03-T2` | 03 | 3 | `SANDBOX-02` | `D-01`–`D-11` + Gates | Document Monty VM & Strands Box evaluation in `docs/QUICKSTART.md` + complete repo verification: 6 CI gates, restricted-module check, `tests/rig/`, full non-integration suite under CI env, loopback stub, live Box+Monty integration, and empty `strands_code_agent/` diff | docs + full CI + integration | `/home/csaba/.local/bin/uv lock --check && .venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C --max-modules C --max-average C strands_code_cli tests scripts && .venv/bin/lint-imports && test -z "$(git diff ee42ea2 -- strands_code_agent/)" && .venv/bin/pytest tests/rig/ -rs -q && TERM=xterm-256color GITHUB_ACTIONS=true .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -rs -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- `tests/sandbox/test_monty.py` — created TDD-first in Plan `20-01` Task 1 (`20-01-T1`) covering `MontyPythonInterpreter` stateful execution, pure-Rust stdlib, blocked `os`/`pathlib`/`subprocess` imports, `external_lookup` callbacks, `256 MiB`/`60s`/`200`/`4 MiB` resource caps, fail-closed missing-runtime error, `MontyCrashedError` stdout salvage & session recovery, concurrency isolation, and deterministic pool/session teardown.

---

## Manual / Opportunistic Live Verifications

| Behavior | Requirement | Why Host / Network Needed | Test Instructions | Status |
| :--- | :--- | :--- | :--- | :--- |
| `uv sync --locked --all-extras` & loopback stub + live `strands-box 0.3.1` Monty execution inside `CLONE_NEWUSER` | `SANDBOX-02` | PyPI lock/wheel sync + host `box`/`dogwood` Linux `CLONE_NEWUSER` & loopback HTTP outside sandbox | `/home/csaba/.local/bin/uv sync --locked --all-extras` + `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -rs -q` + `.venv/bin/pytest -m integration tests/sandbox/test_box.py -rs -q` | ✅ green (`142 packages`, `1 passed`, `1 passed` live Box+Monty) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits cleanly with TDD / automated verification
- [x] Wave 0 gap identified (`tests/sandbox/test_monty.py`)
- [x] No watch-mode flags
- [x] Fast feedback latency (`< 30s` per targeted verification run)
- [x] `nyquist_compliant: true` audited post-execution

**Approval:** verified (Phase 20 complete: `2011 + 1 = 2012` default tests, `44/44` rig, `1/1` live `strands-box 0.3.1` Monty integration, all 6 CI gates green; ready for `/gsd-verify-work 20`)
