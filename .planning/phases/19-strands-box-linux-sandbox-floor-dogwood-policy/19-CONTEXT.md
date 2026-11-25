# Phase 19: Strands Box Linux Sandbox Floor & Dogwood Policy - Context

**Gathered:** 2026-11-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver `SANDBOX-01` — an OS-enforced defense-in-depth containment floor using external Strands Box (`strands-agents/box` `v0.2.3+`, Linux 3-binary layout: `box`, `strands-box-contain-trampoline`, `strands-box-sock-alias` via unprivileged `CLONE_NEWUSER`/`CLONE_NEWNET`/mount/PID/IPC/UTS namespaces + `seccomp-bpf`; no `bwrap` or Landlock required) paired with host-side deterministic Dogwood (`policy.dw`) underneath `strands-code`'s interactive HITL dialogs:
- CLI surface: `strands-code box init|doctor|run` Typer subcommand group (`strands_code_cli/sandbox/box.py`, wired from `strands_code_cli/entry/main.py` while keeping bare `strands-code` launching the REPL), plus a read-only `Sandbox: Strands Box active (STRANDS_BOX=1)` line in `/policy` when running inside Box.
- Host-only self-tamper config storage: generate per-repo configs under `~/.config/strands-box/repos/<repo-slug>-<hash8>/{box.toml,policy.dw}` (`0o700` dirs / `0o600` files, symlink-refused) with `box_dir = ~/.local/share/strands-box/repos/<repo-slug>-<hash8>`, never mounted inside `[agent.filesystem].write`, and protected in `policy/core.py` against broad repo `[[allow]]` globs (with optional `--out <dir>` emitting a self-tamper warning if inside writable paths).
- Containment, 7-provider egress & Dogwood policy: `uv`/`.venv` Python symlink realpaths resolved, `TERM`/`HOME`/`PATH`/`STRANDS_BOX=1`, auto-detected least-privilege egress profiles across all 7 core providers (`bedrock`, `google`, `anthropic`, `openai`, `meta`, `openrouter`, `typesafe`) plus opt-in Phase 17/18 flags (`--allow-decisions-api`, `--allow-github-skills`), default-deny `policy.dw` with `.env`/secret-file read forbids and the canonical MFOTL temporal rule (`git push` requires `formerly within 900s` `pytest`), formally logging a scoped revisit of `v1.0` `D-05`.
- CodeAct & Linux diagnostics/docs: `STRANDS_BOX=1` `codeact_shell` routing via `["sh", "-c", shlex.join(argv)]`, `box doctor` Linux `x86_64` (`EXPERIMENTAL_X86_SUPPORT=TRUE`) + Ubuntu 24.04 `apparmor_restrict_unprivileged_userns` / `/etc/apparmor.d/strands-box` + 3-binary co-location checks, `box run` wrapper, and setup documentation.

Out of scope: bundling or forking Rust Strands Box binaries, adding `strands-agents[cedar]` or LLM/NL-string policies inside `strands-code`'s Python `interventions`, running Strands Box as an in-process Python sandbox binding, macOS Seatbelt automation, MCP broker policies (`SKILL-04`), Monty Rust Python VM (**Phase 20**, `SANDBOX-02`), `/help`/`@file`/`/review` (**Phase 21**), `strands-agents-evals` (**Phase 22**), and any edits to `strands_code_agent/` (`D-24`).

</domain>

<decisions>
## Implementation Decisions

### CLI Surface, Storage Boundary & Self-Tamper Defense
- **D-01 (`strands-code box init|doctor|run` Typer Group + `/policy` Indicator):**
  - Expose Strands Box tooling as a nested Typer command group `strands-code box` (`init`, `doctor`, `run`) on `strands_code_cli/entry/main.py:app`, implemented inside an isolated package `strands_code_cli/sandbox/box.py`.
  - Guard `_root(ctx: typer.Context, ...)` in `strands_code_cli/entry/main.py` with `if ctx.invoked_subcommand is not None: return` so `strands-code box init|doctor|run` never invokes `_preflight_credentials()` or opens the interactive REPL, while bare `strands-code [--session-id ...] [--codeact ...] [--model ...]` launches identically to today (and `_expand_bare_codeact` continues stopping at `--`, preserving `strands-code box run -- --codeact`).
  - Inside `strands_code_cli/dispatch/core.py:_policy_message()`, append a read-only status line `Sandbox: Strands Box active (STRANDS_BOX=1)` whenever `is_in_strands_box()` (defined in `sandbox/box.py`) returns True — keeping `os.environ` reads out of `dispatch/core.py` and avoiding banned enforcement vocabulary (`enforce`, `budget`, `quota`, `halt`). — *Reversibility: easy — isolated subcommand registration and single helper call.*

