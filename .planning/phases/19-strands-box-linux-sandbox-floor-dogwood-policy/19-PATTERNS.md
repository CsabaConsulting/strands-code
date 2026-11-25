# Phase 19 Codebase Patterns & Extension Seams

**Created:** 2026-11-25
**Purpose:** Concrete module contracts, `box.toml`/`policy.dw` schemas, Typer/CodeAct/Policy/Dispatch integration seams, and CI ceilings across Plans `19-01`, `19-02`, and `19-03`.

---

## 1. Sandbox Module (`strands_code_cli/sandbox/box.py`)

New cohesive feature package `strands_code_cli/sandbox/` (`__init__.py` + `box.py`), zero imports from `strands_code_cli.entry.main` (`lint-imports` stays `1 kept, 0 broken`), every function `CC <= 16`.

- **Storage, Repo Slug & Constants (`D-02`, `D-03`):**
  - `_BOX_APP_NAME = "strands-box"`, `_REPOS_DIR = "repos"`
  - Default host-only config dir: `Path(platformdirs.user_config_dir(_BOX_APP_NAME)) / "repos" / repo_id` -> `box.toml` + `policy.dw` (`0o700` dirs, `0o600` files, symlink-refused atomic `tempfile.mkstemp` + `os.replace`).
  - Default host-only runtime state dir: `Path(platformdirs.user_data_dir(_BOX_APP_NAME)) / "repos" / repo_id` (`box_dir`, invisible inside sandbox).
  - `repo_config_id(repo_root: Path) -> str`: `f"{slug}-{digest8}"` where `slug` sanitizes `repo_root.resolve().name.lower()` (`^[a-z0-9-]+$`, max 32 chars, fallback `"repo"`) and `digest8 = hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:8]`.
  - `_sanitize_toml_str(value: str) -> str`: rejects `\x00`..`\x1f` and `\x7f` control chars (`ValueError`), returns TOML-safe double-quoted literal via `json.dumps(value)`.
  - `is_in_strands_box() -> bool`: checks `os.environ.get("STRANDS_BOX", "").strip().lower() in {"1", "true", "yes"}` (mirrors `entry/first_run.py:_is_truthy`).

- **Dataclasses (`D-01`–`D-07`):**
  - `EgressProfile(name: str, hosts: tuple[str, ...], destinations: tuple[str, ...], secret_ref: str | None, placement: str | None, header: str | None, prefix: str | None)` (plus separate unauthenticated destinations when applicable, e.g. `codeload.github.com` / `objects.githubusercontent.com` in `github_skills`).
  - `BoxInitResult(config_dir: Path, box_toml: Path, policy_dw: Path, providers: tuple[str, ...], warnings: tuple[str, ...], self_tamper_risk: bool)`
  - `BoxDoctorCheck(name: str, ok: bool, detail: str, remediation: str | None = None)`
  - `BoxDoctorReport(checks: tuple[BoxDoctorCheck, ...], ok: bool)`

- **Provider Detection & Egress Registry (`D-04`):**
  - `CORE_PROVIDERS = ("bedrock", "google", "anthropic", "openai", "meta", "openrouter", "typesafe")`
  - `OPTIONAL_PROFILES = ("decisions_api", "github_skills")`
  - `detect_active_providers(repo_root: Path, *, allow_decisions_api: bool = False, allow_github_skills: bool = False) -> list[str]`:
    - Inspects `ProviderConfig.load().model` (and `base_url` hint), `routing.core.load_strategy()` (`engine.order` / `engine.primary` / `engine.llm_model` / `candidates`), and non-empty host env keys (`GOOGLE_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MODEL_API_KEY`, `META_API_KEY`, `OPENROUTER_API_KEY`, `TYPESAFE_API_KEY`, `AWS_BEARER_TOKEN_BEDROCK` / `AWS_ACCESS_KEY_ID` / `AWS_PROFILE`).
    - Maps `"litellm"` routes with `"openrouter"` -> `"openrouter"`.
    - Keeps `"decisions_api"` and `"github_skills"` strictly opt-in via CLI flags (`--allow-decisions-api`, `--allow-github-skills`).
    - Falls back to `["bedrock"]` when no providers are detected cleanly.

