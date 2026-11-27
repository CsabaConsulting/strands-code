# Phase 20: Monty Python VM for `python_repl` & CodeAct - Patterns & Recipes

> Reference implementation patterns for Plans `20-01`..`20-03`. Keep helpers small (`xenon <= C`, ideally `<= B`) and avoid `os.environ`/`os.getenv` in restricted modules.

---

## Pattern 1: `MontyPythonInterpreter` & Pool Management (`strands_code_cli/sandbox/monty.py`)

- Subclasses `PythonInterpreter` from `strands_code_agent.python_environments.base` (keeping `STDOUT_LABEL = "STDOUT:\n"`, `STDERR_LABEL = "STDERR:"`, `get_tool()`).
- Override `get_tool(self)` cleanly so it wraps `super().get_tool()` and attaches `tool._interpreter = self` for deterministic CLI teardown (`D-09`), leaving `strands_code_agent/python_environments/base.py` untouched (`D-24`).
- Constants (`D-04`, `D-05`):
  - `MONTY_MAX_MEMORY_BYTES = 256 * 1024 * 1024`
  - `MONTY_DEFAULT_TIMEOUT_SECONDS = 60`
  - `MONTY_MAX_RECURSION_DEPTH = 200`
  - `MONTY_MAX_STDOUT_BYTES = 4 * 1024 * 1024`
  - `MONTY_DENIED_IMPORTS = frozenset({"os", "pathlib", "subprocess"})`
  - `_STDOUT_TRUNCATED_NOTE = "\n[stdout truncated at 4 MiB]"`
- Pre-execution AST import guard `_check_denied_imports(code: str) -> str | None`:
  - Parse AST on valid Python (`SyntaxError` lets Monty produce its native syntax diagnostic).
  - Inspect `ast.Import`, `ast.ImportFrom`, and `ast.Call` (`__import__("os"...)` / `importlib.import_module(...)`) against `MONTY_DENIED_IMPORTS` (matching top-level module component `name.split(".")[0]`).
  - Returns `f"Import of {mod!r} is not allowed."` when matched so `"not allowed"` assertions hold consistently with fail-closed security (`D-04`).
- Bounded stdout collector `_StdoutCollector`:
  - Accumulates `(stream, text)` / text chunks up to `MONTY_MAX_STDOUT_BYTES` UTF-8 bytes; drops extra bytes after recording `_truncated = True` and appends `_STDOUT_TRUNCATED_NOTE` cleanly so partial pre-crash output can always be salvaged without unbounded host RAM growth (`D-05`, `D-06`).
- Process-wide lazy shared pool (`D-09`):
  - Module-level `_POOL_LOCK = threading.Lock()`, `_SHARED_POOL: Any = None`, `_SHARED_POOL_KEY: str | None = None`, plus `_ACTIVE_SESSIONS: weakref.WeakSet[MontyPythonInterpreter]` (or explicit tracking set under `_POOL_LOCK`).
  - `_get_shared_pool()` lazily imports `pydantic_monty`, resolves `Monty` + binary (using `MONTY_BIN` / `.venv/bin/monty` / `PATH`), caches the pool, and registers `atexit.register(shutdown_shared_pool)` once.
  - `shutdown_shared_pool()`: closes all tracked open sessions and exits/closes `_SHARED_POOL`, clearing globals cleanly (used both at process exit and in unit test cleanup).
- Fail-closed checkout & crash recovery (`D-02`, `D-06`):
  - If `pydantic_monty` fails to import or `pool.checkout(...)` raises `ImportError`/`FileNotFoundError`/`OSError`/`RuntimeError`, set/keep session `None` and return `("", f"Monty Python VM unavailable: {exc}")` — **never** import `smolagents`.
  - When `MontyCrashedError` is raised by `session.feed_run(...)`: salvage `collector.text`, close and clear `self._session = None` so subsequent calls lazily check out a fresh session and replay `state_initialization` (if any), and return `(salvaged, f"Monty VM crashed ({exc}); REPL state was reset.")`.
  - Wrap `additional_functions` cleanly for `external_lookup`: support sync callables like `codeact_read`/`write`/`edit`/`shell` and coerce non-string exceptions safely without taking down the VM.

---

## Pattern 2: Hardened CodeAct Host Callbacks (`strands_code_cli/policy/codeact.py`)

Follow `_validate_stashed_target` (`diff_gate.py:388-420`) and `_read_regular_utf8_nofollow` (`policy_gate.py:400-431`) inside small cohesive helpers:

