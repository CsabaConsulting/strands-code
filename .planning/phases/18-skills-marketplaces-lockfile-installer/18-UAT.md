---
status: complete
phase: 18-skills-marketplaces-lockfile-installer
source: [18-01-SUMMARY.md, 18-02-SUMMARY.md, 18-03-SUMMARY.md, 18-VERIFICATION.md]
started: 2026-11-25T02:08:00Z
updated: 2026-11-25T05:31:00Z
---

# Phase 18 User Acceptance Testing (`SKILL-03`)

## Current Test

[testing complete]

## Tests

### 1. Zero-Default Opt-In Registry, Multi-Format Catalog Discovery & Pure-HTTPS Redirect Auth Isolation (`D-01`, `D-02`, `D-03`)
expected: `load_marketplaces()` ships empty (`{}`); `/skills marketplace list` & `/skills browse` return helpful opt-in hints with zero HTTP traffic; aliases enforce `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$` (forbidding `local`/`all`), `github_repo_slug` derives `owner--repo`, and `~/.config/strands-code/marketplaces.yaml` writes `0o700`/`0o600` (symlink-refused); catalog discovery handles `.claude-plugin/marketplace.json` (`plugins[]` + cross-repo `github` dicts), `.agent-plugin/marketplace.json`, root `SKILL.md` (`subdir == "."`), and local-path catalogs; pure-HTTPS `resolve_github_commit` + `download_github_tarball` attach `GITHUB_TOKEN` strictly on `api.github.com`, strip `Authorization` on single-hop `codeload.github.com` redirect, block off-host redirects (`evil.example`), and `marketplace.py` uses zero `git` subprocesses.
result: pass
evidence:
- Executed via `run_uat18_test1.py` (`exit 0`, user accepted `pass` 2026-11-25T02:11Z):
  - `1a`: empty default registry & zero-network empty hints; `~/.config/strands-code/` created `0o700` dir / `0o600` file; `github_repo_slug("Anthropic", "skills.sh") == "anthropic--skills-sh"`.
  - `1b`: `.claude-plugin` (`pkg/pdf` + cross-repo `other/ext`), `.agent-plugin` (`fmt`), root `SKILL.md` (`solo` at `.`), and local-path (`local-helper`) all discovered cleanly.
  - `1c`: `subprocess_imported: False`, resolved `commit_sha`, `Authorization` attached only on `api.github.com` and stripped across `codeload.github.com` redirect, `evil.example` redirect rejected (`Disallowed tarball redirect host: 'evil.example'`).

### 2. Live GitHub Walkthrough (`anthropics/skills`): `/skills marketplace add`, `/skills browse`, `/skills install`, `/skills show`, Tamper Drift -> `/skills sync`, & `/skills uninstall` (`D-01`, `D-03`, `D-04`, `D-07`)
expected: Live GitHub `/skills marketplace add anthropics/skills --name anthropic-skills` resolves a 40-char `commit_sha`, caches catalog locally, `/skills browse` renders without auto-network traffic, `/skills install` creates `./.agent/skills-marketplaces/anthropic-skills/<skill>/` and `./.agent/skills-lock.json` (`version: 1`, `sha256:...`), `/skills show` displays provenance (`@ <short_sha>`, `verified (skills-lock.json)`, informational `Allowed tools`), mutating `SKILL.md` on disk triggers fail-closed skip until `/skills sync` restores the pinned snapshot, and `/skills uninstall` removes both directory and lock entry cleanly.
result: pass
evidence:
- Executed live via `run_uat18_test2.py` (`exit 0`, `BypassSandbox: true`, user accepted `pass` 2026-11-25T04:15Z):
  - `2a`: `Added marketplace 'anthropic-skills' (github: anthropics/skills) with 19 skills.`, cached `/skills browse` ran with zero network calls (`first: 'anthropic-skills:xlsx'`).
  - `2b`: Installed `anthropic-skills:xlsx` (`e4bb5d9`, `sha256:5100b54957a73...`, `has_scripts: True`); `/skills show` displayed `@ e4bb5d9`, `verified (skills-lock.json)`, and `Allowed tools policy: informational only`.
  - `2c`: Tampering `SKILL.md` skipped cleanly on `/skills reload`; `/skills sync` restored byte-identical snapshot; `/skills uninstall` deleted directory & evicted lockfile entry.

### 3. Deny-First Supply-Chain Guards: Malicious Tarballs, Caps, Rollback, `scripts/*` Update Diffs & ANSI/Rich Safe Rendering (`D-03`, `D-04`, `T-18-02`..`T-18-07`)
expected: Malicious tarballs containing symlinks, hardlinks, FIFOs, `.gitmodules`, absolute paths, `..` zip-slip, oversized `Content-Length`/unpacked bloat (`> 25 MiB` / `> 256` files / `> 5 MiB`), or strict `SKILL.md` name mismatch fail closed with zero workspace mutation; failed updates restore prior installed versions; bundled `scripts/*` warn prominently on install and diff `old_sha[:7] -> new_sha[:7]` + `added_scripts`/`changed_scripts` on update; `sanitize_display` strips ANSI/control chars while preserving literal `[tag]` brackets for `print_plain(markup=False)`.
result: pass
evidence:
- Executed via `run_uat18_test3.py` (`exit 0`, user accepted `pass` 2026-11-25T05:08Z):
  - `3a`: rejected `symlink`, `hardlink`, `fifo`, `gitmodules`, `abs`, `zipslip`; enforced `tarball_25mib`, `files_256`, `bytes_5mib` limits.
  - `3b`: corrupt v2 failed `Skill.from_file(..., strict=True)` keeping v1 intact; clean v2 emitted `Updated acme:audit (1111111 -> 2222222) [added scripts: scripts/new.sh; changed scripts: scripts/check.py]`.
  - `3c`: rendered `'Evil [red]literal[/red] next'` via `print_plain` with zero ANSI escapes or Rich markup parsing.