- **`uv` / `.venv` Realpath Resolution & Renderers (`D-03`–`D-05`):**
  - `resolve_runtime_paths(repo_root: Path) -> dict[str, list[Path]]`: resolves canonical `repo_root`, `.venv` (when present), `Path(sys.executable).resolve()`, `Path(sys.prefix).resolve()`, `~/.local/share/uv/python` (when present), `~/.config/strands-code`, `~/.cache/strands-code`, `/tmp`, plus host dev tool binaries via `shutil.which` (`git`, `pytest`, `rg`, `ruff`, `uv`, active Python).
  - `render_box_toml(...) -> str`: emits valid TOML with `name`, `box_dir`, `policy = "policy.dw"`, `[agent]` (`command`, `workspace`, `env`), `[agent.filesystem]` (`read`, `read_file`, `write` — excluding `~/.config/strands-box` — `list`, `exec`), `[tool.*]`, and `[egress.<name>]`.
  - `render_policy_dw(...) -> str`: emits default-deny Dogwood `.dw` with `Box::Action::"net:connect"` (`port == 443`), `Box::Action::"http:request"` (host + optional path prefix matching), `forbid` rules on `*/.env`, `*/.env.*`, `*/.ssh/*`, `*/.aws/*`, non-push dev `[tool.*]` `shell:spawn` permits, and the canonical MFOTL `push_requires_recent_tests` rule (`formerly within 900s` `pytest`).

- **Linux Diagnostics & Wrapper Execution (`D-07`):**
  - `_BOX_BINARIES = ("box", "strands-box-contain-trampoline", "strands-box-sock-alias")`
  - `discover_box_binaries(box_bin: str | Path | None = None) -> tuple[Path | None, list[str]]`: resolves explicit `--box-bin`, then `STRANDS_BOX_BIN`, then `shutil.which("box")`; checks all 3 binaries exist in `resolved.parent` cleanly.
  - `run_box_doctor(repo_root: Path | None = None, *, config_path: Path | None = None, box_bin: str | Path | None = None) -> BoxDoctorReport`: pure diagnostic checks for OS/arch (`x86_64` checks `EXPERIMENTAL_X86_SUPPORT=TRUE`), 3 co-located binaries, Ubuntu `/proc/sys/kernel/apparmor_restrict_unprivileged_userns` + `/etc/apparmor.d/strands-box`, optional `dogwood` CLI, and active config + `uv`/`.venv` realpath readiness. Never reads or prints secret values.
  - `launch_box_run(extra_args: list[str], *, repo_root: Path | None = None, config_path: Path | None = None, box_bin: str | Path | None = None) -> int`: symlink-refuses `box.toml` / `policy.dw`, verifies 3 co-located binaries, auto-sets `EXPERIMENTAL_X86_SUPPORT=TRUE` in child env on Linux `x86_64` when unset, executes `[str(resolved_box), "run", "--config", str(cfg), "--", *extra_args]`, returns child exit code cleanly.

---

## 2. Runtime Seams (`policy/codeact.py`, `policy/core.py`, `dispatch/core.py`, `entry/main.py`)

- **`strands_code_cli/policy/codeact.py` (`D-06`):**
  - Extract small helper `_codeact_shell_cmd(argv: list[str]) -> list[str]`: returns `["sh", "-c", shlex.join(argv)]` when `is_in_strands_box()` is True, else `list(argv)`.
  - Keeps `codeact_shell(cwd, argv)` at `CC 11`, preserves `isinstance(argv, str)` & empty-argv validation, and routes boxed CodeAct calls through `strands-box-sock-alias` -> Dogwood temporal log cleanly.

- **`strands_code_cli/policy/core.py` (`D-02`):**
  - Append `Path(os.path.realpath(platformdirs.user_config_dir("strands-box")))` to `protected_dirs` in `_is_protected_skills_or_config_path()` (`B 8`), keeping `decide()` unchanged at `C 15`.

- **`strands_code_cli/dispatch/core.py` (`D-01`):**
  - In `_policy_message()` (`L2300`), when handling `""` or `"show"`, append `"Sandbox: Strands Box active (STRANDS_BOX=1)"` if `is_in_strands_box()` is True.
  - Strictly NO `os.environ` inside `dispatch/core.py` (`test_no_credential_persistence_sinks`), and strictly NO `"budget"`/`"enforce"`/`"quota"`/`"halt"` substrings (`test_no_budgets_or_enforcement_vocabulary`). Keep `_setup_decision_entries` (`CC 20`) untouched.

- **`strands_code_cli/entry/main.py` (`D-01`):**
  - Build/mount `box_app: typer.Typer` via `app.add_typer(box_app, name="box", help="Strands Box Linux sandbox helpers (init, doctor, run).")` delegating to `sandbox/box.py` and rendering reports cleanly through `print_plain(Console(), ...)`.
  - Add `if ctx.invoked_subcommand is not None: return` at top of `_root` (`C 13 -> C 14`) so `strands-code box init|doctor|run` never triggers `_preflight_credentials()` or `run_loop()`. Keep zero `os.environ` inside `entry/main.py`.
