---
phase: 18-skills-marketplaces-lockfile-installer
plan: "01"
subsystem: memory-marketplace
tags: [skills, marketplace, lockfile, supply-chain, security]
requires:
  - phase: 06-skills-memory
    provides: Skill.from_file strict slug rules, BUILTIN_SLASH_HEADS, atomic config patterns
provides:
  - Pure-HTTPS GitHub & local catalog registry and cache manager
  - Deny-first tarball/local unpack with symlink, zip-slip, device, submodule, and size caps
  - Deterministic SHA-256 directory hasher and atomic ./.agent/skills-lock.json manager
  - Fail-closed verify_installed_marketplace_skills() guard
  - Hermetic GITHUB_TOKEN/GH_TOKEN test environment scrubbing
affects:
  - strands_code_cli/memory/marketplace.py
  - tests/conftest.py
  - tests/memory/test_marketplace.py
tech-stack:
  added: []
  patterns:
    - Single-hop redirect allowlist (codeload.github.com / objects.githubusercontent.com) without auth forwarding
    - Staging directory validation (Skill.from_file strict=True) with atomic swap & rollback
key-files:
  created:
    - strands_code_cli/memory/marketplace.py
    - tests/memory/test_marketplace.py
  modified:
    - tests/conftest.py
key-decisions:
  - Zero pre-registered remote marketplaces; zero git subprocesses
  - Local-path catalog lock entries pin deterministic SHA-256 prefix as 40-char commit_sha
patterns-established:
  - make_marketplace_client(follow_redirects=False) seam for httpx.MockTransport testing
  - Deterministic SHA-256 directory digest over sorted POSIX relative paths + byte lengths + bytes
requirements-completed:
  - SKILL-03
duration: 12min
completed: 2026-11-24
---

# Phase 18 Plan 01 Summary: Marketplace Catalog Registry, Safe Unpack & Lockfile Manager

**Executed:** 2026-11-24
**Status:** Complete

## Changes Delivered

1. **[marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py):**
   - Implemented opt-in catalog persistence (`~/.config/strands-code/marketplaces.yaml` at `0o700`/`0o600` & cache under `~/.cache/strands-code/marketplaces/<name>.json`, refusing symlinks and shipping empty by default).
   - Enforced `^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$` aliases (excluding `local`/`all`), flat `owner--repo` ad-hoc slugs (`github_repo_slug`), and strict `https://github.com/owner/repo[.git][@ref]` parsing (`parse_github_spec`).
   - Built pure-HTTPS `resolve_github_commit` + `download_github_tarball` via `httpx` (`follow_redirects=False`, optional `GITHUB_TOKEN`/`GH_TOKEN` isolated in `read_github_token()` sent strictly to `api.github.com`, at most 1 redirect hop to `codeload.github.com`/`objects.githubusercontent.com` without forwarding auth, `MAX_TARBALL_BYTES = 25 MiB`).
   - Implemented discovery across `.agent-plugin/marketplace.json`, `.claude-plugin/marketplace.json` (both subpath `plugins[]`/`skills[]` and cross-repo `github`/`git-subdir` sources), direct GitHub `owner/repo[@ref]` auto-discovery (including root `SKILL.md`), and local filesystem directories.
   - Built deny-first `extract_tarball_subdir_safe` and `copy_local_dir_safe` rejecting symlinks, hardlinks, FIFOs, devices, `.gitmodules`, `\x00`, absolute paths, and `..` traversal while enforcing `MAX_SKILL_FILES = 256`, `MAX_SKILL_BYTES = 5 MiB`, and `Skill.from_file(..., strict=True)` before atomic promotion with rollback.
   - Added deterministic `compute_skill_dir_hash`, atomic `./.agent/skills-lock.json` (`version: 1`) persistence, `scripts/*` warnings + update script diffs, and fail-closed `verify_installed_marketplace_skills()`.
2. **[conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py):**
   - Added `"GITHUB_TOKEN"` and `"GH_TOKEN"` to `_PROVIDER_ENV_VARS` while preserving `@pytest.mark.integration` exemption.
3. **[test_marketplace.py](file:///home/csaba/repos/AWS/strands-code/tests/memory/test_marketplace.py):**
   - Added 15 hermetic unit + adversarial security tests covering token scrubbing, catalog discovery, redirect auth isolation, script diffs, tamper drift + `/skills sync`, zip-slip/symlink/hardlink/device/`.gitmodules`/size-cap rejections, and rollback on failed update.

## Verification

- `.venv/bin/pytest tests/memory/test_marketplace.py -q` -> **15 passed**
- `.venv/bin/pytest tests/memory/ tests/cost/test_cost_context.py -k "not nonexistent" -q` -> **244 passed** (including `test_no_credential_persistence_sinks`)
- `.venv/bin/ruff check strands_code_cli tests scripts` -> **All checks passed**
- `.venv/bin/ruff format --check strands_code_cli tests scripts` -> **123 files already formatted**
- `.venv/bin/xenon --max-absolute C strands_code_cli/memory tests/memory` -> **Passed** (max CC in `marketplace.py`: `C (15)` in `remove_installed_skill` and `verify_installed_marketplace_skills`)
- `.venv/bin/lint-imports` -> **1 kept, 0 broken**
- `git diff ee42ea2 -- strands_code_agent/` -> **Empty** (`D-24`)
