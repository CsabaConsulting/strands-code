---
phase: "19"
slug: "strands-box-linux-sandbox-floor-dogwood-policy"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-25"
---

# Phase 19 — Security

> Per-phase security contract: threat register, remediation verification, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `Host Config & State (~/.config/strands-box/, ~/.local/share/strands-box/) <-> Agent Workspace ([agent.filesystem].write)` | Repo-scoped `box.toml`, `policy.dw`, and `box_dir` socket/state dirs | Stored host-only under `0o700` dirs / `0o600` files, excluded from `[agent.filesystem].write`, downgraded to `Prompt` + dead-`Always` blocked in `policy/core.py` & `policy_gate.py`, and protected by Dogwood `fs:write`/`fs:delete`/`fs:move` forbids in `policy.dw` |
| `Host Env Secrets -> Egress Gateway Secret Refs (env://VAR, aws://) -> Upstream APIs` | Provider API keys & AWS SigV4 credentials vs `[agent.env]` & `[egress.*]` | Raw secrets never enter `[agent.env]` or generated TOML/DW files; gateway injects auth only to pinned hosts/headers; `bedrock` omits `sts.amazonaws.com`; unauthenticated targets live solely in `policy.dw` |
| `Untrusted CLI Args & Env -> strands-code box init|doctor|run -> box.toml / subprocess` | Repo paths, `--region`, `--aws-profile`, `--provider`, `box_dir`, `STRANDS_BOX_BIN`, `XDG_*` | Control chars (`< 32`, `127`) rejected; region/profile/provider regex-checked; `XDG_*` non-absolute/root values filtered; binary layout checks `os.X_OK`; `launch_box_run()` parses TOML and validates `policy` & `box_dir` fail-closed |
| `Symlinked Paths / Ancestors <-> _refuse_symlink() & _resolve_code_dirs()` | `~/.config/strands-box`, `~/.local/share/strands-box`, `~/.config/strands-code`, `~/.cache/strands-code`, `box.toml`, `policy.dw` | `_refuse_symlink()` checks target + up to 2 ancestor dirs before creation, read, `chmod`, or launch; `_resolve_code_dirs()` checks un-dereferenced paths before `realpath()`; writes use `mkstemp(..., dir=parent)` + `chmod(0o600)` + `os.replace()` |
| `Agent Shell & CodeAct -> _codeact_shell_cmd() -> sh -c -> Dogwood policy.dw` | `CodeactStint` `shell(argv)` calls inside Box (`STRANDS_BOX=1`) | String `argv` refused; list/tuple wrapped via `["sh", "-c", shlex.join(argv)]` so metacharacters stay quoted while Dogwood inspects resolved `shell:spawn`; `policy.dw` forbids `.env`/`.ssh`/`.aws` reads & gates `git` `push` behind recent passing `pytest` |
| `In-Process Policy Gate -> policy/core.py:decide() -> Protected Repo & Host Paths` | Broad `[[allow]]` globs (`path = "*"`, `.agent/**`) | Explicit `[[deny]]` wins; broad `write`/`edit` targeting `~/.config/strands-box/**`, `~/.local/share/strands-box/**`, `.agent/policy.toml`, `.agent/routing.yaml`, `.agent/MEMORY.md`, and `STRANDS.md` (incl. symlinks) downgrade to `Prompt` and block persisting dead `[[allow]]` rules |
| `Upstream package boundary (strands_code_agent/)` | Fork-inherited agent package kept byte-pristine under `D-24` | `CodeAgent` / `SandboxedPythonInterpreter` untouched (`git diff ee42ea2 -- strands_code_agent/` empty) |

---

## Threat Register

