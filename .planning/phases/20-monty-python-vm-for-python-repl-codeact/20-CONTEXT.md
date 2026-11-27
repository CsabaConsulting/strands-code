# Phase 20: Monty Python VM for `python_repl` & CodeAct - Context

**Gathered:** 2026-11-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver `SANDBOX-02` — replace in-process `smolagents` AST execution across all 3 `strands_code_cli/` `python_repl` peer sites (`entry/main.py:237`, `policy/codeact.py:306`, and `loop/btw.py:438` used by `/btw` & `entry/subagent.py:73`) with a crash-isolated, memory-bounded Rust Python VM (`pydantic-monty`) via `strands_code_cli/sandbox/monty.py`, harden CodeAct host callbacks (`read`/`write`/`edit`/`shell`) to Phase 19.1 security parity, wire deterministic worker-pool teardown across reset/exit/delegate lifecycles, and grant `[agent.filesystem].exec` compatibility for `pydantic-monty-runtime` in `strands_code_cli/sandbox/box.py` plus live `strands-box 0.3.1` verification as specified in [ROADMAP.md](file:///home/csaba/repos/AWS/strands-code/.planning/ROADMAP.md#L263-L272) and [REQUIREMENTS.md](file:///home/csaba/repos/AWS/strands-code/.planning/REQUIREMENTS.md#L30).

Out of scope: modifying `strands_code_agent/` (`D-24` — `smolagents` stays in core `[project.dependencies]` for the untouched upstream library package), emitting Strands Box's embedded `[tool.python]` / Dogwood `python:execute` schema (evaluated and documented in `docs/QUICKSTART.md` only), Phase 21 (`LOOP-06`/`TOOL-05`/`REVIEW-01` — `/help`, `@file`/`/file`, `/review`), Phase 22 (`EVAL-01`), and Phase 23 (`STRUCT-02`/`CLEANUP-02`).

</domain>

<decisions>
## Implementation Decisions

### Packaging, Fallback & Peer Scope
- **D-01 (`pyproject.toml` Core Dependency):** Add `pydantic-monty` (no upper pin) to `[project.dependencies]` in `pyproject.toml` (matching `httpx`/`smolagents`; optional extras remain strictly for third-party model-provider SDKs). Keep `smolagents` in `[project.dependencies]` so untouched `strands_code_agent/` (`D-24`) continues to resolve cleanly. — *Reversibility: easy — dependency declaration in `pyproject.toml` + `uv.lock`.*
- **D-02 (Fail-Closed Runtime Posture):** If `pydantic-monty` fails to import or its `monty` worker binary cannot launch inside `MontyPythonInterpreter`, return an explicit `STDERR:` error — never silently downgrading to in-process `smolagents` execution. — *Reversibility: easy — isolated in `sandbox/monty.py` constructor/session checkout.*
- **D-03 (3-Site CLI Peer Symmetry):** Migrate all 3 CLI `python_repl` peer sites onto `MontyPythonInterpreter` together: main tool-turn REPL (`strands_code_cli/entry/main.py:237`), CodeAct stint (`strands_code_cli/policy/codeact.py:306`), and `/btw` + `subagent` delegate REPLs (`strands_code_cli/loop/btw.py:438`, called by `loop/btw.py:507` and `entry/subagent.py:73`). `strands_code_agent/` remains byte-pristine per `D-24`. — *Reversibility: easy — uniform swap behind `PythonInterpreter` ABC.*

### Stdlib Surface, Resource Caps & Crash Recovery
- **D-04 (Pure-Computation Stdlib + Explicit OS/Subprocess Denial):** Allow Monty's safe pure-computation Rust stdlib (`math`, `json`, `re`, `collections`, `itertools`, `datetime`, `base64`, `dataclasses`, `random`, `typing`, etc.) across all 3 CLI sites with `os=None` (zero host FS, env, or network access inside the VM), while explicitly rejecting `os`, `pathlib`, and `subprocess` imports fail-closed before/during execution so `import os` and `import subprocess` return clear `"not allowed"` / blocked errors. — *Reversibility: easy — module import gate in `sandbox/monty.py`.*
- **D-05 (`ResourceLimits` & Stdout Bounds):** Configure default bounds on `MontyPythonInterpreter`: `max_memory = 256 * 1024 * 1024` (256 MiB), `max_feed_duration_secs = 60` (matching existing `CODEACT_TIMEOUT_SECONDS = 60`), `max_recursion_depth = 200`, and a `4 MiB` captured stdout cap via `print_callback` (truncating cleanly with an explicit note when exceeded). — *Reversibility: easy — module-level constants / kwargs on `MontyPythonInterpreter`.*
- **D-06 (`MontyCrashedError` Recovery & Stdout Salvage):** On `MontyCrashedError` (OOM, hard timeout, or worker abort), salvage any partial `print()` stdout emitted before the crash, discard the dead session and transparently replace it on a fresh worker, and return a clear `STDERR:` message reporting the crash/limit hit plus an explicit notice that REPL state was reset. — *Reversibility: easy — localized in `MontyPythonInterpreter.execute_code()`.*

### CodeAct Host Callback Hardening
- **D-07 (Phase 19.1 Path & Symlink Parity in `codeact_read`/`write`/`edit`):** Backport Phase 19.1's security floor into `codeact_read`, `codeact_write`, and `codeact_edit` (`strands_code_cli/policy/codeact.py`): refuse target and ancestor symlinks (`platform_io.refuse_symlink_under_roots` + nofollow / `atomic_write_text`), refuse dynamic reads of sensitive files (`_is_sensitive_read_path`: `.env*`, `~/.ssh/*`, `~/.aws/*`, `*.pem`/`*.key`), and refuse dynamic writes/edits to protected paths (`_is_protected_skills_or_config_path`: `.agent/**`, `.git/**`, `STRANDS.md`, `~/.config/strands-code/**`, `~/.cache/strands-code/**`, `~/.config/strands-box/**`, `~/.local/share/strands-box/**`) — returning refusal strings, never raising exceptions into the VM. — *Reversibility: moderate — security boundary inside CodeAct host callbacks.*
- **D-08 (Active `PolicyConfig` `[[deny]]` Enforcement in CodeAct Callbacks):** Evaluate active `PolicyConfig` `[[deny]]` rules inside `codeact_read`, `codeact_write`, `codeact_edit`, and `codeact_shell` host callbacks (honoring home-vs-repo precedence with fail-closed symlinked repo policy, returning refusal strings and never prompting mid-VM), closing dynamic runtime bypasses of file/shell `[[deny]]` rules from inside an approved CodeAct block. — *Reversibility: moderate — non-interactive deny evaluation inside CodeAct host callbacks.*

### Worker Pool Ownership & Teardown
- **D-09 (Process-Wide Lazy Shared `Monty()` Pool + Deterministic Teardown):** Use a thread-safe process-wide lazy shared `Monty()` worker pool in `strands_code_cli/sandbox/monty.py` with per-interpreter isolated checked-out sessions (each `MontyPythonInterpreter` owns an independent session, never sharing VM state across main REPL, `CodeactStint`, `/btw`, or `subagent`). Close sessions deterministically on `clear_state()`, `MontyPythonInterpreter.close()`, `CodeactStint.close()`, `_close_loop_session()` (`strands_code_cli/loop/core.py:2582`), and delegate teardown (`_teardown_btw_agent` / subagent exit), and shut down the shared pool cleanly via `atexit` (plus a test helper for clean reset). — *Reversibility: easy — lifecycle hooks on interpreter, stint, loop exit, and delegate teardown.*

### Strands Box Runtime Grants & Embedded `[tool.python]` Scope
- **D-10 (`box.py` `pydantic-monty-runtime` Exec Grant & Live Box+Monty Integration):** Update `resolve_runtime_paths()` in `strands_code_cli/sandbox/box.py` to discover the `pydantic-monty-runtime` `monty` binary realpath (checking `venv_bin / "monty"`, `pydantic_monty_runtime` package location, and `PATH`) and include it in `[agent.filesystem].exec` (plus its parent dir in `read` if outside `.venv`). Extend the `@pytest.mark.integration` live `strands-box 0.3.1` test in `tests/sandbox/test_box.py` to verify real `MontyPythonInterpreter` execution inside `CLONE_NEWUSER`. — *Reversibility: easy — runtime path discovery in `box.py`.*
- **D-11 (Embedded `[tool.python]` Omitted & Evaluated in Docs):** Keep Strands Box's embedded `[tool.python]` / Dogwood `python:execute` rules omitted from generated `box.toml`/`policy.dw` — `strands-code`'s `python_repl` runs `pydantic-monty` directly inside Box (identical behavior boxed & unboxed, while callbacks already run inside Box FS containment and `codeact_shell` routes via `sh -c` to Dogwood `shell:spawn`). Document the Strands Box embedded Monty evaluation and architecture clearly in `docs/QUICKSTART.md`. — *Reversibility: easy — documented evaluation; can add `--allow-box-python` in a future phase if a Box MCP bridge lands.*

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/ROADMAP.md` — Phase 20 (`SANDBOX-02`) goal, scope & success criteria
- `.planning/REQUIREMENTS.md` — `SANDBOX-02`
- `.planning/INVARIANTS.md` — `D-24` (`strands_code_agent/` immutability), Horizontal Backport Rule & static CI invariants
- `strands_code_agent/python_environments/base.py` — `PythonInterpreter` ABC, `STDOUT_LABEL`, `STDERR_LABEL`, `get_tool()`
- `strands_code_cli/entry/main.py` — main tool-turn REPL construction (`build_agent`, line 237)
- `strands_code_cli/policy/codeact.py` — `CodeactStint`, `codeact_read`, `codeact_write`, `codeact_edit`, `codeact_shell`, `CODEACT_TIMEOUT_SECONDS`
- `strands_code_cli/loop/btw.py` & `strands_code_cli/entry/subagent.py` — `fresh_tools_for_delegate()`, `_teardown_btw_agent()`, `build_cli_subagent()`
- `strands_code_cli/loop/core.py` — `stint` creation, `stint.reset()`, and `_close_loop_session()` teardown (line 2582)
- `strands_code_cli/policy/core.py` & `strands_code_cli/platform_io.py` — `PolicyConfig`, `decide`, `_is_sensitive_read_path`, `_is_protected_skills_or_config_path`, `refuse_symlink_under_roots`, `atomic_write_text`
- `strands_code_cli/sandbox/box.py` — `resolve_runtime_paths()`, `render_box_toml()`, `render_policy_dw()`
- `tests/policy/test_codeact.py`, `tests/sandbox/test_box.py`, `pyproject.toml`, `docs/QUICKSTART.md`

</canonical_refs>

<deferred>
## Deferred Ideas

- Opt-in `--allow-box-python` (`[tool.python]` + Dogwood `python:execute` rules) if a future Strands Box MCP bridge integrates natively with Strands Harness tools.
- Persistent cross-process Monty snapshot (`session.dump()`) serialization into session files (REPL state remains session/stint-scoped in memory).

</deferred>
