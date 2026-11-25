---
phase: 19-strands-box-linux-sandbox-floor-dogwood-policy
verified: 2026-11-25
status: passed
score: 12/12
requirement: SANDBOX-01
live_probes:
  - target: host dogwood validate & strands-box run (--help)
    result: 1 skipped, 19 deselected in 2.43s (host box/dogwood binaries absent on dev machine; deselected by default)
ci_gates:
  - ruff format --check strands_code_cli tests scripts: 128 files already formatted
  - ruff check strands_code_cli tests scripts: All checks passed!
  - xenon --max-absolute C strands_code_cli tests scripts: passed
  - lint-imports: Contracts 1 kept, 0 broken (43 files, 97 dependencies)
  - uv lock --check: Resolved 156 packages in 3ms
  - git diff ee42ea2 -- strands_code_agent/: empty
---

# Phase 19 Goal-Backward Verification (`SANDBOX-01`)

**Status:** `PASS` (`12/12` must-have truths verified across Waves 1–3)

---

## Goal-Backward Verification Matrix

| # | Observable / Structural Truth | Code & Test Evidence | Result |
|---:|---|---|---|
| 1 | Host-only repo-scoped storage (`~/.config/strands-box/repos/<slug>-<hash8>/`, `0o700`/`0o600`, symlink-refused) with `box_dir` under `~/.local/share/strands-box/repos/<slug>-<hash8>/`, completely excluded from `[agent.filesystem].write` | [box.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/sandbox/box.py) (`default_box_config_dir`, `default_box_data_dir`, `_atomic_write_0600`), [test_box.py](file:///home/csaba/repos/AWS/strands-code/tests/sandbox/test_box.py) (`TestSandboxSecurityAndDiagnostics`) | PASS |
| 2 | Valid `tomllib`-parsed `box.toml` sets `STRANDS_BOX="1"`, `TERM`, `HOME`, `PATH`, resolves `.venv` / `sys.executable.resolve()` / `~/.local/share/uv/python`, and never embeds raw API keys into `[agent.env]` | `box.py` (`resolve_runtime_paths`, `_render_agent_env`, `render_box_toml`), `test_box.py` (canary secret zero-leakage & `tomllib.loads` checks across all 7+2 providers) | PASS |
| 3 | Least-privilege egress profiles for all 7 core providers (`bedrock` SigV4/bearer without `sts.amazonaws.com`, `google` `x-goog-api-key`, `anthropic` `x-api-key`, `openai`, `meta`, path-scoped `openrouter` `/api/v1/chat/*` + `/api/alpha/decisions`, `typesafe`) + opt-ins (`--allow-decisions-api`, `--allow-github-skills` with `api.github.com`-only token) | `box.py` (`detect_active_providers`, `_egress_specs_for_providers`, `_bedrock_egress_spec`, `_github_egress_specs`), `test_box.py` (`CORE_PROVIDERS`, `OPTIONAL_PROFILES`, opt-in isolation checks) | PASS |
| 4 | Default-deny Dogwood `policy.dw` forbids `fs:read` on `*/.env`, `*/.env.*`, `*/.ssh/*`, `*/.aws/*`, permits non-push dev tools (`pytest`, `rg`, `ruff`, `uv`, `python`, non-push `git`), and enforces canonical MFOTL rule `push_requires_recent_tests` (`formerly within 900s` `pytest`) with formal scoped `v2.0` `D-05` revisit header | `box.py` (`render_policy_dw`, `_egress_dw_rules`), `test_box.py` | PASS |
| 5 | Adversarial input & tampering guards: `--out` writable-path warning, symlink clobber refusal on `init`/`run`, control-char & TOML/Cedar quote injection rejection | `box.py` (`_refuse_symlink`, `_reject_control_chars`, `_is_writable_target`, `init_box_config`), `test_box.py` | PASS |
| 6 | Linux 3-binary layout (`box`, `strands-box-contain-trampoline`, `strands-box-sock-alias`), `x86_64` `EXPERIMENTAL_X86_SUPPORT=TRUE` doctor/run handling, and Ubuntu 24.04 AppArmor `userns` sysctl + `/etc/apparmor.d/strands-box` remediation diagnostics | `box.py` (`discover_box_binaries`, `run_box_doctor`, `format_doctor_report`, `launch_box_run`, `APPARMOR_PROFILE_SNIPPET`), `test_box.py` | PASS |
| 7 | Under `STRANDS_BOX=1`, `codeact_shell` routes argv invocations through `["sh", "-c", shlex.join(argv)]` preserving metacharacter quoting while unboxed runs direct argv (`shell=False`) | [codeact.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/codeact.py) (`_codeact_shell_cmd`, `codeact_shell`), [test_codeact.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_codeact.py) | PASS |
| 8 | Broad `allow` write/edit rules targeting `~/.config/strands-box/**` (including workspace symlink escapes) downgrade to `Prompt` | [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/core.py) (`_is_protected_skills_or_config_path`), [test_policy.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_policy.py) | PASS |
| 9 | `/policy` and `/policy show` display `"Sandbox: Strands Box active (STRANDS_BOX=1)"` when `STRANDS_BOX=1` without `os.environ` or forbidden vocabulary in `dispatch/core.py` | [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py) (`_policy_message`), [test_box_cli.py](file:///home/csaba/repos/AWS/strands-code/tests/sandbox/test_box_cli.py), [test_cost_context.py](file:///home/csaba/repos/AWS/strands-code/tests/cost/test_cost_context.py) | PASS |
| 10 | `strands-code box init|doctor|run` Typer subcommand group skips REPL `_preflight_credentials()` via `ctx.invoked_subcommand`, forwards `--` args, and preserves bare `strands-code` / `--codeact` / `--model` / `--session-id` | `box.py` (`build_box_app`, `box_app`), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py) (`_root`), `test_box_cli.py` | PASS |
| 11 | Hermetic test env scrub (`STRANDS_BOX_BIN`, `EXPERIMENTAL_X86_SUPPORT`), opt-in `@pytest.mark.integration` host `dogwood`/`box` probe (`pytest.skip` when absent), and `docs/QUICKSTART.md` Linux/AppArmor/egress guide | [conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py), `test_box.py`, [QUICKSTART.md](file:///home/csaba/repos/AWS/strands-code/docs/QUICKSTART.md) | PASS |
| 12 | All 6 CI gates, `tests/rig/` (`44/44`), full non-integration suite (`1820 + 1 = 1821 passed`), and `strands_code_agent/` untouched (`D-24`) | Commits `f5a8ac6`, `10ef216`, `dbddce8` — see verified command outputs below | PASS |

---

## Verified Test & Gate Outputs

- **Default non-integration suite:** `uv run pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` -> **1820 passed, 16 deselected** in 70.41s
- **Standalone loopback stub:** `uv run pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` -> **1 passed, 195 deselected** in 2.24s (combined default total: **1821 passed**)
- **Sandbox unit/CLI + Rig suite:** `uv run pytest tests/sandbox/ tests/rig/ -q` -> **63 passed, 1 deselected** (`19` sandbox + `44` rig) in 2.45s
- **Opportunistic host Box/Dogwood probe:** `uv run pytest tests/sandbox/ -m integration -v` -> **1 skipped, 19 deselected** in 2.43s (`Host Strands Box / Dogwood binaries not installed`)
- **Formatting & Lint:** `uv run ruff format --check strands_code_cli tests scripts` -> **128 files already formatted**; `uv run ruff check strands_code_cli tests scripts` -> **All checks passed!**
- **Complexity & Architecture:** `uv run xenon --max-absolute C strands_code_cli tests scripts` -> **passed** (`box.py` max `C 15`); `uv run lint-imports` -> **Contracts: 1 kept, 0 broken** (`43 files, 97 dependencies`); `uv lock --check` -> **Resolved 156 packages in 3ms**; `git diff ee42ea2 -- strands_code_agent/` -> **empty**.
