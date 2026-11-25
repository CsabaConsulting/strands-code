---
phase: "18"
slug: "skills-marketplaces-lockfile-installer"
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-24"
validated: "2026-11-24"
---

# Phase 18 — Validation Strategy

> Per-phase Nyquist validation contract for feedback sampling during Phase 18 execution (`SKILL-03`).

---

## Test Infrastructure

| Property | Value |
| :--- | :--- |
| **Framework** | `pytest` (installed in `.venv`) via `/home/csaba/.local/bin/uv run pytest` or `.venv/bin/pytest` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts = "-m 'not integration'"`) |
| **Quick run command** | `.venv/bin/pytest tests/memory/ tests/policy/test_policy.py tests/policy/test_policy_gate.py -q` |
| **Full suite command** | `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` + standalone `test_stub_server_systemone_decision_routes` |
| **Static / complexity gates** | `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check` |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted verification command (`< 25s`).
- **After every plan wave:** Run `.venv/bin/pytest tests/memory/ tests/policy/ tests/dispatch/ tests/loop/ tests/entry/ -q` + `ruff check` + `ruff format --check` + `xenon --max-absolute C` + `lint-imports`.
- **Before `/gsd-verify-work 18`:** All 6 CI workflow checks must pass cleanly (`strands_code_agent/` diff empty).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Decision / Anchor | Secure / Correct Behavior | Test Type | Automated Command | File Exists | Status |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| `18-01-T1` | 01 | 1 | `SKILL-03` | `D-01`–`D-04`, `T-18-01` | `strands_code_cli/memory/marketplace.py` + `tests/conftest.py` (`GITHUB_TOKEN`/`GH_TOKEN` scrub): zero pre-registered catalogs, YAML registry (`0o700`/`0o600`), pure-HTTPS `/commits/<ref>` + redirect-guarded `/tarball/<sha>`, `.agent-plugin`/`.claude-plugin`/`owner/repo[@ref]`/local-path discovery, `./.agent/skills-marketplaces/<ns>/<skill>/` install, `./.agent/skills-lock.json` (`commit_sha` + `computed_hash` + `has_scripts`), `scripts/*` warning, and update/sync/remove lifecycle | unit (TDD RED→GREEN, Wave 0 file) | `.venv/bin/pytest tests/memory/test_marketplace.py -q && .venv/bin/ruff check strands_code_cli/memory/marketplace.py tests/conftest.py tests/memory/test_marketplace.py && .venv/bin/xenon --max-absolute C strands_code_cli/memory/marketplace.py tests/memory/test_marketplace.py && .venv/bin/lint-imports` | ✅ | ✅ green (`e8db593`) |
| `18-01-T2` | 01 | 1 | `SKILL-03` | `T-18-02`..`T-18-08` | Adversarial supply-chain rejections: tarball & local-dir symlinks, hardlinks, FIFOs, devices, `.gitmodules`, `..` zip-slip, 25 MiB compressed / 256 files / 5 MiB unpacked caps, strict `Skill.from_file(..., strict=True)`, `old_sha -> new_sha` update rollback, tampered hash-drift exclusion, control-char `GITHUB_TOKEN`, and `sanitize_display()` | security unit | `.venv/bin/pytest tests/memory/ tests/cost/test_cost_context.py -k "not nonexistent" -q && .venv/bin/ruff check strands_code_cli/memory tests/memory && .venv/bin/xenon --max-absolute C strands_code_cli/memory tests/memory && .venv/bin/lint-imports` | ✅ | ✅ green (`e8db593`) |
| `18-02-T1` | 02 | 2 | `SKILL-03` | `D-04`, `D-05`, `D-06`, `T-18-06` | `SkillIndex` multi-namespace loading + `local:` precedence + fail-closed hash-drift skip + non-mutating `discover_plugin_sources()`, dynamic `/<ns>:` completion in `SlashCompleter`, and `_is_protected_skills_or_config_path()` `Prompt` downgrade in `policy/core.py:decide()` | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/memory/ tests/policy/test_policy.py tests/policy/test_policy_gate.py -q && .venv/bin/ruff check strands_code_cli/memory strands_code_cli/ui/completer.py strands_code_cli/policy/core.py tests/memory tests/policy && .venv/bin/xenon --max-absolute C strands_code_cli/memory strands_code_cli/ui/completer.py strands_code_cli/policy/core.py tests/memory tests/policy && .venv/bin/lint-imports` | ✅ | ✅ green (`f160706`) |
| `18-02-T2` | 02 | 2 | `SKILL-03` | `D-04`, `D-06`, `D-07` | `/skills marketplace|browse|install|update|sync|show|remove|reload` wired in `dispatch/core.py` (`CC <= 15`, `_setup_decision_entries` untouched at `20`), provenance-framed remote skill prompts, `print_plain(markup=False)`, and atomic `AgentSkills.set_available_skills` sync across `entry/main.py` & `loop/core.py` | unit + integration (dispatch/loop/entry) | `.venv/bin/pytest tests/memory/ tests/dispatch/ tests/loop/ tests/entry/ tests/policy/ -k "not test_stub_server_systemone_decision_routes" -q && .venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports` | ✅ | ✅ green (`f160706`) |
| `18-03-T1` | 03 | 3 | `SKILL-03` | `D-07` | Add `@pytest.mark.integration` live GitHub marketplace probe in `tests/memory/test_marketplace.py`, execute opportunistically against public GitHub (skip cleanly if rate-limited/offline), and verify `tests/rig/` (`44/44`) | integration + rig contract | `.venv/bin/pytest tests/memory/ tests/rig/ -q && .venv/bin/ruff check tests/memory/test_marketplace.py && .venv/bin/xenon --max-absolute C tests/memory/test_marketplace.py` | ✅ | ✅ green (`d0562be`) |
| `18-03-T2` | 03 | 3 | `SKILL-03` | `D-01`–`D-07` + Gates | Document Skills Marketplaces in `docs/QUICKSTART.md` (`GITHUB_TOKEN`/`GH_TOKEN`, `./.agent/skills-lock.json`, deny-first safeguards) and verify all 6 CI gates + full default suite + standalone loopback stub | docs + full CI gates | `.venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports && /home/csaba/.local/bin/uv lock --check && .venv/bin/pytest tests/rig/ -q && .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q && git diff ee42ea2 -- strands_code_agent/` | ✅ | ✅ green (`d0562be`) |
| `18-UAT-T1` | uat | 4 | `SKILL-03` | `D-01`–`D-07` | Full `6/6` interactive & live UAT (`18-UAT.md`): zero-default registry + redirect auth stripping, live `anthropics/skills` add → cached browse → install (`@ e4bb5d9`) → `/skills show` → tamper skip → `/skills sync` → `/skills uninstall`, deny-first tarball/cap/rollback + `scripts/*` update diffs + `print_plain` safety, multi-namespace `SkillIndex` + dynamic `/<ns>:` `SlashCompleter` + `AgentSkills` sync + provenance framing, protected-path `Prompt` downgrade + HITL gate, `docs/QUICKSTART.md` + CI gates | live UAT + CI gates | `18-UAT.md` (`6/6 PASS`) + `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` | ✅ | ✅ green (`b2cb3ac`) |
| `18-SEC-T1` | sec | 4 | `SKILL-03` | `T-18-01`–`T-18-10` | ASVS L1 security audit (`18-SECURITY.md`, `10/10 closed`, `threats_open: 0`): strict `load_lockfile()` slug/key/SHA/hash/subdir validation via `valid_skill_name()` & `validate_skill_name()`, `_validate_sync_source()` blocking unregistered local-path sync from crafted `skills-lock.json`, staging hash check before `_atomic_swap_skill_dir()`, explicit redirect port & JSON `NaN`/`Infinity` rejection, `2 MiB` API JSON cap, `httpx.HTTPError` scrubbing, direct segment validation, `update_marketplace()` `ValueError` ordering, symlink-safe cache/lockfile parent checks, `user_cache_dir("strands-code")` policy protection, and GitHub token patterns in `scrub_credentials()` | security unit + live probe + CI gates | `.venv/bin/pytest tests/memory/ tests/policy/ tests/cost/test_cost_context.py tests/rig/ -q` (`620 passed`) + full suite (`1784+1`) + live integration probe (`1 passed` in `5.07s`) | ✅ | ✅ green (`b169716`) |
| `18-VAL-T1` | val | 4 | `SKILL-03` | `D-01`–`D-07` | Retroactive Nyquist edge-branch coverage (**zero runtime edits**, `git diff b169716 -- strands_code_cli/ strands_code_agent/` empty; `2084/2099` = **99.3%** changed executable line coverage across all 8 Phase 18 source files: `100.0%` on `cost_context.py`, `dispatch/core.py`, `entry/main.py`, `loop/core.py`, `policy/core.py`, `ui/completer.py`; `99.4%` on `marketplace.py` `[1633/1643]`; `96.2%` on `skills.py` `[127/132]`): default config/cache paths, `sanitize_display` truncation, `_validate_git_ref`/`_validate_tarball_redirect_url`/`parse_github_spec` errors, `_refuse_symlink*`/`_atomic_write_text` tmp cleanup, malformed YAML/JSON registry/cache, `make_marketplace_client` & HTTP `302`/`404`/oversized/`ConnectError`/streaming caps, tarball PAX/unsupported-type/multi-top-level/subdir/scripts-symlink/staged caps, local copy/FIFO/`.gitmodules`/hash caps, lockfile schema rejections, `.agent-plugin`/`.claude-plugin`/plugin-subpath manifest discovery variants, local catalog install/sync/atomic-swap rollback, update/sync/remove/`verify_installed_marketplace_skills` edge branches, `run_loop` `/skills reload` `AgentSkills` sync (`loop/core.py:2538`), `SkillIndex` fallback/symlink remove paths, `/skills` dispatch usage/error/empty/ambiguous/sync/remove branches, and `_is_protected_skills_or_config_path` empty/`None`/symlinked-`cwd`/`OSError` fallbacks | unit (Nyquist) | `.venv/bin/pytest tests/memory/ tests/policy/ -q` + full suite (`1797+1`) + `44/44` rig + 6/6 CI gates | ✅ | ✅ green (**1798/1798** default suite `[1797+1]` + **44/44** rig) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- `tests/memory/test_marketplace.py` — created TDD-first in Plan `18-01` Task 1 (`18-01-T1`) and hardened in `18-01-T2` covering catalog persistence, HTTPS GitHub `/commits/<ref>` + `/tarball/<sha>` + redirect isolation, `.agent-plugin`/`.claude-plugin`/`owner/repo[@ref]`/local discovery, malicious tarball/symlink/size rejections, `./.agent/skills-lock.json` verification, and hash-drift quarantine (`test_live_github_marketplace_browse_install_and_verify` added in `18-03-T1` under `@pytest.mark.integration`; `TestPhase18SecurityAuditHardening` added in `b169716`; `TestPhase18NyquistMarketplaceBranches` added in `18-VAL-T1`).

---

## Manual / Opportunistic Live Verifications

| Behavior | Requirement | Why Live Creds / Network Required | Test Instructions | Status |
| :--- | :--- | :--- | :--- | :--- |
| Live GitHub catalog discovery, single-skill tarball install, 40-char `commit_sha` + SHA-256 lockfile verification & tamper detection | `SKILL-03` | Requires outbound HTTPS to `api.github.com` & `codeload.github.com` | `.venv/bin/pytest tests/memory/test_marketplace.py -m integration -v` *(verified `1 passed` in `4.55s` at `d0562be` and `1 passed` in `5.07s` at `b169716` against live `anthropics/skills`; skips cleanly in offline sandbox)* | ✅ green |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with TDD / automated verification
- [x] Wave 0 gaps identified (`tests/memory/test_marketplace.py` in `18-01-T1`)
- [x] No watch-mode flags
- [x] Fast feedback latency (`< 25s` per targeted verification run)
- [x] `nyquist_compliant: true` audited post-execution

**Approval:** validated 2026-11-24 (`1797 passed, 15 deselected` in `63.80s` sandboxed + standalone loopback stub `1 passed, 195 deselected` in `2.13s` = **1798 passed, 0 failed**; `tests/rig/` **44 passed** in `0.10s`; live GitHub probe `1 passed` in `5.07s` on `b169716`; `sys.monitoring` **2084/2099 = 99.3%** Phase 18 executable line coverage; `ruff check`, `ruff format --check` `123 files`, `xenon --max-absolute C`, `lint-imports` `1 kept / 0 broken`, `uv lock --check` `156 packages` all green; `git diff b169716 -- strands_code_cli/ strands_code_agent/` empty and `git diff ee42ea2 -- strands_code_agent/` empty; `18-UAT.md` `6/6 PASS`; `18-SECURITY.md` `10/10 closed`, `threats_open: 0`).
