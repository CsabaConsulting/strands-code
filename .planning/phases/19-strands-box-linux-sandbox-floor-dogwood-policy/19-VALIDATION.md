---
phase: "19"
slug: "strands-box-linux-sandbox-floor-dogwood-policy"
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-25"
verified: "2026-11-25"
validated: "2026-11-25"
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
| `19-UAT-T1` | uat | 4 | `SANDBOX-01` | `D-01`–`D-07` | Full `6/6` interactive & live UAT (`19-UAT.md`, `1db18e8`) + live `strands-box 0.3.1` alignment fixes (`679c874`, `87c1564`): 8-provider Box auto-detect (`decisions_api`), 32-byte `sc-<slug[:20]>-<hash8>` box name, `TMPDIR=~/.cache/strands-code/tmp`, multiarch lib read + `lib-dynload`/`site-packages` exec, shebang interpreter resolution, writable in-workspace tool skip, `[tool.python]` omitted until Phase 20, `forbid ... unless temporal` `output.status: 0` MFOTL rule, plus live `strands-box 0.3.1` `box policy generate-schema` and `box run -- --help` on isolated & self-hosting repos | live UAT + host `strands-box` | `19-UAT.md` (`6/6 PASS`) + `.venv/bin/pytest -m integration tests/sandbox/test_box.py -q` (`1 passed`) + `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` | ✅ | ✅ green (`1db18e8`) |
| `19-SEC-T1` | sec | 4 | `SANDBOX-01` | `T-19-01`–`T-19-11` | ASVS L1 security audit (`19-SECURITY.md`, `11/11 closed`, `threats_open: 0`, `9ac28d3`): closed `T-19-09` (ancestor `max_ancestors=2` + pre-`realpath` `_resolve_code_dirs()` symlink refusal + fail-closed `_validate_launch_config()` / `_validate_launch_box_dir()` checks), `T-19-10` (`git` flag-before-`push` MFOTL rules + Dogwood `forbid_box_config_write`/`delete`/`move` rules + `os.X_OK`/control-char checks in `discover_box_binaries()`), and `T-19-11` (`XDG_*` absolute/non-root validation in `_render_agent_env()`) | security unit + live integration + CI gates | `.venv/bin/pytest tests/sandbox/ -q` (`30 passed`) + `.venv/bin/pytest -m integration tests/sandbox/test_box.py -q` (`1 passed` in `7.46s`) + full suite (`1843+1`) + `44/44` rig + `6/6` CI gates | ✅ | ✅ green (`9ac28d3`) |
| `19-VAL-T1` | val | 4 | `SANDBOX-01` | `D-01`–`D-07`, `T-19-01`–`T-19-11` | Retroactive Nyquist edge-branch coverage (**zero runtime edits**, `git diff 9ac28d3 -- strands_code_cli/ strands_code_agent/` empty; `sys.monitoring`: `box.py` **1178/1180 = 99.8%** executable lines — `100.0%` of Python 3.12 reachable lines, excluding only Python 3.10 `tomllib` import fallback lines `26-27`; `sandbox/__init__.py` **1/1 = 100.0%**; **100.0%** on Phase 19 integration seams in `policy/codeact.py` `[8/8]`, `policy/core.py` `[2/2]`, `dispatch/core.py` `[4/4]`, and `entry/main.py` `[7/7]`): `_shebang_interpreter` `OSError`/whitespace-only, `_atomic_write_text` `os.replace` failure tmp cleanup, `_valid_nonroot_dir(None)`, `_resolve_venv_dir` no-venv fallback, `_system_arch_lib_dir` empty fallback, `_provider_from_model_id` ARN/bare Bedrock, `openrouter` engine detection, `_safe_load_provider_config`/`_safe_load_strategy` `ValueError` fallbacks, `_normalize_requested_providers` empty CSV segments, `GEMINI_API_KEY`/`META_API_KEY` alias egress precedence, `_configured_model_refs` `llm_model`, `discover_box_binaries` dir input, `run_box_doctor` non-Linux/`aarch64`/disabled AppArmor/`dogwood` CLI/symlink/missing/corrupt TOML + default `config_path=None`, `launch_box_run` default missing config/missing binaries/absolute symlink `policy`/`tomllib=None` fallback, and `strands-code box run -- -- ...` extra double-dash strip (`5` new tests in `TestBoxNyquistEdgeBranches` & `TestBoxCliSubcommands`) | unit (Nyquist) | `.venv/bin/pytest tests/sandbox/ tests/policy/test_codeact.py tests/policy/test_policy.py -q` (`191 passed`) + full suite (`1848+1`) + live integration (`1 passed` in `8.07s`) + `44/44` rig + `6/6` CI gates | ✅ | ✅ green (**1849/1849** default suite `[1848+1]` + **1** live integration + **44/44** rig) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- `tests/sandbox/test_box.py` — created TDD-first in Plan `19-01` Task 1 (`19-01-T1`) and hardened in `19-01-T2` covering host-only `box.toml`/`policy.dw` persistence, `tomllib` schema validity, `uv`/`.venv` realpaths, all 7+1 core + 2 opt-in egress profiles, canonical Dogwood MFOTL temporal `git push*` rule, `--out` self-tamper warnings, symlink refusal, canary secret zero-leakage, TOML/Cedar injection rejections, Linux 3-binary co-location, `x86_64` `EXPERIMENTAL_X86_SUPPORT=TRUE`, and Ubuntu 24.04 AppArmor diagnostics (`test_host_strands_box_or_dogwood_validates_generated_policy` added in `19-03-T1` under `@pytest.mark.integration`; security hardening tests added in `9ac28d3`; `TestBoxNyquistEdgeBranches` added in `19-VAL-T1`).

