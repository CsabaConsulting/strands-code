---
status: complete
phase: 19-strands-box-linux-sandbox-floor-dogwood-policy
source: [19-01-SUMMARY.md, 19-02-SUMMARY.md, 19-03-SUMMARY.md, 19-VERIFICATION.md]
started: 2026-11-25T01:20:00Z
updated: 2026-11-26T01:46:00Z
---

# Phase 19 User Acceptance Testing (`SANDBOX-01`)

## Current Test

[testing complete]

## Tests

### 1. Host-Only Repo Config Generation, Permissions, `uv` Realpaths & Symlink/Self-Tamper Guards (`D-01`, `D-02`, `D-03`, `T-19-01`, `T-19-02`, `T-19-07`)
expected: Running `strands-code box init` skips REPL credential preflight, writes repo-scoped `box.toml` and `policy.dw` host-only under `~/.config/strands-box/repos/<slug>-<hash8>/` (`0o700` dirs, `0o600` files) outside `[agent.filesystem].write`, produces `tomllib`-valid `box.toml` with `STRANDS_BOX="1"` + resolved `uv`/`.venv` Python realpaths, warns when `--out` targets a writable repo directory, and refuses symlink clobber targets or control-char/injected `--region` values (exit code 1).
result: pass
evidence:
- Re-verified on `HEAD` `edbe4ce` and aligned with live `strands-box 0.3.1` in `679c874` / `87c1564`:
  - `1a`: skipped REPL credential preflight (`rc=0`); wrote `0o700` repo config dir & `0o600` `box.toml`/`policy.dw` and pre-created `box_dir.parent` (`~/.local/share/strands-box/repos/`) + `~/.config/strands-code` + `~/.cache/strands-code/tmp`; `tomllib.loads` valid with `sc-<slug>-<hash8>` `name` (`<= 32` bytes), `STRANDS_BOX="1"`, `TMPDIR` under `~/.cache/strands-code/tmp`, `HOME` omitted from `[agent.env]`, coalesced canonical non-root `read` grants (including multiarch shared-lib dir), writable in-workspace tools excluded / shebang interpreters resolved, and canonical `exec` grants (including `lib-dynload`/`site-packages`, `/usr/bin/python3.12` realpath, and `.venv/bin/strands-code`); real-`$HOME` `default_box_config_dir` confirmed outside `[agent.filesystem].write`.
  - `1b`: `--out` inside writable repo dir exited `0` with single `Warning:` prefix (`Warning: Warning:` resolved).
  - `1c`: symlink clobber target exited `1`, left `sentinel.txt` untouched, and printed `Error: Refusing symlink box.toml: <path>` cleanly (duplicated path resolved).
  - `1d`: control-char / TOML-injected `--region` exited `1` (`Error: Invalid control character in AWS region`).

### 2. Auto-Detected 8-Provider Egress Profiles, Unauthenticated OpenRouter Models, Opt-In Flags & Zero Secret Embedding (`D-04`, `T-19-03`, `T-19-04`)
expected: `init_box_config` / `strands-code box init` auto-detects and cleanly renders least-privilege egress specs for all 8 core providers (`bedrock` SigV4 without `sts.amazonaws.com`, `google` `x-goog-api-key`, `anthropic` `x-api-key`, `openai`, `meta`, path-scoped `openrouter` `/api/v1/chat/*` + `/api/alpha/decisions` plus policy-only unauthenticated `openrouter_models` `/api/v1/models*`, `typesafe`, `decisions_api` `decisionapi.net` after `typesafe`) plus `--allow-decisions-api` force-enable override (when `JEV_API_KEY` / `routing.yaml` are absent) and opt-in `--allow-github-skills` (`api.github.com`-only token separate from `codeload`/`objects`), while embedding zero canary API key strings anywhere in `box.toml` or `policy.dw`.
result: pass
evidence:
- Executed via isolated `strands-code box init` probe on `edbe4ce` (user accepted `pass` 2026-11-25T22:29Z) and verified end-to-end against live `strands-box 0.3.1` in `679c874`:
  - `2a`: zero opt-in flags enabled `bedrock, google, anthropic, openai, meta, openrouter, typesafe, decisions_api` in order, kept secret-less `openrouter.ai/api/v1/models*` in `policy.dw` only (never `[egress.*]` in `box.toml`), omitted `sts.amazonaws.com` & `github_api`/`github_downloads`, and leaked zero canary secrets.
  - `2b`: `--allow-decisions-api --allow-github-skills` enabled `bedrock, decisions_api, github_skills`, kept `GITHUB_TOKEN` strictly on `api.github.com` in `box.toml` with unauthenticated `codeload.github.com`/`objects.githubusercontent.com` in `policy.dw` only, and leaked zero canary secrets.