- `_prepare_codeact_path(cwd: str | Path, raw_path: str, op: str) -> tuple[Path | None, str | None]`:
  1. Resolve `base = Path(cwd)`, check `PolicyConfig.load(repo_path=base / ".agent" / "policy.toml")` (catch `ValueError` -> return `(None, f"Refused {op}: {exc}")` so symlinked or corrupt repo policy fails closed).
  2. Expand `~` (`os.path.expanduser(raw_path)`) before resolution; construct `pre_path` and call `refuse_symlink(pre_path, f"codeact {op} target", max_ancestors=1)` + `refuse_symlink_under_roots(pre_path, [base, base.resolve(), Path("/tmp")], f"codeact {op} target")`.
  3. Call `confined = confine(resolve(raw_path, base), base)` and re-run `refuse_symlink_under_roots(confined, [base, base.resolve(), Path("/tmp")], f"codeact {op} target")`.
  4. Enforce Phase 19.1 path floors (`D-07`):
     - If `op in ("read", "edit")` and (`_is_sensitive_read_path(raw_path, base)` or `_is_sensitive_read_path(str(confined), base)`): return `(None, f"Refused {op}: sensitive path {raw_path!r}")`.
     - If `op in ("write", "edit")` and (`_is_protected_skills_or_config_path(raw_path, base)` or `_is_protected_skills_or_config_path(str(confined), base)`): return `(None, f"Refused {op}: protected path {raw_path!r}")`.
  5. Evaluate active `[[deny]]` rules (`D-08`): call `decide(op, {"path": str(confined)}, policy, cwd=base)`; if `isinstance(verdict, Deny)`, return `(None, verdict.reason)`.
  6. Return `(confined, None)`.
- `_read_codeact_file(target: Path, raw_path: str) -> tuple[str | None, str | None]`:
  - Open with `os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))`, verify `stat.S_ISREG(os.fstat(fd).st_mode)`, read and UTF-8 decode; return `File not found: ...` / `Could not read ...` / `Refused read: not a regular file` on errors.
- `codeact_write` / `codeact_edit`:
  - Check parent symlinks on any missing parent directories cleanly before `target.parent.mkdir(parents=True, exist_ok=True)`, then call `atomic_write_text(target, content, encoding="utf-8", mode=None)`.
- `codeact_shell`:
  - Load `policy = PolicyConfig.load(repo_path=base / ".agent" / "policy.toml")` (fail closed on `ValueError`), normalize command with `shlex.join([str(p) for p in argv])`, evaluate `decide("shell", {"command": cmd_str}, policy, cwd=base)`, and refuse if `isinstance(verdict, Deny)` before spawning subprocess.

---

## Pattern 3: 3-Site CLI Migration & Deterministic Teardown

- **`MontyPythonInterpreter.get_tool()` + helpers (`sandbox/monty.py`):**
  - `close_repl_tool(tool: Any) -> None`: if `interp := getattr(tool, "_interpreter", None)` has callable `.close()`, call it fail-soft.
  - `close_agent_repls(agent: Any) -> None`: close `getattr(getattr(agent, "tool_registry", None), "registry", {}).get("python_repl")` via `close_repl_tool()`.
- **`entry/main.py` (`build_agent`):** replace `SandboxedPythonInterpreter("", authorized_imports=set())` with `MontyPythonInterpreter()`.
- **`policy/codeact.py` (`CodeactStint`):** replace `SandboxedPythonInterpreter` with `MontyPythonInterpreter`, bind `read`/`write`/`edit`/`shell` via `additional_functions`, keep `timeout_seconds=CODEACT_TIMEOUT_SECONDS`, add `close(self) -> None` (`self._interpreter.close()`), and clear `clear_state()` via `reset()`.
- **`loop/btw.py` (`fresh_tools_for_delegate`, `_teardown_btw_agent`):** replace `SandboxedPythonInterpreter` with `MontyPythonInterpreter()` in `fresh_tools_for_delegate`; call `close_agent_repls(agent)` inside `_teardown_btw_agent(agent)`.
- **`entry/subagent.py`:** ensure subagent child REPLs built by `fresh_tools_for_delegate` are closed after child turn completion (`builder` wraps or cleans child tool registry after subagent run completes — verify exact `make_subagent` invocation hook/lifecycle in Wave 2).
- **`loop/core.py` (`_close_loop_session`):** call `close_agent_repls(agent)` and `stint.close()` in `_close_loop_session()` (passing `stint: CodeactStint | None = None` or closing via `_close_loop_session`).

---

## Pattern 4: Strands Box `monty` Exec Grant (`sandbox/box.py`)

- Add `_resolve_monty_binary(venv_bin: Path | None, env_path: str, env_map: Mapping[str, str]) -> Path | None`:
  1. Check validated `env_map.get("MONTY_BIN")` (reject control chars via `_reject_control_chars`, verify `Path(val).is_file()`).
  2. Check `venv_bin / "monty"` when `venv_bin` is present.
  3. Check `importlib.util.find_spec("pydantic_monty_runtime")` binary location if packaged inside site-packages.
  4. Check `shutil.which("monty", path=env_path)`.
  5. Return `Path(os.path.realpath(hit))` when non-root and `is_file()`, else `None`.
- In `resolve_runtime_paths()`: append `monty_bin` to `exec_paths`, and if `monty_bin.parent` is not under `read_paths` and not in `_REFUSED_ROOTS`, append `_valid_nonroot_dir(monty_bin.parent)` to `read_paths`. Expose `"monty_bin": monty_bin` in returned dict.
- In `tests/sandbox/test_box.py`: add offline unit tests for `_resolve_monty_binary` (via `.venv/bin/monty`, `MONTY_BIN`, `PATH`, control-char rejection) and extend the `@pytest.mark.integration` live `strands-box 0.3.1` test to run a real Python snippet through `MontyPythonInterpreter` inside `CLONE_NEWUSER`.