---

## Manual / Opportunistic Live Verifications

| Behavior | Requirement | Why Host Binaries / Kernel Required | Test Instructions | Status |
| :--- | :--- | :--- | :--- | :--- |
| Host `dogwood validate` / `box run` check against generated `policy.dw` & `box.toml` | `SANDBOX-01` | Requires external `box` / `dogwood` Rust binaries and unprivileged `userns` support on host Linux kernel | `.venv/bin/pytest tests/sandbox/test_box.py -m integration -v` *(verified live on host `strands-box 0.3.1` with `CLONE_NEWUSER`: `box policy generate-schema` + real `box run -- --help` on isolated & self-hosting `.venv/bin/strands-code` repos — **`1 passed, 24 deselected` in `8.07s`**; skips cleanly via `pytest.skip` when binaries are absent or userns restricted)* | ✅ green |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with TDD / automated verification
- [x] Wave 0 gaps identified (`tests/sandbox/test_box.py` in `19-01-T1`)
- [x] No watch-mode flags
- [x] Fast feedback latency (`< 25s` per targeted verification run)
- [x] `nyquist_compliant: true` audited post-execution

**Approval:** validated 2026-11-25 (`1848 passed, 16 deselected` in `71.81s` sandboxed + standalone loopback stub `1 passed, 195 deselected` in `2.42s` = **1849 passed, 0 failed**; `tests/rig/` **44 passed** in `0.11s`; live `strands-box 0.3.1` integration check `1 passed, 24 deselected` in `8.07s`; `sys.monitoring` **1178/1180 = 99.8%** on `box.py` [100.0% reachable on Python 3.12], **1/1 = 100.0%** on `sandbox/__init__.py`, and **100.0%** on Phase 19 integration seams; `ruff check`, `ruff format --check` `128 files`, `xenon --max-absolute C`, `lint-imports` `1 kept / 0 broken`, `uv lock --check` `156 packages` all green; `git diff 9ac28d3 -- strands_code_cli/ strands_code_agent/` empty and `git diff ee42ea2 -- strands_code_agent/` empty; `19-UAT.md` `6/6 PASS`; `19-SECURITY.md` `11/11 closed`, `threats_open: 0`).