- **D-02 (Host-Only Config Storage Outside `[agent.filesystem].write` + Policy Downgrade):**
  - Store generated per-repo files outside the agent's writable workspace by default under `Path(platformdirs.user_config_dir("strands-box")) / "repos" / f"{slug}-{hash8}"` (`box.toml` and `policy.dw`) with `0o700` directories, `0o600` files, atomic temp-write + `os.replace`, and symlink refusal across parent/target paths; set `box_dir` under `Path(platformdirs.user_data_dir("strands-box")) / "repos" / f"{slug}-{hash8}"` (invisible inside the sandbox).
  - Never include `~/.config/strands-box` in `[agent.filesystem].write` so an in-session compromised `write`, `edit`, or `python_repl` call cannot weaken next-launch containment or swap `policy.dw`.
  - Extend `strands_code_cli/policy/core.py:_is_protected_skills_or_config_path()` to include `Path(os.path.realpath(platformdirs.user_config_dir("strands-box")))`, downgrading broad `[[allow]]` write/edit rules to `Prompt` even during unboxed sessions while keeping explicit `[[deny]]` priority and `read` allows unchanged.
  - Support an explicit `--out <dir>` override on `box init` for inspection or custom paths; when the resolved `--out` directory falls inside `[agent.filesystem].write` (repo workspace, `~/.config/strands-code`, `~/.cache/strands-code`, or `/tmp`), print a prominent plain-text self-tamper warning. — *Reversibility: easy — path resolver + one protected directory addition.*

### `box.toml` Containment & Least-Privilege 7-Provider Egress Profiles
- **D-03 (`uv`/`.venv` Realpath Resolution, `[agent].env` & Zero Secret Persistence):**
  - Resolve realpaths when constructing `[agent.filesystem]` for:
    - `.venv` (if present in repo) AND symlink targets of `sys.executable` / `uv`-managed Python toolchains (`Path(sys.executable).resolve()`, its Python runtime prefix, and `~/.local/share/uv/python` when present) so dynamically linked stdlib/shared libs remain readable under Linux mount namespaces.
    - Read-only system runtime trees (`/usr`, `/bin`, `/lib`, `/lib64`, `/etc/ssl`, `/etc/resolv.conf`, plus `read_file = ["/etc/hosts", "/etc/nsswitch.conf"]`).
    - Read-write runtime paths required by `strands-code`: canonical workspace repo root, `~/.config/strands-code`, `~/.cache/strands-code`, and `/tmp`.
    - Direct OS executables (`git`, `pytest`, `rg`, `ruff`, `uv`, active Python) resolved to concrete paths.
  - Populate `[agent].env` explicitly with `HOME`, `PATH` (prepending active `.venv/bin` if present), `TERM` (host `TERM` or fallback `"xterm-256color"`, plus `COLORTERM` if set), `AWS_REGION` (when Bedrock is enabled), and `STRANDS_BOX = "1"`.
  - Read host env var *names/presence* strictly inside `strands_code_cli/sandbox/box.py` (never persisting secret values, never reading `.env`); emit `env://VAR` / `aws://` references only. — *Reversibility: moderate — template builder in `sandbox/box.py`.*

