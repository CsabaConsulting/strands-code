---
phase: "19"
slug: "strands-box-linux-sandbox-floor-dogwood-policy"
status: verified
nyquist_compliant: false
wave_0_complete: true
created: "2026-11-25"
verified: "2026-11-25"
---

# Phase 19 — Validation Strategy

> Per-phase Nyquist validation contract for feedback sampling during Phase 19 execution (`SANDBOX-01`).

---

## Test Infrastructure

| Property | Value |
| :--- | :--- |
| **Framework** | `pytest` (installed in `.venv`) via `/home/csaba/.local/bin/uv run pytest` or `.venv/bin/pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `.venv/bin/pytest tests/sandbox/ tests/policy/test_codeact.py tests/policy/test_policy.py -q` |
| **Full suite command** | `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` + standalone `test_stub_server_systemone_decision_routes` |
| **Static / complexity gates** | `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check` |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted verification command (`< 25s`).
- **After every plan wave:** Run `.venv/bin/pytest tests/sandbox/ tests/policy/ tests/dispatch/ tests/entry/ tests/cost/test_cost_context.py -q` + `ruff check` + `ruff format --check` + `xenon --max-absolute C` + `lint-imports`.
- **Before `/gsd-verify-work 19`:** All 6 CI workflow checks must pass cleanly (`strands_code_agent/` diff empty).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Decision / Anchor | Secure / Correct Behavior | Test Type | Automated Command | File Exists | Status |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `19-01-T1` | 01 | 1 | `SANDBOX-01` | `D-02`–`D-05`, `T-19-01`–`T-19-04` | `strands_code_cli/sandbox/box.py` + `tests/conftest.py` (`STRANDS_BOX_BIN`, `EXPERIMENTAL_X86_SUPPORT`): host-only `~/.config/strands-box/repos/<slug>-<hash8>/` (`0o700`/`0o600`, symlink-refused), valid `tomllib.loads()` `box.toml`, `uv`/`.venv` realpath resolution, least-privilege auto-detected 7+2 egress profiles (no STS hole, path-scoped OpenRouter), default-deny `policy.dw` with `.env`/`.ssh`/`.aws` read forbids and canonical MFOTL temporal `git push*` rule (`f5a8ac6`) | unit (TDD RED→GREEN, Wave 0 file) | `.venv/bin/pytest tests/sandbox/test_box.py -q && .venv/bin/ruff check strands_code_cli/sandbox tests/conftest.py tests/sandbox && .venv/bin/xenon --max-absolute C strands_code_cli/sandbox tests/sandbox && .venv/bin/lint-imports` | ✅ | ✅ green |
| `19-01-T2` | 01 | 1 | `SANDBOX-01` | `T-19-01`–`T-19-08`, `D-07` | Adversarial & Linux diagnostics: `--out` self-tamper warning, symlink clobber refusal on init/run, TOML/Dogwood control-char & quote rejection, canary secret zero-leakage across all 7+2 providers, 3-binary co-location (`box`, `trampoline`, `sock-alias`), Linux `x86_64` `EXPERIMENTAL_X86_SUPPORT=TRUE` doctor/run checks, Ubuntu 24.04 AppArmor `userns` sysctl/profile diagnostics (`f5a8ac6`, `95 passed`) | security unit | `.venv/bin/pytest tests/sandbox/ tests/cost/test_cost_context.py -k "not nonexistent" -q && .venv/bin/ruff check strands_code_cli/sandbox tests/sandbox && .venv/bin/xenon --max-absolute C strands_code_cli/sandbox tests/sandbox && .venv/bin/lint-imports` | ✅ | ✅ green |
| `19-02-T1` | 02 | 2 | `SANDBOX-01` | `D-01`, `D-02`, `D-06`, `T-19-06`, `T-19-08` | `codeact_shell` `["sh", "-c", shlex.join(argv)]` routing under `STRANDS_BOX=1` (preserving unboxed direct argv & quoting metacharacters), `user_config_dir("strands-box")` protected-path `Prompt` downgrade in `policy/core.py:decide()`, and read-only `Sandbox: Strands Box active (STRANDS_BOX=1)` in `_policy_message()` (`10ef216`) | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/policy/ tests/dispatch/ tests/sandbox/ tests/cost/test_cost_context.py -q && .venv/bin/ruff check strands_code_cli/policy strands_code_cli/dispatch tests/policy tests/sandbox && .venv/bin/xenon --max-absolute C strands_code_cli/policy strands_code_cli/dispatch tests/policy tests/sandbox && .venv/bin/lint-imports` | ✅ | ✅ green |
| `19-02-T2` | 02 | 2 | `SANDBOX-01` | `D-01`, `D-07`, `T-19-08` | Typer subcommand group `strands-code box init|doctor|run` in `entry/main.py` (`ctx.invoked_subcommand` early exit preserving bare REPL & `--codeact --` args; zero `os.environ` in `entry/main.py`) + end-to-end `CliRunner` tests in `tests/sandbox/test_box_cli.py` (`10ef216`, `541 passed`) | unit + CLI integration | `.venv/bin/pytest tests/sandbox/ tests/entry/ tests/dispatch/ tests/policy/ tests/cost/test_cost_context.py -q && .venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports` | ✅ | ✅ green |
| `19-03-T1` | 03 | 3 | `SANDBOX-01` | `D-07` | Added `@pytest.mark.integration` host `dogwood` / `box` validation probe in `tests/sandbox/test_box.py` (`1 skipped, 19 deselected` when host binaries absent) and verified `tests/sandbox/ tests/rig/` (`63 passed, 1 deselected`; `44` rig contracts) (`dbddce8`) | integration + rig contract | `.venv/bin/pytest tests/sandbox/ tests/rig/ -q && .venv/bin/pytest tests/sandbox/ -m integration -v && .venv/bin/ruff check tests/sandbox/test_box.py && .venv/bin/xenon --max-absolute C tests/sandbox/test_box.py` | ✅ | ✅ green |
| `19-03-T2` | 03 | 3 | `SANDBOX-01` | `D-01`–`D-07` + Gates | Documented Strands Box Linux setup in `docs/QUICKSTART.md` + passed all 6 CI gates (`128 files already formatted`, `Contracts: 1 kept, 0 broken`, `Resolved 156 packages`, `strands_code_agent/` diff empty) + `1820 passed` + standalone loopback stub (`1 passed`; combined `1821 passed`) (`dbddce8`) | docs + full CI gates | `.venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports && /home/csaba/.local/bin/uv lock --check && .venv/bin/pytest tests/rig/ -q && .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q && git diff ee42ea2 -- strands_code_agent/` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- `tests/sandbox/test_box.py` — created TDD-first in Plan `19-01` Task 1 (`19-01-T1`) and hardened in `19-01-T2` covering host-only `box.toml`/`policy.dw` persistence, `tomllib` schema validity, `uv`/`.venv` realpaths, all 7 core + 2 opt-in egress profiles, canonical Dogwood MFOTL temporal `git push*` rule, `--out` self-tamper warnings, symlink refusal, canary secret zero-leakage, TOML/Cedar injection rejections, Linux 3-binary co-location, `x86_64` `EXPERIMENTAL_X86_SUPPORT=TRUE`, and Ubuntu 24.04 AppArmor diagnostics (`test_host_strands_box_or_dogwood_validates_generated_policy` added in `19-03-T1` under `@pytest.mark.integration`).

---

## Manual / Opportunistic Live Verifications

| Behavior | Requirement | Why Host Binaries / Kernel Required | Test Instructions | Status |
| :--- | :--- | :--- | :--- | :--- |
| Host `dogwood validate` / `box run` check against generated `policy.dw` & `box.toml` | `SANDBOX-01` | Requires external `box` / `dogwood` Rust binaries and unprivileged `userns` support on host Linux kernel | `.venv/bin/pytest tests/sandbox/test_box.py -m integration -v` *(skips cleanly via `pytest.skip` when binaries are not installed)* | ⬜ pending |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with TDD / automated verification
- [x] Wave 0 gaps identified (`tests/sandbox/test_box.py` in `19-01-T1`)
- [x] No watch-mode flags
- [x] Fast feedback latency (`< 25s` per targeted verification run)
- [ ] `nyquist_compliant: true` audited post-execution

**Approval:** pending execution
