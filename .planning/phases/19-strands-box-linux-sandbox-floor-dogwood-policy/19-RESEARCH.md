# Phase 19: Strands Box Linux Sandbox Floor & Dogwood Policy — Research

**Researched:** 2026-11-25
**Phase:** `19-strands-box-linux-sandbox-floor-dogwood-policy`
**Requirements:** `SANDBOX-01`
**Sources Inspected Directly:**
- Planning & evaluation archive: `.planning/research/SANDBOX.md`, `.planning/research/ARCHITECTURE.md` (§2), `.planning/research/STACK.md` (§2), `.planning/research/FEATURES.md` (§2), `.planning/research/PITFALLS.md` (Pitfalls 1–4), `19-CONTEXT.md`
- Existing CLI seams: `strands_code_cli/entry/main.py`, `strands_code_cli/entry/first_run.py`, `strands_code_cli/entry/provider_config.py`, `strands_code_cli/routing/core.py`, `strands_code_cli/policy/codeact.py`, `strands_code_cli/policy/core.py`, `strands_code_cli/dispatch/core.py`
- CI & security contracts: `pyproject.toml` (`[tool.ruff]`, `[tool.importlinter]`, `requires-python = ">=3.10"`), `tests/cost/test_cost_context.py` (`test_no_budgets_or_enforcement_vocabulary`, `test_no_credential_persistence_sinks`), `tests/conftest.py`
- Upstream Strands Box (`strands-agents/box` `v0.2.3+`) & Dogwood (`dogwood-policy/dogwood`) design/schema documentation (verified in live research)

---

## 1. Strands Box (`strands-agents/box` `v0.2.3+`) Linux Architecture

### 1.1 Native 3-Binary Layout & Installation (No `bwrap`, No Landlock Required)

Unlike earlier assumptions in `.planning/research/SANDBOX.md:3,29`, Strands Box on Linux (`v0.2.3+`) does **not** invoke Bubblewrap (`bwrap`) or depend on Landlock. It ships as three co-located Rust binaries that MUST sit in the same host directory:

1. `box` — CLI entrypoint, embedded **Dogwood Local Engine**, TLS/SigV4 egress gateway proxy, Strands Shell host runtime, and MCP broker.
2. `strands-box-contain-trampoline` — Linux namespace/mount/`seccomp-bpf` isolator creating `CLONE_NEWUSER`, `CLONE_NEWNS`, `CLONE_NEWPID`, `CLONE_NEWIPC`, `CLONE_NEWUTS`, and `CLONE_NEWNET`, applying `PR_SET_NO_NEW_PRIVS`, dropping capabilities, bind-mounting `[agent.filesystem]`, and attaching `seccomp-bpf` before `exec`ing `[agent].command`.
3. `strands-box-sock-alias` — UNIX-socket/loopback bridge inside the private network namespace plus `sh`/`bash`/`zsh` `PATH` aliases routing shell commands back to the host Strands Shell + Dogwood policy engine.

- **Packaging:** Native host binaries (Rust Cargo crates `strands-box` and `strands-box-containment`, installed via `download.sh` or `cargo build --release`) — zero PyPI/`uv` wheel and zero Rust fork inside `strands-code`.
- **Mandatory Linux `x86_64` Gate:** Linux `aarch64` is GA; Linux `x86_64` requires `EXPERIMENTAL_X86_SUPPORT=TRUE` in the host environment launching `box run`, otherwise `box` refuses startup.
- **Ubuntu 24.04+ AppArmor `userns` Trap:** When `/proc/sys/kernel/apparmor_restrict_unprivileged_userns` is `"1"`, Ubuntu denies `CLONE_NEWUSER` with `EPERM`. Pre-installed `/etc/apparmor.d/bwrap` profiles do **not** apply because Box executes `strands-box-contain-trampoline`. Mitigation: load a targeted `/etc/apparmor.d/strands-box` profile granting `userns,` to the fixed install directory's `box` and `strands-box-contain-trampoline` binaries (or disable sysctl in ephemeral dev VMs).