- **D-04 (Least-Privilege Auto-Detected 7-Provider Egress + Phase 17/18 Opt-Ins):**
  - By default, `box init` auto-detects the minimal active provider set from `ProviderConfig.load()`, active `routing.yaml` engine choices (if configured), and non-empty host env keys (overridable via repeatable or comma-separated `--provider`), falling back to the active configured model's provider or `bedrock` when none are detected.
  - Generate vetted `[egress.<name>]` blocks for all 7 core providers matching each provider's exact wire authentication header/signature:
    1. `bedrock`: `destinations = ["bedrock-runtime.<region>.amazonaws.com"]`, `secret.ref = "aws://"` (or `"aws://<profile>"` via `--aws-profile`; or `env://AWS_BEARER_TOKEN_BEDROCK` Bearer when bearer token is present) — **zero `sts.amazonaws.com` egress hole** (`first_run.py` skips STS under `STRANDS_BOX=1`).
    2. `google`: `destinations = ["generativelanguage.googleapis.com"]`, `secret.ref = "env://GOOGLE_API_KEY"` (or `"env://GEMINI_API_KEY"`), `placement = "header"`, `header = "x-goog-api-key"`, `prefix = ""`.
    3. `anthropic`: `destinations = ["api.anthropic.com"]`, `secret.ref = "env://ANTHROPIC_API_KEY"`, `placement = "header"`, `header = "x-api-key"`, `prefix = ""`.
    4. `openai`: `destinations = ["api.openai.com"]`, `secret.ref = "env://OPENAI_API_KEY"`, `placement = "header"`, `header = "Authorization"`, `prefix = "Bearer"`.
    5. `meta`: `destinations = ["api.meta.ai"]`, `secret.ref = "env://MODEL_API_KEY"` (or `"env://META_API_KEY"`), `placement = "header"`, `header = "Authorization"`, `prefix = "Bearer"`.
    6. `openrouter`: path-scoped `destinations = ["openrouter.ai/api/v1/chat/*", "openrouter.ai/api/alpha/decisions"]`, `secret.ref = "env://OPENROUTER_API_KEY"`, `placement = "header"`, `header = "Authorization"`, `prefix = "Bearer"` — path-scoping prevents Box's default `inject = "phantom"` from blocking unauthenticated `live_pricing.py` requests to `openrouter.ai/api/v1/models`.
    7. `typesafe`: `destinations = ["api.typesafe.ai"]`, `secret.ref = "env://TYPESAFE_API_KEY"`, `placement = "header"`, `header = "Authorization"`, `prefix = "Bearer"`.
  - Keep Phase 17/18 optional endpoints disabled unless explicitly opted in:
    - `--allow-decisions-api`: adds `decisionapi.net` with `env://JEV_API_KEY` (`Authorization: Bearer`).
    - `--allow-github-skills`: adds `api.github.com` (with optional `env://GITHUB_TOKEN`/`GH_TOKEN` Bearer strictly scoped to `api.github.com` only) plus unauthenticated download hosts `codeload.github.com` and `objects.githubusercontent.com`. — *Reversibility: easy — table-driven provider profile registry.*

### Dogwood `policy.dw`, Scoped `D-05` Revisit, CodeAct & Diagnostics
- **D-05 (Default-Deny `policy.dw`, Canonical Temporal Rule & Formal Scoped `D-05` Revisit):**
  - Generate `policy.dw` with default-deny semantics (`forbid` always beats `permit`):
    - Scoped `Box::Action::"net:connect"` (port `443`) and `Box::Action::"http:request"` permits matching ONLY the active enabled provider hosts/paths.
    - Explicit sensitive-file read forbids: `forbid (principal, action == Box::Action::"fs:read", resource)` matching `*/.env`, `*/.env.*`, `*/.ssh/*`, `*/.aws/*`.
    - Standard dev `[tool.*]` definitions in `box.toml` (`git`, `pytest`, `rg`, `ruff`, `uv`, `python`) paired with `Box::Action::"shell:spawn"` permits for non-push dev invocations plus the **canonical MFOTL temporal rule**:
      ```cedar
      @id("push_requires_recent_tests")
      permit (principal, action == Box::Action::"shell:spawn", resource)
      when { context.input.command == "git" && context.input.args like "push*" }
      when temporal {
          formerly within 900s (
              action == Box::Action::"shell:spawn" && context.input.command == "pytest"
          )
      };
      ```
  - **Formal Scoped Revisit of `v1.0` Decision `D-05`:** `v1.0` `D-05` specified deterministic TOML+Python policy rules and *"never Cedar"* inside `strands-code`. Because Dogwood (`.dw`) lowers to Cedar internally inside the external Rust `box` process (`SANDBOX.md:42-49`), Phase 19 formally logs this **scoped revisit of `D-05`**: deterministic host-side Dogwood (`.dw`) enforced externally by Strands Box is authorized as the OS containment floor, while in-process `strands-code` `interventions` remain 100% deterministic TOML + Python (`PolicyClassifier` only; never `strands-agents[cedar]`, never `"smart"`/NL-string policies). — *Reversibility: easy — declarative `.dw` rules and documented policy boundary.*

