---
phase: "18"
slug: "skills-marketplaces-lockfile-installer"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-24"
---

# Phase 18 — Security

> Per-phase security contract: threat register, remediation verification, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `Untrusted CWD repository (.env / .agent/skills-lock.json) -> disable_cwd_dotenv() & load_lockfile()` | Untrusted repo checked out into CWD | `.env` auto-loading blocked (`disable_cwd_dotenv()`); lockfile schema/slugs/SHAs/hashes/subdirs strictly validated before any write or sync (`T-18-09`) |
| `Env API keys (GITHUB_TOKEN / GH_TOKEN) -> read_github_token() -> api.github.com` | GitHub auth tokens isolated to `memory/marketplace.py` | Control-char-free bearer token sent ONLY to `api.github.com`, never forwarded on `codeload` redirects, scrubbed in `conftest.py` and `cost_context.scrub_credentials()` |
| `Remote GitHub API + Tarball Storage <-> httpx.Client(follow_redirects=False)` | GitHub REST metadata + single-hop tarball streams (`codeload.github.com` / `objects.githubusercontent.com`) | JSON bounded `<= 2 MiB` with `NaN`/`Infinity` rejected; tarball bounded `<= 25 MiB`; zero auth headers on redirects |
| `Tarball / Local Catalog Stream -> extract_tarball_subdir_safe() / copy_local_dir_safe() -> Staging` | Third-party archives and local skill directories | Deny-first rejection of symlinks, hardlinks, FIFOs, devices, `.gitmodules`, `\x00`, absolute paths, `..` zip-slip; `256` files / `5 MiB` caps; `Skill.from_file(..., strict=True)` before atomic swap |
| `./.agent/skills-marketplaces/<ns>/<skill>/ <-> ./.agent/skills-lock.json` | Installed marketplace skills vs versioned lockfile | Deterministic SHA-256 hash verification; symlinked parents/roots/entries & hash drift warn-and-skipped out of `SkillIndex` & `AgentSkills`; `/skills sync` verifies hash inside staging before swap |
| `Prompt / Tool Gate <-> policy/core.py:decide() <-> .agent/skills* & user config/cache` | Broad repo `[[allow]]` globs (`path = "*"`, `.agent/**`) | Explicit `[[deny]]` preserved first; `write`/`edit` targeting realpath-resolved `.agent/skills*`, `skills-lock.json`, `~/.config/strands-code/**`, or `~/.cache/strands-code/**` downgraded to `Prompt(...)` |
| `Remote SKILL.md Metadata & Bodies -> dispatch / print_plain / AgentSkills` | Untrusted third-party descriptions, instructions, `allowed-tools`, and `scripts/*` | ANSI CSI/control chars stripped via `sanitize_display()`; `print_plain(markup=False)`; `@ <short_sha>` provenance framing; `allowed-tools` informational only; `scripts/*` never auto-executed |
| `Upstream package boundary (strands_code_agent/)` | Fork-inherited agent package kept byte-pristine under `D-24` | `CodeAgent` / `SandboxedPythonInterpreter` untouched |

---

## Threat Register