Audited against Phase 19 commits (`f5a8ac6..b2604e6`), [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py), [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/core.py), [policy_gate.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/policy_gate.py), [dispatch/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py), `19-UAT.md` (`6/6` passed on live `strands-box 0.3.1`), and ASVS Level 1 remediations verified freshly on `strands-box 0.3.1` + full suite (`1843 + 1 = 1844`) + all 6 CI gates at `security_block_on: high`.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| `T-19-01` | Containment Tampering (`write`/`edit` mutating Box config/state) | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/core.py), [policy_gate.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/policy_gate.py) | critical | mitigate | Default storage under `~/.config/strands-box/repos/<id>/` and `~/.local/share/strands-box/repos/<id>/` excluded from `[agent.filesystem].write`; `_is_protected_skills_or_config_path()` downgrades `write`/`edit` on `~/.config/strands-box/**`, `~/.local/share/strands-box/**`, `.agent/policy.toml`, `.agent/routing.yaml`, `.agent/MEMORY.md`, and `STRANDS.md` (incl. symlinks) to `Prompt`; HITL omits `"always"` & blocks dead `[[allow]]` writes; `--out` inside writable paths warns (`self_tamper_risk=True`); see `R-19-02`/`R-19-03`. | closed |
| `T-19-02` | Symlink Clobber / Race on Config & Data Paths | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py) | high | mitigate | `_atomic_write_text()` writes via `tempfile.mkstemp(..., dir=path.parent)` + `os.chmod(0o600)` + `os.replace()` under `0o700` dirs; `_refuse_symlink()` guards target & ancestors on `init`, `doctor`, and `run` (hardened further in `T-19-09`). | closed |
| `T-19-03` | Egress Over-Privilege / Auth Header Leak | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py) | high | mitigate | `bedrock` scopes strictly to `bedrock-runtime.<region>.amazonaws.com` (zero `sts.amazonaws.com`); Google uses `x-goog-api-key`, Anthropic `x-api-key`, OpenAI/Meta/TypeSafe/`decisions_api` `Authorization: Bearer`; `openrouter` path-scopes tokens to `/api/v1/chat/*` & `/api/alpha/decisions` while secret-less `/api/v1/models*` lives solely in `policy.dw`; `--allow-github-skills` keeps `GITHUB_TOKEN`/`GH_TOKEN` strictly on `api.github.com` separate from `codeload`/`objects`. | closed |
| `T-19-04` | Secret Leakage into Config / Diagnostics / Errors | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py) | high | mitigate | Emits symbolic `env://VAR` and `aws://[profile]` refs only; checks presence via `_nonempty()` without printing values; canary-tested across all 9 credential env vars (`toml`, `policy.dw`, `format_doctor_report`); `OMIT`s `HOME` when nested; mounts `~/.cache/strands-code/tmp` instead of `/tmp`. | closed |
| `T-19-05` | TOML / Cedar-Dogwood Injection via Inputs & Env | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py) | high | mitigate | `_reject_control_chars()` rejects ASCII `< 32` & `127` across paths, `--region`, `--aws-profile`, `--provider`, `PATH`, `TERM`, and `XDG_*`; regex validation on region/profile; `_toml_str()` uses `json.dumps()` quoting; `render_policy_dw()` verified against live `strands-box 0.3.1` `box policy generate-schema`. | closed |
| `T-19-06` | `codeact_shell` Bypassing Dogwood Shell Interception / Metacharacter Injection | [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py), [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py) | high | mitigate | Under `STRANDS_BOX=1`, `_codeact_shell_cmd()` wraps list/tuple `argv` via `["sh", "-c", shlex.join(cmd)]` (`shell=False`) while refusing bare string `argv`; metacharacters preserved literally (live `printf` tested); in-workspace `.venv/bin/{pytest,ruff}` tools are skipped without global fallback (`_first_non_writable_tool`), and shebang interpreters are inspected safely (`_shebang_interpreter`); see `R-19-04`. | closed |
| `T-19-07` | Silent Binary Mismatch / AppArmor `userns` `EPERM` / Unset `x86_64` Flag | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py) | medium | mitigate | `discover_box_binaries()` requires co-located `box`, `strands-box-contain-trampoline`, `strands-box-sock-alias` (executable bit verified in `T-19-10`); `run_box_doctor()` diagnoses Linux `x86_64`, AppArmor `userns` sysctl & `/etc/apparmor.d/strands-box`, and box config (exit `1` on failure); `launch_box_run()` auto-exports `EXPERIMENTAL_X86_SUPPORT=TRUE` on `x86_64`. | closed |
| `T-19-08` | Test Env Bleed / Import Cycle / Policy & Vocab Invariants | [conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py), [dispatch/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py) | medium | mitigate | `conftest.py` scrubs `STRANDS_BOX`, `STRANDS_BOX_BIN`, and `EXPERIMENTAL_X86_SUPPORT`; zero `entry.main` imports in `sandbox/box.py` (`lint-imports` clean); zero `os.environ` or forbidden vocabulary in `dispatch/core.py`; `box` subcommands bypass REPL `_preflight_credentials()` via `ctx.invoked_subcommand`. | closed |
| `T-19-09` | Ancestor / Pre-`realpath` Symlink Clobber & Unvalidated `launch_box_run` `box_dir`/TOML | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py#L175-L185) (`_refuse_symlink`, `_resolve_code_dirs`, `_validate_launch_config`, `_validate_launch_box_dir`) | **high** | mitigate | **Discovered & remediated in this audit:** extended `_refuse_symlink()` to walk `max_ancestors=2` (blocking symlinked `~/.config/strands-box` and `~/.config/strands-box/repos`); moved `_refuse_symlink()` checks inside `_resolve_code_dirs()` *before* `os.path.realpath()` so symlinked `~/.config/strands-code` / `~/.cache/strands-code` refuse before `chmod`; replaced `except Exception:` in `launch_box_run()` with fail-closed `_validate_launch_config()` + `_validate_launch_box_dir()` validating `box.toml`, symlinked custom `policy` paths, and refusing relative, control-char, root, or `$HOME`-parent `box_dir` values before `_ensure_dir()`. | closed |
| `T-19-10` | `git -C` Push MFOTL Bypass / Non-Exec Binary Layout / Defense-in-Depth Box `policy.dw` | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py#L985-L1034) (`render_policy_dw`, `discover_box_binaries`) | **high** | mitigate | **Discovered & remediated in this audit:** widened `push_requires_recent_tests` in `policy.dw` to match `arg1 == "push"`, `arg2 == "push"`, `command like "* push"`, and `command like "* push *"` (blocking `git -C . push` / `git -c k=v push` / `git --no-pager push` without a prior passing `pytest`); added Dogwood `forbid_box_config_write`, `forbid_box_config_delete`, and `forbid_box_config_move` on `*/.config/strands-box/*` and `*/.local/share/strands-box/*`; enforced control-char rejection and `os.X_OK` on `box` and both co-located helpers in `discover_box_binaries()`. | closed |
| `T-19-11` | Malformed `XDG_*` Env Propagation & Complexity / Upstream Scope Boundaries | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py#L813-L826) (`_render_agent_env`) | **medium** | mitigate | **Discovered & remediated in this audit:** filtered `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` in `_render_agent_env()` to reject relative or refused-root values alongside control chars; maintained `D-24` pristine `strands_code_agent/` and `box.py` max `radon C (16)` (`R-19-01`). | closed |