- **D-06 (`STRANDS_BOX=1` `codeact_shell` Alignment):**
  - Update `strands_code_cli/policy/codeact.py:codeact_shell()` so when `STRANDS_BOX` is truthy (`1`/`true`/`yes`), it invokes `subprocess.run(["sh", "-c", shlex.join(argv)], ...)` (`shell=False`, resolving `sh` on `PATH` so `strands-box-sock-alias` intercepts CodeAct shell calls through Strands Shell and records `shell:spawn` events in Dogwood's temporal log).
  - Retain strict `argv` validation (`isinstance(argv, str)` refused, empty `argv` refused) and `shlex.join` quoting so shell injection remains impossible; keep direct `subprocess.run(list(argv), ...)` outside Strands Box unchanged. — *Reversibility: trivial — localized branch in `codeact_shell`.*

- **D-07 (Linux `box doctor` / `box run`, Documentation & Verification Scope):**
  - Implement `strands-code box doctor` (read-only checks rendered via `print_plain(markup=False)`):
    - Checks Linux platform/arch (`x86_64` verifies `EXPERIMENTAL_X86_SUPPORT=TRUE`, `aarch64` GA).
    - Discovers `box` (`--box-bin` / `STRANDS_BOX_BIN` / `PATH`) and verifies the 3 co-located binaries in the same directory (`box`, `strands-box-contain-trampoline`, `strands-box-sock-alias`) + optional `dogwood` CLI.
    - Inspects Ubuntu 24.04+ `/proc/sys/kernel/apparmor_restrict_unprivileged_userns` (when present and `== "1"`, verifies `/etc/apparmor.d/strands-box` or reports exact remediation).
    - Validates active repo generated config (`box.toml` / `policy.dw`) and `uv` Python symlink realpaths cleanly without printing any secrets.
  - Implement `strands-code box run [--config <path>] [--box-bin <path>] [-- <args...>]` to resolve config (symlink-refused) and co-located `box`, inject `EXPERIMENTAL_X86_SUPPORT=TRUE` on Linux `x86_64` when unset (with notice), and invoke `subprocess.run([box_bin, "run", "--config", str(cfg), "--", *extra_args])` propagating the child exit code.
  - Document Linux 3-binary installation, `EXPERIMENTAL_X86_SUPPORT=TRUE`, copy-pasteable Ubuntu 24.04 `/etc/apparmor.d/strands-box` profile, 7-provider egress matrix, `strands-code box init|doctor|run` workflow, and Dogwood temporal rules in `docs/QUICKSTART.md` (and `docs/SANDBOX.md` if helpful).
  - Verify completely offline with hermetic unit tests (`tomllib` TOML validation, `.dw` structural/temporal checks, symlink refusal, `uv` realpath resolution, all 7+2 egress profiles, `box doctor`/`box run` mocks, `codeact_shell` `STRANDS_BOX=1` `sh -c` & injection tests, `policy/core.py` `strands-box` config downgrade, `/policy` read-only line, `main.py` Typer routing) plus opportunistic `@pytest.mark.integration` execution if host `box`/`dogwood` binaries exist. — *Reversibility: easy — self-contained diagnostics and wrapper.*

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/REQUIREMENTS.md` — `SANDBOX-01`
- `.planning/ROADMAP.md` — Phase 19 goal & 3 success criteria
- `.planning/research/SANDBOX.md` — Strands Box Linux evaluation & scoped `D-05` revisit rationale
- `.planning/research/ARCHITECTURE.md` (§2 Box Containment & Credential Flow), `.planning/research/STACK.md` (§2), `.planning/research/FEATURES.md` (§2), `.planning/research/PITFALLS.md` (Pitfalls 1–4)
- `strands_code_cli/entry/main.py` — `app`, `_root`, `_expand_bare_codeact` (`D-01`)
- `strands_code_cli/entry/first_run.py` — `STRANDS_BOX=1` STS skip & `_PROVIDER_ENV_KEYS`
- `strands_code_cli/entry/provider_config.py` — `ProviderConfig`, default model/region reading
- `strands_code_cli/policy/codeact.py` — `codeact_shell` (`L234-271`)
- `strands_code_cli/policy/core.py` — `_is_protected_skills_or_config_path` (`L535-571`), `decide` (`C 15`)
- `strands_code_cli/dispatch/core.py` — `_policy_message` (`L2300-2329`)
- `tests/cost/test_cost_context.py` — `test_no_budgets_or_enforcement_vocabulary` (`L1041`), `test_no_credential_persistence_sinks` (`L1070`)
- `pyproject.toml` — `[tool.ruff]`, `[tool.importlinter]`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `strands_code_cli/entry/first_run.py` ALREADY skips `sts.get_caller_identity()` when `STRANDS_BOX=1` and checks non-empty env var presence (never key prefixes), so Strands Box `strands_box_...` phantom placeholders pass startup preflight natively!
- `strands_code_cli/policy/core.py:_is_protected_skills_or_config_path()` ALREADY canonicalizes paths via `realpath` and downgrades broad `[[allow]]` write/edit rules targeting `platformdirs.user_config_dir("strands-code")` and `platformdirs.user_cache_dir("strands-code")` — adding `platformdirs.user_config_dir("strands-box")` fits directly into `protected_dirs` without inflating `decide()` (`CC 15`).
- `strands_code_cli/ui/output.py:print_plain` ensures sandbox paths and diagnostics render safely with `markup=False`.

### Constraints & Watchpoints
- **`test_no_credential_persistence_sinks` (`tests/cost/test_cost_context.py:1070`):** asserts zero `os.environ`/`os.getenv` tokens inside `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, and `entry/main.py`! Keep ALL `os.environ` reads (`STRANDS_BOX`, `STRANDS_BOX_BIN`, `EXPERIMENTAL_X86_SUPPORT`, host env key detection, `AWS_REGION`, `TERM`, `PATH`) strictly inside `strands_code_cli/sandbox/box.py` (and `policy/codeact.py` / `entry/first_run.py`), exposing `is_in_strands_box()` for `dispatch/core.py:_policy_message()`.
- **`test_no_budgets_or_enforcement_vocabulary` (`tests/cost/test_cost_context.py:1041`):** asserts no unnegated `"budget"`, `"enforce"`, `"quota"`, or `"halt"` substrings appear in `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, `model/model_switch.py`, or `cost/cost_context.py`. Use `"Sandbox: Strands Box active (STRANDS_BOX=1)"` in `_policy_message()`.
- **Complexity ceilings (`xenon --max-absolute C`) & `lint-imports`:** keep `run_loop` (`C 18`), `_setup_decision_entries` (`C 20`), and `price_table` (`C 20`) untouched; keep `decide()` (`C 15`) and `_policy_message()` well within `<= C (20)`. `strands_code_cli/sandbox/box.py` MUST NEVER import `strands_code_cli.entry.main` (`lint-imports`).
- **Python 3.10+ minimum:** `pyproject.toml` declares `requires-python >=3.10`, while dev `.venv` runs Python 3.12+ (and CI 3.10+): write TOML output in `sandbox/box.py` via clean JSON/TOML-escaped helpers with zero extra runtime dependencies, and use `tomllib` (stdlib 3.11+) cleanly in tests.
- **`strands_code_agent/` immutability (`D-24`):** Zero edits anywhere under `strands_code_agent/`.

</code_context>

<specifics>
## Specific Ideas

- **Per-repo config path derivation:** Build `<slug>-<hash8>` from sanitized lowercase repo directory name (e.g., `re.sub(r"[^a-z0-9]+", "-", repo_root.name.lower()).strip("-") or "repo"`) plus first 8 hex chars of `hashlib.sha256(str(repo_root.resolve()).encode()).hexdigest()` so two repos sharing a directory basename never overwrite each other's `box.toml`/`policy.dw`.
- **Canonical `/etc/apparmor.d/strands-box` snippet for Ubuntu 24.04+:**
  ```text
  abi <abi/4.0>,
  include <tunables/global>

  profile strands-box /usr/local/libexec/strands-box/{box,strands-box-contain-trampoline} flags=(unconfined) {
    userns,
    include if exists <local/strands-box>
  }
  ```
- **TOML escaping helper:** Reject ASCII control characters (`< 32`, `\x7f`) in any env/path/region string written into `box.toml` or `policy.dw` to prevent TOML or Cedar/Dogwood rule injection from crafted repo paths or env values.

</specifics>

<deferred>
## Deferred Ideas

- Automating installation of `box` Rust binaries or mutating host `/etc/apparmor.d/` with `sudo`.
- Non-LLM HTTP exfil-correlation temporal rules or full MCP broker `.cedarschema` policy rules (`SKILL-04`, `v2.1+`).
- macOS Apple Silicon Seatbelt diagnostics/profiles.
- Monty Rust Python VM (`pydantic-monty` / Strands Box Monty) for `python_repl` & CodeAct — **Phase 20 (`SANDBOX-02`)**.
- `/help`, `@file` / `/file`, `/review` — **Phase 21 (`LOOP-06`, `TOOL-05`, `REVIEW-01`)**.
- `strands-agents-evals` & red-team suite — **Phase 22 (`EVAL-01`)**.

</deferred>

*Phase: 19-strands-box-linux-sandbox-floor-dogwood-policy*
*Context gathered: 2026-11-25*