Audited against Phase 18 commits (`e8db593..b2cb3ac`), [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py), [skills.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/skills.py), [completer.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/completer.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/core.py), [dispatch/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py), [entry/main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py), UAT (`18-UAT.md` `6/6` passed), and ASVS Level 1 remediations verified freshly across the full suite (`1784 + 1`) + live GitHub `anthropics/skills` probe at `security_block_on: high`.

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| `T-18-01` | Information Disclosure (`GITHUB_TOKEN` / `GH_TOKEN`) | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py), [cost_context.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/cost/cost_context.py), [conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py) | high | mitigate | `tests/conftest.py` scrubs `GITHUB_TOKEN`/`GH_TOKEN` in non-integration runs; `disable_cwd_dotenv()` blocks untrusted repo `.env` injection; `read_github_token()` rejects whitespace/control chars and keeps env reads isolated to `marketplace.py` (`test_no_credential_persistence_sinks`). **Hardened in this audit:** added `gh[pousr]_*`, `github_pat_*`, and `GITHUB_TOKEN`/`GH_TOKEN` key-value patterns to `cost_context.scrub_credentials()` so transcripts/compaction never leak GitHub tokens. | closed |
| `T-18-02` | Arbitrary File Write / Symlink Exfiltration / Zip-Slip / Submodules | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py) | critical | mitigate | `extract_tarball_subdir_safe()` & `copy_local_dir_safe()` refuse symlinks, hardlinks, FIFOs, devices, `.gitmodules`, `\x00`, absolute paths, and `..` traversal before writing staging files; `verify_installed_marketplace_skills()`, `load_marketplaces()`, `load_cached_catalog()`, and `load_lockfile()` fail closed on symlinks at target or parent dirs (`R-18-02`). | closed |
| `T-18-03` | Denial of Service (Tarball Bomb & Bloat) | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py) | medium | mitigate | Enforces `MAX_TARBALL_BYTES = 25 MiB` on `Content-Length` + streaming body accumulation, `MAX_SKILL_FILES = 256`, and `MAX_SKILL_BYTES = 5 MiB` unpacked per skill (and on catalog metadata files). **Hardened in this audit:** capped `MAX_API_JSON_BYTES = 2 MiB` in `_github_get_json()`. | closed |
| `T-18-04` | Tampering / Silent Drift / Local Override | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py), [skills.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/skills.py), [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py), [loop/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py) | high | mitigate | `./.agent/skills-lock.json` (`version: 1`) pins immutable 40-char `commit_sha` + deterministic SHA-256 `computed_hash`; `verify_installed_marketplace_skills()` fail-closed warn-and-skips un-locked/drifted skills from `SkillIndex` & `AgentSkills`; read-only `discover_plugin_sources()` preserves stale state on failed reload and loads `local:` last to win bare-name ties (`R-18-03`). | closed |
| `T-18-05` | Privilege Escalation (`allowed-tools` & `scripts/*`) | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py), [dispatch/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py) | high | mitigate | `allowed-tools` remains strictly informational in `/skills show` (`Allowed tools policy: informational only (never enforced)`) and never feeds `PolicyConfig`; bundled `scripts/*` warn prominently on install and diff added/changed scripts on update, remaining gated by `shell`/`python_repl` HITL (`R-18-03`). | closed |
| `T-18-06` | Authorization Bypass (`[[allow]]` Overwriting Skills/Config/Cache) | [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/core.py) | high | mitigate | `policy/core.py:decide()` evaluates `[[deny]]` first and downgrades broad `[[allow]]` write/edit matches targeting `realpath`-resolved `.agent/skills*`, `.agent/skills-lock.json`, and `~/.config/strands-code/**` to `Prompt(...)`. **Hardened in this audit (`T-18-10`):** added `platformdirs.user_cache_dir("strands-code")` so broad globs cannot poison cached marketplace catalogs (`~/.cache/strands-code/marketplaces/`). | closed |
| `T-18-07` | Terminal Control Injection / Prompt Provenance Spoofing | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py), [dispatch/core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py), [completer.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/completer.py) | medium | mitigate | `sanitize_display()` strips ANSI CSI sequences and ASCII control chars; CLI replies render via `print_plain(markup=False)`; dynamic `/<ns>:` completer isolates namespaces; remote skill turns carry explicit `@ <short_sha>` untrusted-provenance framing. | closed |
| `T-18-08` | SSRF / Auth Header Leak on Redirect / Non-Standard JSON / Transport Errors | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py) | **high** | mitigate | `make_marketplace_client()` disables redirects (`follow_redirects=False`) and allows one hop strictly to `codeload.github.com` / `objects.githubusercontent.com` without `Authorization`. **Hardened in this audit:** rejected whitespace and explicit `parsed.port` in `_validate_tarball_redirect_url()`, added `owner`/`repo` `_validate_github_segment()` guards at entrypoints `resolve_github_commit`/`download_github_tarball`, added `parse_constant=_reject_json_constant` rejecting `NaN`/`Infinity`, and normalized `httpx.HTTPError` cleanly to `"GitHub network error (offline or unreachable)"`. | closed |
| `T-18-09` | Malicious Repo `skills-lock.json` Traversal / Unregistered Local-Path Sync / Pre-Swap Hash Bypass | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py) | **high** | mitigate | **Discovered & remediated in this audit:** tightened `load_lockfile()` via `_parse_lock_entry()` to reject invalid `namespace`, invalid `name` (`valid_skill_name` + `--`/slug grammar), mismatched keys, non-40-hex `commit_sha`, malformed `computed_hash`, or unsafe `subdir`; enforced `validate_skill_name()` before creating `staging_dir / skill_name`; added `_validate_sync_source()` so `/skills sync` refuses non-HTTPS `repo_url` values not matching a user-registered `local` marketplace entry; verified `expected_hash` inside staging BEFORE `_atomic_swap_skill_dir()` so mismatched sync tarballs never touch disk or `skills-lock.json`. | closed |
| `T-18-10` | Unhandled Lookup Crash / Symlinked `.agent` Parent / Protected Cache & Upstream Isolation | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/core.py) | **medium** | mitigate | **Discovered & remediated in this audit:** fixed `update_marketplace()` validation order (`Unknown marketplace` `ValueError` instead of `KeyError`), guarded `remove_marketplace()` cache unlink against symlinked cache parent dirs, checked `lockfile_path.parent.is_symlink()` and `marketplaces_dir.parent.is_symlink()` in `verify_installed_marketplace_skills()`, kept all new/edited functions `<= xenon C (17)` (zero edits to `_setup_decision_entries`/`price_table`/`run_loop` and `strands_code_agent/` untouched per `D-24`, `R-18-01`). | closed |