### 4. Multi-Namespace `SkillIndex`, Dynamic `/<ns>:` `SlashCompleter`, `@ <short_sha>` Provenance Framing & Real `AgentSkills` Sync (`D-04`, `D-06`)
expected: `SkillIndex` loads verified marketplace skills alongside `./.agent/skills/` (`local:` winning bare-name ties, `<ns>:<name>` explicit, ambiguous bare names failing closed), non-mutating `discover_plugin_sources()` syncs real `AgentSkills` (`local:` last, tampered skills omitted without mutating cache before failed reload), `SlashCompleter` completes `/<ns>:` dynamically (and leaves unknown namespaces empty), and remote slash invocation frames instructions with third-party provenance (`@ <short_sha>` + untrusted reminder).
result: pass
evidence:
- Executed via `run_uat18_test4.py` (`exit 0`, user accepted `pass` 2026-11-25T05:18Z):
  - `4a`: `shared` resolved to `'local:shared'`; ambiguous `audit` returned `None` & `"Ambiguous skill 'audit' — specify /acme:audit, /beta:audit."`.
  - `4b`: `SlashCompleter` completed `/acme:`, `/beta:`, `/local:` dynamically and emitted `[]` for `/unknown:`.
  - `4c`: `AgentSkills` prioritized `'Local shared wins'`; failed harness refresh kept `SkillIndex` stale; tampering omitted drifted skill; `/gamma:scan` emitted third-party provenance framing with `@ ddddddd`.

### 5. Protected-Path Policy Downgrade & HITL Gate Enforcement on `.agent/skills*`, `skills-lock.json` & `~/.config/strands-code/**` (`D-05`, `T-18-06`)
expected: Broad repo `[[allow]]` globs (`path = "*"`, `path = "**"`) on `write`/`edit` targeting `.agent/skills/*`, `.agent/skills-marketplaces/*`, `.agent/skills-lock.json`, `~/.config/strands-code/marketplaces.yaml`, or a workspace symlink resolving into user config downgrade from `Allow()` to `Prompt(...)` through both `decide()` and `PolicyHumanInTheLoop`, while `read` remains `Allow`, explicit `[[deny]]` stays `Deny`, and normal workspace files (`docs/a.md`) remain `Allow`.
result: pass
evidence:
- Executed via `run_uat18_test5.py` (`exit 0`, user accepted `pass` 2026-11-25T05:24Z):
  - `5a`: downgraded all 4 protected `write`/`edit` targets under `Rule(tool="*", path="*")` while keeping `read` and `docs/a.md` as `Allow()`.
  - `5b`: workspace symlink `escape.yaml -> cfg_home/marketplaces.yaml` downgraded to `Prompt(...)`; explicit `[[deny]]` still returned `Deny`.
  - `5c`: interactive `PolicyHumanInTheLoop` prompted twice with `'Protected path (.agent/skills/evil/SKILL.md): approve explicit write'` (`"n"` -> `Deny`, `"y"` -> `Proceed`).

### 6. Documentation (`docs/QUICKSTART.md`), Full Test Suite (`1779+1`), Rig Contracts (`44/44`) & All 6 CI Gates on `HEAD` (`D-07`, `D-24`)
expected: `docs/QUICKSTART.md` (`## Skills marketplaces`) accurately documents marketplace commands, layout, precedence, optional tokens, and protections; `pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q`, standalone `test_stub_server_systemone_decision_routes`, `tests/rig/`, `ruff check`, `ruff format --check`, `xenon --max-absolute C`, `lint-imports`, `uv lock --check`, and empty `git diff ee42ea2 -- strands_code_agent/` all pass cleanly on `HEAD`.
result: pass
evidence:
- Verified cleanly on `HEAD` (`73d60ee`, user accepted `pass` 2026-11-25T05:31Z):
  - `docs/QUICKSTART.md` (`## Skills marketplaces`, lines 315–350) reviewed + `pytest tests/ -k "docs_routing" -q` -> `2 passed, 1792 deselected`.
  - `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` -> `1779 passed, 15 deselected` (67.53s) + standalone `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` (`BypassSandbox: true`) -> `1 passed, 195 deselected` (2.44s); `.venv/bin/pytest tests/rig/ -q` -> `44 passed` (0.13s).
  - 6/6 CI gates: `ruff format --check` (`123 files already formatted`), `ruff check` (`All checks passed!`), `xenon --max-absolute C` (`exit 0`), `lint-imports` (`1 kept, 0 broken`, `41` files / `91` deps), `uv lock --check` (`Resolved 156 packages`), `git diff ee42ea2 -- strands_code_agent/` (empty).

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
