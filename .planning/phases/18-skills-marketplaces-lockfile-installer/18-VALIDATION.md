---
phase: "18"
slug: "skills-marketplaces-lockfile-installer"
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-11-24"
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
| `18-01-T1` | 01 | 1 | `SKILL-03` | `D-01`–`D-04`, `T-18-01` | `strands_code_cli/memory/marketplace.py` + `tests/conftest.py` (`GITHUB_TOKEN`/`GH_TOKEN` scrub): zero pre-registered catalogs, YAML registry (`0o700`/`0o600`), pure-HTTPS `/commits/<ref>` + redirect-guarded `/tarball/<sha>`, `.agent-plugin`/`.claude-plugin`/`owner/repo[@ref]`/local-path discovery, `./.agent/skills-marketplaces/<ns>/<skill>/` install, `./.agent/skills-lock.json` (`commit_sha` + `computed_hash` + `has_scripts`), `scripts/*` warning, and update/sync/remove lifecycle | unit (TDD RED→GREEN, Wave 0 file) | `.venv/bin/pytest tests/memory/test_marketplace.py -q && .venv/bin/ruff check strands_code_cli/memory/marketplace.py tests/conftest.py tests/memory/test_marketplace.py && .venv/bin/xenon --max-absolute C strands_code_cli/memory/marketplace.py tests/memory/test_marketplace.py && .venv/bin/lint-imports` | ⬜ W0 | ⬜ pending |
| `18-01-T2` | 01 | 1 | `SKILL-03` | `T-18-02`..`T-18-08` | Adversarial supply-chain rejections: tarball & local-dir symlinks, hardlinks, FIFOs, devices, `.gitmodules`, `..` zip-slip, 25 MiB compressed / 256 files / 5 MiB unpacked caps, strict `Skill.from_file(..., strict=True)`, `old_sha -> new_sha` update rollback, tampered hash-drift exclusion, control-char `GITHUB_TOKEN`, and `sanitize_display()` | security unit | `.venv/bin/pytest tests/memory/ tests/cost/test_cost_context.py -k "not nonexistent" -q && .venv/bin/ruff check strands_code_cli/memory tests/memory && .venv/bin/xenon --max-absolute C strands_code_cli/memory tests/memory && .venv/bin/lint-imports` | ⬜ W0 | ⬜ pending |
| `18-02-T1` | 02 | 2 | `SKILL-03` | `D-04`, `D-05`, `D-06`, `T-18-06` | `SkillIndex` multi-namespace loading + `local:` precedence + fail-closed hash-drift skip + non-mutating `discover_plugin_sources()`, dynamic `/<ns>:` completion in `SlashCompleter`, and `_is_protected_skills_or_config_path()` `Prompt` downgrade in `policy/core.py:decide()` | unit (TDD RED→GREEN) | `.venv/bin/pytest tests/memory/ tests/policy/test_policy.py tests/policy/test_policy_gate.py -q && .venv/bin/ruff check strands_code_cli/memory strands_code_cli/ui/completer.py strands_code_cli/policy/core.py tests/memory tests/policy && .venv/bin/xenon --max-absolute C strands_code_cli/memory strands_code_cli/ui/completer.py strands_code_cli/policy/core.py tests/memory tests/policy && .venv/bin/lint-imports` | ✅ | ⬜ pending |
| `18-02-T2` | 02 | 2 | `SKILL-03` | `D-04`, `D-06`, `D-07` | `/skills marketplace|browse|install|update|sync|show|remove|reload` wired in `dispatch/core.py` (`CC <= 15`, `_setup_decision_entries` untouched at `20`), provenance-framed remote skill prompts, `print_plain(markup=False)`, and atomic `AgentSkills.set_available_skills` sync across `entry/main.py` & `loop/core.py` | unit + integration (dispatch/loop/entry) | `.venv/bin/pytest tests/memory/ tests/dispatch/ tests/loop/ tests/entry/ tests/policy/ -k "not test_stub_server_systemone_decision_routes" -q && .venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports` | ✅ | ⬜ pending |
| `18-03-T1` | 03 | 3 | `SKILL-03` | `D-07` | Add `@pytest.mark.integration` live GitHub marketplace probe in `tests/memory/test_marketplace.py`, execute opportunistically against public GitHub (skip cleanly if rate-limited/offline), and verify `tests/rig/` (`44/44`) | integration + rig contract | `.venv/bin/pytest tests/memory/ tests/rig/ -q && .venv/bin/ruff check tests/memory/test_marketplace.py && .venv/bin/xenon --max-absolute C tests/memory/test_marketplace.py` | ⬜ W0 | ⬜ pending |
| `18-03-T2` | 03 | 3 | `SKILL-03` | `D-01`–`D-07` + Gates | Document Skills Marketplaces in `docs/QUICKSTART.md` (`GITHUB_TOKEN`/`GH_TOKEN`, `./.agent/skills-lock.json`, deny-first safeguards) and verify all 6 CI gates + full default suite + standalone loopback stub | docs + full CI gates | `.venv/bin/ruff format --check strands_code_cli tests scripts && .venv/bin/ruff check strands_code_cli tests scripts && .venv/bin/xenon --max-absolute C strands_code_cli tests scripts && .venv/bin/lint-imports && /home/csaba/.local/bin/uv lock --check && .venv/bin/pytest tests/rig/ -q && .venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q && git diff ee42ea2 -- strands_code_agent/` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- `tests/memory/test_marketplace.py` — created TDD-first in Plan `18-01` Task 1 (`18-01-T1`) and hardened in `18-01-T2` covering catalog persistence, HTTPS GitHub `/commits/<ref>` + `/tarball/<sha>` + redirect isolation, `.agent-plugin`/`.claude-plugin`/`owner/repo[@ref]`/local discovery, malicious tarball/symlink/size rejections, `./.agent/skills-lock.json` verification, and hash-drift quarantine (`test_live_github_marketplace_browse_install_and_verify` added in `18-03-T1` under `@pytest.mark.integration`).

---

## Manual / Opportunistic Live Verifications

| Behavior | Requirement | Why Live Creds / Network Required | Test Instructions | Status |
| :--- | :--- | :--- | :--- | :--- |
| Live GitHub catalog discovery, single-skill tarball install, 40-char `commit_sha` + SHA-256 lockfile verification & tamper detection | `SKILL-03` | Requires outbound HTTPS to `api.github.com` & `codeload.github.com` | `.venv/bin/pytest tests/memory/test_marketplace.py -m integration -v` *(use `BypassSandbox: true` if outbound HTTPS is sandbox-blocked; skips cleanly if offline/rate-limited)* | ⬜ pending |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: every task commits with TDD / automated verification
- [x] Wave 0 gaps identified (`tests/memory/test_marketplace.py` in `18-01-T1`)
- [x] No watch-mode flags
- [x] Fast feedback latency (`< 25s` per targeted verification run)
- [ ] `nyquist_compliant: true` audited post-execution

**Approval:** pending execution (`18-01`–`18-03`)