### 3. Default-Deny Dogwood `policy.dw`, `.env`/Secret Read Forbids & Canonical MFOTL Temporal `git push` Rule (`D-05`, `T-19-05`)
expected: Generated `policy.dw` declares default-deny semantics (`forbid` overrides `permit`), blocks `fs:read` on `*/.env`, `*/.env.*`, `*/.ssh/*`, and `*/.aws/*`, permits non-push dev tools (`["pytest", "rg", "ruff", "uv", "python", "git"].contains(context.input.program)`), enforces the canonical MFOTL rule `push_requires_recent_tests` (`forbid` on `context.input.program == "git"` + `arg1 == "push"` `unless temporal` `formerly within 900s` passing `pytest` `shell:spawn::response` with `output.status: 0`), validates cleanly under `strands-box 0.3.1`, and records the formal scoped `v2.0` revisit of `D-05`.
result: pass
evidence:
- Verified on `HEAD` `87c1564` via user's live `strands-box 0.3.1` run (`strands-code box init && strands-code box doctor && strands-code box run -- --help` → `Status: READY`, live sandbox `box-744ca6c63fc78ee7` started with zero config/policy/schema errors) and `@pytest.mark.integration` `box policy generate-schema`:
  - `render_policy_dw()` declares default-deny (`forbid` overrides `permit`) and formal scoped `v2.0` `D-05` revisit header.
  - `forbid_sensitive_files_read` blocks `fs:read` on `*/.env`, `*/.env.*`, `*/.ssh/*`, and `*/.aws/*`.
  - `allow_dev_tools` permits `shell:spawn` for `["pytest", "rg", "ruff", "uv", "python", "git"].contains(context.input.program)`.
  - `push_requires_recent_tests` enforces `forbid` on `context.input.program == "git"` + `arg1 == "push"` `unless temporal { formerly within 900s ( Box::Action::"shell:spawn"::response { input.program: "pytest", output.status: 0 } ) }`.

### 4. Linux Diagnostics (`strands-code box doctor`) & Launch Wrapper (`strands-code box run -- ...`) (`D-01`, `D-07`)
expected: `strands-code box doctor` verifies the 3 co-located binaries (`box`, `strands-box-contain-trampoline`, `strands-box-sock-alias`), Linux `x86_64` `EXPERIMENTAL_X86_SUPPORT=TRUE`, and Ubuntu 24.04 AppArmor `userns` sysctl + `/etc/apparmor.d/strands-box` profile (returning exit `0` / `Status: READY` when satisfied and exit `1` with actionable remediation when failing); `strands-code box run -- --codeact --model ...` exports `EXPERIMENTAL_X86_SUPPORT=TRUE` on `x86_64` and forwards `--` arguments while refusing symlinks and missing binaries.
result: pass
evidence:
- Verified via live host run (`box doctor` → all 6 `[OK]`, `Status: READY`; `box run -- --help` → live `box-744ca6c63fc78ee7` launch), isolated probe (`probe_test4.py`), and unit suite (`4 passed`):
  - `4a`: `box doctor` exits `0` with `Status: READY` when the 3 co-located binaries (`box`, `strands-box-contain-trampoline`, `strands-box-sock-alias`), `EXPERIMENTAL_X86_SUPPORT=TRUE`, AppArmor `userns` profile, and valid config are present.
  - `4b`: `box doctor` exits `1` with `Status: ACTION REQUIRED` and remediation when sibling binaries are missing, `EXPERIMENTAL_X86_SUPPORT=TRUE` is unset on `x86_64`, or Ubuntu AppArmor sysctl=`1` lacks `/etc/apparmor.d/strands-box` (`userns,`).
  - `4c`: `launch_box_run` and `CliRunner` `box run -- --codeact --model google/gemini-3.8-flash` auto-export `EXPERIMENTAL_X86_SUPPORT=TRUE` on `x86_64` and forward `["run", "--config", ..., "--", "--codeact", "--model", "google/gemini-3.8-flash"]`.
  - `4d`: `box run` refuses symlink `--config` targets and incomplete/missing binary layouts with exit code `1`.