*Status: `open` · `closed`*
*Severity: `critical` > `high` > `medium` > `low` — only `open` threats at or above `workflow.security_block_on` (`high`) count toward `threats_open`*
*Disposition: `mitigate` (implementation verified) · `accept` (documented risk) · `transfer` (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| `R-18-01` | `T-18-10` | Phase 18 preserves `D-24` (`git diff ee42ea2 -- strands_code_agent/` empty) and leaves complexity-ceiling functions `save_strategy` (`20`), `_setup_decision_entries` (`20`), and `price_table` (`20`) unmodified (`marketplace.py` max `C 17`, `policy/core.py:decide` `C 15`, `dispatch/core.py:_skills_message` `C 13`, `loop/core.py:run_loop` `C 18`). | secure-phase L1 audit | 2026-11-24 |
| `R-18-02` | `T-18-02` | MVP Phase 6 contract (`test_remove_symlinked_skill_dir_refused`) keeps symlinked entries inside `./.agent/skills/` loadable while refusing `/skills remove` on symlinks; strict load-time symlink rejection applies specifically to `./.agent/skills-marketplaces/`, `./.agent/skills-lock.json`, their parent `.agent` dir when scanning marketplace skills, and user marketplace/cache configs. | secure-phase L1 audit | 2026-11-24 |
| `R-18-03` | `T-18-04`, `T-18-05` | Once verified by `/skills sync` or `/skills install`, markdown skill instructions enter the model prompt verbatim (framed explicitly as untrusted third-party directives `@ <short_sha>`); prompt-injection defense at runtime rests on model compliance plus Phase 3/4/18 Plan-mode & HITL `PolicyHumanInTheLoop` gates on all side-effecting tool calls (including `scripts/*`). | secure-phase L1 audit | 2026-11-24 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-24 | 10 | 10 | 0 | `gsd-secure-phase` ASVS L1 audit (discovered & closed `T-18-09` HIGH strict lockfile/slug/sync-source/pre-swap hash guards, `T-18-08` HIGH port/`NaN`/network-error/segment guards, `T-18-10` MEDIUM `update_marketplace` `ValueError`/symlinked `.agent` parent/cache policy protection, and `T-18-01` GitHub token scrubbing patterns in `scrub_credentials`; verified after final code/test edits: `ruff format --check` `123 files already formatted`, `ruff check` `All checks passed!`, `xenon --max-absolute C` `exit 0` with `marketplace.py` max `C 17` and `price_table`/`_setup_decision_entries`/`save_strategy` untouched at `20`, `lint-imports` `1 kept, 0 broken`, `uv lock --check` `Resolved 156 packages`, `pytest tests/rig/` `44 passed`, `pytest tests/memory/test_marketplace.py -m integration` `1 skipped` offline / `1 passed` live against `anthropics/skills` in `5.07s`, full default suite `1784 passed, 15 deselected` + standalone loopback stub `1 passed` = `1785/1785` non-integration suite green, `git diff ee42ea2 -- strands_code_agent/` empty; `18-UAT.md` `6/6` passed) |

---

## Sign-Off

- [x] All threats have a disposition (`mitigate` / `accept` / `transfer`)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-24