*Status: `open` · `closed`*
*Severity: `critical` > `high` > `medium` > `low` — only `open` threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: `mitigate` (implementation verified) · `accept` (documented risk) · `transfer` (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| `R-19-01` | `T-19-11` | Phase 19 preserves `D-24` (`git diff ee42ea2 -- strands_code_agent/` empty) and keeps `box.py` at max `C (16)` (`_render_agent_env`), leaving complexity-ceiling functions (`save_strategy`, `_setup_decision_entries`, `price_table`, `_check_explicit_provider`) untouched until Phase 23 refactoring. | secure-phase L1 audit | 2026-11-25 |
| `R-19-02` | `T-19-01` | Self-hosting `strands-code` inside its own source repo leaves `.venv/` inside the writable workspace grant (`strands-box` emits explicit self-writable `.venv` warnings, as observed in live `box run -- --help`); normal usage targeting external repos keeps `.venv` outside the target repo's write grant. | secure-phase L1 audit | 2026-11-25 |
| `R-19-03` | `T-19-01` | Repo files `.agent/policy.toml`, `.agent/routing.yaml`, `.agent/MEMORY.md`, and `STRANDS.md` remain writable to the `strands-code` CLI process inside Box so interactive `"Always"`/`"Never"`, `/route setup`, and `/memory` work; in-session agent `write`/`edit` tools are gated via `policy/core.py` `Prompt` downgrades + dead-`"Always"` HITL blocking (broader `.agent/` hardening & `PolicyGateHandler` move into Phase 19.1 `HARDEN-01`). | secure-phase L1 audit | 2026-11-25 |
| `R-19-04` | `T-19-06` | `[tool.python]` is omitted from `box.toml` (leaving `strands-box`'s default `monty = true` warning-free) until Phase 20 (`SANDBOX-02`) integrates `pydantic-monty` and evaluates embedded-Monty vs `monty = false` Dogwood event-log alignment. | secure-phase L1 audit | 2026-11-25 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-25 | 11 | 11 | 0 | `gsd-secure-phase` ASVS L1 audit (discovered & closed `T-19-09` HIGH ancestor/pre-`realpath` symlink refusal + fail-closed `launch_box_run()` config/`policy`/`box_dir` validation, `T-19-10` HIGH `git` flag-before-`push` MFOTL coverage + Dogwood `forbid_box_config_*` rules + `os.X_OK`/control-char checks in `discover_box_binaries()`, and `T-19-11` MEDIUM absolute/non-root `XDG_*` filtering in `_render_agent_env()`; verified after final edits: `ruff format --check` `128 files already formatted`, `ruff check` `All checks passed!`, `xenon --max-absolute C` `exit 0` with `box.py` max `C (16)`, `lint-imports` `1 kept, 0 broken`, `uv lock --check` `Resolved 156 packages`, `pytest tests/sandbox/` `30 passed`, `pytest -m integration tests/sandbox/test_box.py` `1 passed, 20 deselected` in `7.46s` against live `strands-box 0.3.1` + real `CLONE_NEWUSER`, `pytest tests/rig/` `44 passed`, full non-integration suite `1843 passed, 16 deselected` + loopback stub `1 passed` = `1844/1844` green, `git diff ee42ea2 -- strands_code_agent/` empty; `19-UAT.md` `6/6` passed) |

---

## Sign-Off

- [x] All threats have a disposition (`mitigate` / `accept` / `transfer`)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-25