### 5. Boxed Runtime Alignment: `STRANDS_BOX=1` `codeact_shell` `sh -c`, Protected Path `Prompt` Downgrades, Dead-`Always` Guard & `/policy` Indicator (`D-01`, `D-02`, `D-06`, `T-19-06`, `T-19-08`)
expected: Under `STRANDS_BOX=1`, `codeact_shell` executes commands via `["sh", "-c", shlex.join(cmd)]` preserving metacharacter quoting while unboxed uses direct argv; `policy/core.py:decide()` downgrades broad `allow` write/edit rules targeting `~/.config/strands-box/**`, `~/.local/share/strands-box/**`, `.agent/policy.toml`, `.agent/routing.yaml`, `.agent/MEMORY.md`, and `STRANDS.md` (including workspace symlink escapes) to `Prompt`; HITL prompts on those protected paths omit `"Always"` and block persisting dead `[[allow]]` rules while preserving `"Never"`; `/policy` and `/policy show` display `"Sandbox: Strands Box active (STRANDS_BOX=1)"` without forbidden vocabulary; bare `strands-code` REPL launches cleanly without regression.
result: pass
evidence:
- Verified via isolated probe (`probe_test5.py`) and matching unit tests (`11 passed`):
  - `5a`: under `STRANDS_BOX=1`, `codeact_shell()` wraps via `["sh", "-c", shlex.join(cmd)]` preserving metacharacter quoting (`printf` literal payload without executing shell metacharacters), while unboxed calls use direct argv.
  - `5b`: `policy/core.py:decide()` downgrades `write`/`edit` under `[[allow]] tool="*" path="*"` to `Prompt` (keeping `read` as `Allow` and explicit `deny` as `Deny`) across `~/.config/strands-box/**`, `~/.local/share/strands-box/**`, workspace symlink escapes to both, `.agent/policy.toml`, `.agent/routing.yaml`, `.agent/MEMORY.md`, and `STRANDS.md`.
  - `5c`: HITL omits `"always"` in TTY `radio_choice` (`["y", "n", "never"]`), blocks persisting dead `[[allow]]` rules on non-TTY `"always"` input, and preserves `"never"` (`[[deny]]` persisted).
  - `5d`: `/policy` and `/policy show` display `"Sandbox: Strands Box active (STRANDS_BOX=1)"` with zero banned vocabulary and omit the line when unboxed.
  - `5e`: bare `strands-code --codeact code --model openai/gpt-4o` (`CliRunner`) and `.venv/bin/strands-code --help` launch cleanly.

### 6. Documentation (`docs/QUICKSTART.md`), Full Test Suite (`1839` + Host Integration), Rig Contracts (`44/44`) & All 6 CI Gates on `HEAD` (`D-07`, `D-24`)
expected: `docs/QUICKSTART.md` (`## Strands Box Linux sandbox floor`) documents 3-binary installation (`install.sh`, `download.sh`, Cargo), `EXPERIMENTAL_X86_SUPPORT=TRUE`, `/etc/apparmor.d/strands-box`, `box init|doctor|run`, `8+1` egress table (`decisions_api` auto-detected, policy-only secret-less targets, `TMPDIR` under `~/.cache/strands-code/tmp`), Dogwood temporal `git push` rule (`forbid ... unless temporal` with `output.status: 0`), and `codeact_shell` alignment; all 6 CI gates (`ruff format --check`, `ruff check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check`, empty `git diff ee42ea2 -- strands_code_agent/`), `tests/rig/` (`44/44`), `@pytest.mark.integration` live `strands-box 0.3.1` host check, and complete `1838 + 1 = 1839` unit suite pass on `HEAD`.
result: pass
evidence:
- Verified on `HEAD` `87c1564`:
  - `6a`: `docs/QUICKSTART.md` (`## Strands Box Linux sandbox floor`, lines 352–429) covers 3-binary installation (`install.sh`, `download.sh`, Cargo), `EXPERIMENTAL_X86_SUPPORT=TRUE`, `/etc/apparmor.d/strands-box` (`userns,`), `box init|doctor|run`, `TMPDIR=~/.cache/strands-code/tmp`, policy-only secret-less targets, `/policy` indicator, `codeact_shell` `sh -c` alignment, `8+1` egress table (`decisions_api` auto-detected after `typesafe`, `--allow-github-skills` opt-in), Dogwood temporal `git push` rule (`forbid ... unless temporal` with `output.status: 0`), and scoped `v2.0` `D-05` revisit.
  - `6b`: all 6 CI gates passed (`ruff format --check` `128 files already formatted`, `ruff check` `All checks passed!`, `xenon --max-absolute C` exit `0`, `lint-imports` `1 kept, 0 broken`, `uv lock --check` `156 packages`, `git diff ee42ea2 -- strands_code_agent/` empty).
  - `6c`: `tests/rig/` → `44 passed`.
  - `6d`: full non-integration unit suite → `1838 + 1 = 1839 passed` (`1838 passed, 16 deselected` sandboxed + `test_stub_server_systemone_decision_routes` `1 passed` with loopback access).
  - `6e`: `@pytest.mark.integration` live `strands-box 0.3.1` host check (`tests/sandbox/test_box.py`) → `1 passed, 15 deselected` (isolated fixture repo + self-hosting `.venv/bin/strands-code --help` in real `CLONE_NEWUSER`).

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
