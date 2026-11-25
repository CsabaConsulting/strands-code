---
phase: 19-strands-box-linux-sandbox-floor-dogwood-policy
plan: "02"
completed: 2026-11-25
requirements:
  - SANDBOX-01
files_modified:
  - strands_code_cli/policy/codeact.py
  - strands_code_cli/policy/core.py
  - strands_code_cli/dispatch/core.py
  - strands_code_cli/sandbox/box.py
  - strands_code_cli/entry/main.py
  - tests/policy/test_codeact.py
  - tests/policy/test_policy.py
  - tests/sandbox/test_box_cli.py
---

# Plan 19-02 Summary: `strands-code box` CLI, `codeact_shell` Box Alignment & Protected-Path Downgrade

## Implemented
- **[codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py):** Added `_codeact_shell_cmd()` inside `codeact_shell()` so `STRANDS_BOX=1` routes argv invocations through `["sh", "-c", shlex.join(cmd)]` (preserves metacharacter quoting and feeds Dogwood's shell temporal log) while keeping unboxed execution as direct argv (`subprocess.run(shell=False)`). Uses a lazy import of `is_in_strands_box()` to keep `entry.provider_config -> policy.codeact -> sandbox.box` cycle-free.
- **[core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/core.py):** Added `platformdirs.user_config_dir("strands-box")` to `protected_dirs` in `_is_protected_skills_or_config_path()` so writes targeting `~/.config/strands-box/**` (including workspace symlink escapes) downgrade `Allow` (`*`) rules to `Prompt`.
- **[core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py):** Updated `_policy_message()` (`verb in ("", "show")`) to append `"Sandbox: Strands Box active (STRANDS_BOX=1)"` via `is_in_strands_box()` without adding `os.environ` reads or forbidden vocabulary.
- **[box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py) & [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py):** Added `build_box_app()` / `box_app` (`strands-code box init|doctor|run`), registered `app.add_typer(box_app, name="box", ...)` on the root Typer app, and exited `_root()` early when `ctx.invoked_subcommand is not None` so subcommands never trigger REPL `_preflight_credentials()` while preserving bare `strands-code` and `--codeact`/`--model`/`--session-id`.
- **Tests:** Expanded [test_codeact.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_codeact.py) and [test_policy.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_policy.py), and created [test_box_cli.py](file:///home/csaba/repos/AWS/strands-code/tests/sandbox/test_box_cli.py).

## Verification
- `uv run ruff format --check strands_code_cli tests scripts`: `128 files already formatted`.
- `uv run ruff check strands_code_cli tests scripts`: `All checks passed!`.
- `uv run xenon --max-absolute C strands_code_cli tests scripts`: passed.
- `uv run lint-imports`: `Contracts: 1 kept, 0 broken` (`43 files, 97 dependencies`).
- `uv run pytest tests/sandbox/ tests/entry/ tests/dispatch/ tests/policy/ tests/cost/test_cost_context.py -q`: `541 passed` (`6` upstream Strands context-window warnings).