### 1.2 CLI Surface & Subcommand Contracts

- `box run --config <PATH_TO_BOX.TOML> [-- <AGENT_ARGS>...]` validates both `box.toml` and `policy.dw` **before** spawning namespaces or launching the agent, preserves the host interactive PTY (`stdin`/`stdout`/`stderr` for `prompt_toolkit` and `rich`), and forwards trailing arguments after `--` to `[agent].command`.
- `dogwood validate <policy.dw>` (companion CLI from `dogwood-policy/dogwood`) provides offline static validation when installed on the host.

---

## 2. `box.toml`, Containment & Dogwood `policy.dw` Contracts

### 2.1 Self-Tamper Storage Boundary (`D-02`)

Operation hitting `[agent.filesystem].write` uses direct kernel mounts and bypasses `policy.dw` event logging (`SANDBOX.md` / `ARCHITECTURE.md §2`). Therefore:
- Per-repo configs MUST live host-only outside `[agent.filesystem].write`:
  `~/.config/strands-box/repos/<repo-slug>-<hash8>/{box.toml,policy.dw}` (`0o700` dirs, `0o600` files, symlink-refused atomic `mkstemp` + `os.replace`) with `box_dir = ~/.local/share/strands-box/repos/<repo-slug>-<hash8>`.
- `strands_code_cli/policy/core.py:_is_protected_skills_or_config_path()` MUST additionally include `Path(os.path.realpath(platformdirs.user_config_dir("strands-box")))` so unboxed sessions also downgrade broad `[[allow]]` write/edit rules to interactive `Prompt`.
- Explicit `--out <dir>` export MUST warn loudly if the target path sits inside `[agent.filesystem].write` (`repo_root`, `~/.config/strands-code`, `~/.cache/strands-code`, or `/tmp`).

### 2.2 `[agent].env`, Proxy Auto-Discovery & `uv` Symlink Realpaths (`D-03`)

- Box clears host env inheritance: `[agent].env` MUST pass `HOME`, `PATH` (prepending `.venv/bin`), `TERM` (defaulting to `"xterm-256color"`, plus `COLORTERM` when set), `AWS_REGION` (when Bedrock active), and `STRANDS_BOX = "1"`.
- Box reserves and injects `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`, `SSL_CERT_FILE`, `AWS_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, `GIT_SSL_CAINFO`, and `strands_box_<rand>` phantom placeholders for `env://...` refs (or synthetic AWS creds for `aws://...`). Python's `boto3`, `httpx`, and `urllib.request` honor these proxy/CA env vars natively with zero preload shims.
- **Critical `uv` Python symlink fix:** `.venv/bin/python` created by `uv` symlinks to `~/.local/share/uv/python/.../bin/python3.x`. Mounting only `.venv` breaks dynamic loader / stdlib resolution under Linux mount namespaces unless `[agent.filesystem].read` resolves `Path(sys.executable).resolve()` (plus its runtime prefix and `~/.local/share/uv/python` when present).
- Generated TOML MUST sanitize/reject ASCII control chars (`ord < 32` or `127`) and properly escape paths/env strings (`json.dumps()` produces TOML-valid basic strings on Python 3.10+ with zero new runtime dependencies; `tomllib` verifies round-trip parsing cleanly in Python 3.12 test runtime).

### 2.3 Least-Privilege 7-Provider Egress Profiles + Phase 17/18 Opt-Ins (`D-04`)

| Profile | `destinations` | `secret.ref` | Wire Injection (`placement` / `header` / `prefix`) | Notes / Pitfalls |
|---|---|---|---|---|
| `bedrock` | `["bedrock-runtime.<region>.amazonaws.com"]` | `"aws://"` (or `"aws://<profile>"`; alt `"env://AWS_BEARER_TOKEN_BEDROCK"`) | Host-side SigV4 re-signing (`aws://`) or `Authorization: Bearer` | **Zero `sts.amazonaws.com` egress hole** (`first_run.py` skips STS on `STRANDS_BOX=1`). |
| `google` | `["generativelanguage.googleapis.com"]` | `"env://GOOGLE_API_KEY"` (or `"env://GEMINI_API_KEY"`) | `placement = "header"`, `header = "x-goog-api-key"`, `prefix = ""` | Must NOT use `Authorization: Bearer`; `google-genai` expects `x-goog-api-key`. |
| `anthropic` | `["api.anthropic.com"]` | `"env://ANTHROPIC_API_KEY"` | `placement = "header"`, `header = "x-api-key"`, `prefix = ""` | `anthropic` SDK sends `x-api-key`. |
| `openai` | `["api.openai.com"]` | `"env://OPENAI_API_KEY"` | `placement = "header"`, `header = "Authorization"`, `prefix = "Bearer"` | Native OpenAI Responses API & model discovery. |
| `meta` | `["api.meta.ai"]` | `"env://MODEL_API_KEY"` (or `"env://META_API_KEY"`) | `placement = "header"`, `header = "Authorization"`, `prefix = "Bearer"` | Meta Model API (`/v1/responses`, `/v1/models`). |
| `openrouter` | `["openrouter.ai/api/v1/chat/*", "openrouter.ai/api/alpha/decisions"]` | `"env://OPENROUTER_API_KEY"` | `placement = "header"`, `header = "Authorization"`, `prefix = "Bearer"` | Path-scoped so Box's `inject = "phantom"` does NOT break unauthenticated `live_pricing.py` requests to `/api/v1/models`. |
| `typesafe` | `["api.typesafe.ai"]` | `"env://TYPESAFE_API_KEY"` | `placement = "header"`, `header = "Authorization"`, `prefix = "Bearer"` | Native TypeSafe System One router (`Phase 17`). |
| `decisions_api` *(opt-in)* | `["decisionapi.net"]` | `"env://JEV_API_KEY"` | `placement = "header"`, `header = "Authorization"`, `prefix = "Bearer"` | Enabled only with `--allow-decisions-api`. |
| `github_skills` *(opt-in)* | `["api.github.com"]` + unauthenticated `["codeload.github.com", "objects.githubusercontent.com"]` | `"env://GITHUB_TOKEN"` / `"env://GH_TOKEN"` (only on `api.github.com`) | Bearer on `api.github.com` only; no secret on `codeload`/`objects` | Enabled only with `--allow-github-skills`; mirrors `T-18-01`/`T-18-08` token isolation. |

### 2.4 Dogwood `policy.dw` & Formal Scoped Revisit of `v1.0` `D-05` (`D-05`)

- Default-deny Cedar-superset rules evaluated by external host `box` (`forbid` overrides `permit`):
  - `Box::Action::"net:connect"` (`context.input.port == 443`) + `Box::Action::"http:request"` strictly scoped to active egress hosts/paths.
  - `forbid (principal, action == Box::Action::"fs:read", resource)` when `context.input.path like "*/.env" || context.input.path like "*/.env.*" || context.input.path like "*/.ssh/*" || context.input.path like "*/.aws/*"`.
  - `[tool.{git,pytest,rg,ruff,uv,python}]` in `box.toml` + `Box::Action::"shell:spawn"` permits (non-push `git` + dev tools) + the **canonical MFOTL temporal rule**:
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
- **Scoped `D-05` Revisit:** `v1.0` `D-05` locked deterministic TOML+Python rules and banned Cedar inside Python `interventions`. Dogwood lowers `.dw` to Cedar internally inside the external host `box` binary, so Phase 19 formally logs a **scoped revisit of `D-05`**: deterministic host-side `.dw` evaluated by Strands Box is authorized as the OS containment floor, while `strands_code_cli/policy/policy_gate.py` remains 100% deterministic TOML + Python (zero `strands-agents[cedar]`, zero LLM/NL-string policy).

---

## 3. Codebase Integration Seams & Empirically Verified Constraints

Inspecting live code and running empirical checks revealed six hard constraints that Plans `19-01`..`19-03` satisfy by design:

1. **Typer Subcommand Routing (`strands_code_cli/entry/main.py`):**
   - Verified with `.venv` Typer: registering `@app.callback(invoke_without_command=True)` with `if ctx.invoked_subcommand is not None: return` at top of `_root` plus `app.add_typer(box_app, name="box")` preserves bare `strands-code`, `--session-id`, `--model`, `--codeact` AND routes `strands-code box init|doctor|run -- ...` cleanly without invoking `_preflight_credentials()` or `run_loop()`.
   - `_expand_bare_codeact` (`L356-358`) already halts on `"--"`, so `strands-code box run -- --codeact` passes through untouched.
   - Notice current Radon complexity: `_root` is `C (13)`, rising to `14` cleanly within `xenon C (<= 20)`.
2. **`test_no_credential_persistence_sinks` (`tests/cost/test_cost_context.py:1070-1105`):**
   - Forbids any `os.environ` or `os.getenv` token in `entry/main.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, `model/model_switch.py`, and `cost/cost_context.py`!
   - Therefore, ALL environment reads (`STRANDS_BOX`, `STRANDS_BOX_BIN`, `EXPERIMENTAL_X86_SUPPORT`, `PATH`, `HOME`, `TERM`, `AWS_REGION`, provider key presence) MUST live inside `strands_code_cli/sandbox/box.py` (and `first_run.py` / `codeact.py`), with `dispatch/core.py` and `entry/main.py` calling helpers like `is_in_strands_box()`.
3. **`test_no_budgets_or_enforcement_vocabulary` (`tests/cost/test_cost_context.py:1041-1068`):**
   - Forbids unnegated `"budget"`, `"enforce"`, `"quota"`, and `"halt"` substrings inside `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, `model/model_switch.py`, `cost/cost_context.py`, and `strands_code_agent/utils.py`.
   - Therefore, `_policy_message()` (`B 9`) in `dispatch/core.py` MUST render `"Sandbox: Strands Box active (STRANDS_BOX=1)"` — zero `"enforce"` substring!
4. **`codeact_shell` Box Alignment (`strands_code_cli/policy/codeact.py:234-271`):**
   - `codeact_shell` currently runs `subprocess.run(list(argv), ...)` (`shell=False`, `CC 11`), bypassing `PATH`'s `sh` alias (`strands-box-sock-alias`). Extracting `_codeact_shell_cmd(argv)` (`is_in_strands_box()` -> `["sh", "-c", shlex.join(argv)]`, else `list(argv)`) keeps `codeact_shell` `CC 11`, preserves strict `argv`-list type checks and `shlex.join` quoting against injection, and feeds CodeAct commands into Dogwood's temporal log under `STRANDS_BOX=1`.
5. **`tests/conftest.py` Hermeticity (`L5-26`):**
   - Already strips `"STRANDS_BOX"` and all 7 provider keys (`AWS_BEARER_TOKEN_BEDROCK`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `MODEL_API_KEY`, `META_API_KEY`, `OPENROUTER_API_KEY`, `TYPESAFE_API_KEY`, `JEV_API_KEY`, `GITHUB_TOKEN`, `GH_TOKEN`). Add `"STRANDS_BOX_BIN"` and `"EXPERIMENTAL_X86_SUPPORT"` so host box env vars never leak into unit tests (while `@pytest.mark.integration` retains opt-in host testing).
6. **`import-linter` & `D-24`:**
   - `strands_code_cli/sandbox/box.py` MUST NEVER import `strands_code_cli.entry.main` (`contracts: 1 kept, 0 broken`). `entry/main.py` imports `box_app` / subcommand handlers from `sandbox/box.py` (the composition-root direction).
   - Zero edits under `strands_code_agent/` (`D-24`).
