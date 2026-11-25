---
phase: 18-skills-marketplaces-lockfile-installer
verified: 2026-11-24
status: passed
score: 12/12
requirement: SKILL-03
live_probes:
  - target: anthropics/skills (.claude-plugin/marketplace.json)
    result: 1 passed in 4.55s (skipped cleanly inside offline sandbox)
ci_gates:
  - ruff format --check strands_code_cli tests scripts: 123 files already formatted
  - ruff check strands_code_cli tests scripts: All checks passed
  - xenon --max-absolute C strands_code_cli tests scripts: passed
  - lint-imports: 1 kept, 0 broken (41 files, 91 dependencies)
  - uv lock --check: passed (Resolved 156 packages in 2ms)
  - git diff ee42ea2 -- strands_code_agent/: empty
---

# Phase 18 Goal-Backward Verification (`SKILL-03`)

**Status:** `PASS` (`12/12` must-have truths + `8/8` ASVS supply-chain threats verified)

---

## Goal-Backward Verification Matrix

| # | Observable / Structural Truth | Code & Test Evidence | Result |
|---:|---|---|---|
| 1 | Pure-HTTPS GitHub resolution (`/commits/<ref>` -> 40-char `commit_sha`) & single-hop redirect-guarded `/tarball/<commit_sha>` without `Authorization` forwarding (`codeload.github.com` / `objects.githubusercontent.com` only); zero `git` subprocesses | [marketplace.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/marketplace.py) (`make_marketplace_client`, `resolve_github_commit`, `download_github_tarball`), [test_marketplace.py](file:///home/csaba/repos/AWS/strands-code/tests/memory/test_marketplace.py) (`test_redirect_strips_authorization_and_blocks_evil_host`) | PASS |
| 2 | Zero pre-registered marketplaces; strict alias validation (`^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$`, excluding `local`/`all`); flat `owner--repo` ad-hoc slugs; ~/.config/strands-code/marketplaces.yaml (`0o700`/`0o600`, symlink-refused) & cache persistence | `marketplace.py` (`load_marketplaces`, `save_marketplaces`, `valid_namespace`, `github_repo_slug`), `test_marketplace.py` (`test_ships_empty_and_persists_with_restricted_perms`, `test_namespace_alias_and_slug_validation`, `test_adhoc_owner_repo_install_derives_flat_slug`) | PASS |
| 3 | Discovery across `.agent-plugin/marketplace.json`, `.claude-plugin/marketplace.json` (subpaths & cross-repo `github`/`git-subdir`), direct `owner/repo[@ref]` (including root `SKILL.md`), and local-path catalogs | `marketplace.py` (`discover_catalog_from_tree`, `discover_catalog_from_tarball`, `add_marketplace`), `test_marketplace.py` (`TestMarketplaceRegistryAndCatalogs`), plus live GitHub `anthropics/skills` probe (`test_live_github_marketplace_browse_install_and_verify`) | PASS |
| 4 | Deny-first unpacking rejects symlinks, hardlinks, FIFOs, devices, `.gitmodules`, `\x00`, absolute paths, `..` zip-slip; enforces `25 MiB` compressed / `256` files / `5 MiB` unpacked caps & `Skill.from_file(..., strict=True)` before atomic swap + rollback | `marketplace.py` (`extract_tarball_subdir_safe`, `copy_local_dir_safe`, `_atomic_swap_skill_dir`), `test_marketplace.py` (`TestMarketplaceSecurityGuards`) | PASS |
| 5 | `./.agent/skills-lock.json` (`version: 1`) persists `commit_sha` + deterministic SHA-256 `computed_hash`; `verify_installed_marketplace_skills()` fail-closed warn-and-skips missing-lock, symlinked, or hash-drifted directories; install/update warns on `scripts/*` with `old_sha -> new_sha` + script diffs | `marketplace.py` (`compute_skill_dir_hash`, `load_lockfile`, `save_lockfile`, `verify_installed_marketplace_skills`, `update_installed_skills`, `sync_installed_skills`), `test_marketplace.py` (`test_end_to_end_install_and_update_scripts_diff`, `test_tamper_drift_sync_restore_and_remove`) | PASS |
| 6 | Multi-namespace `SkillIndex` keeps `./.agent/skills/` (`local:`) winning bare-name ties, exposes `<ns>:<name>`, fails closed on ambiguous bare marketplace names, excludes hash-drifted skills, and provides read-only `discover_plugin_sources()` preserving atomic reload order & MVP `./.agent/skills/` symlink contract | [skills.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/memory/skills.py), [test_skills.py](file:///home/csaba/repos/AWS/strands-code/tests/memory/test_skills.py) (`TestMultiNamespaceSkillIndex`, `test_failed_harness_refresh_leaves_index_stale`, `test_remove_symlinked_skill_dir_refused`) | PASS |
| 7 | `SlashCompleter` dynamically completes `/<ns>:<skill>` from live `get_words()` while leaving unknown namespaces empty | [completer.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/ui/completer.py), `test_skills.py` (`test_dynamic_namespace_slash_completer_and_remove`, `test_unknown_namespace_suggests_nothing`) | PASS |
| 8 | Protected-path `Prompt` downgrade in `policy/core.py:decide()` downgrades broad `[[allow]]` write/edit rules targeting `.agent/skills*`, `.agent/skills-lock.json`, or `~/.config/strands-code/**` (realpath-resolved, preserving `[[deny]]` priority & `read` allows) | [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/policy/core.py) (`_is_protected_skills_or_config_path`, `decide` at `CC 15`), [test_policy.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_policy.py), [test_policy_gate.py](file:///home/csaba/repos/AWS/strands-code/tests/policy/test_policy_gate.py) | PASS |
| 9 | `/skills marketplace|browse|install|update|sync|show|remove|uninstall|reload|refresh` wired in `dispatch/core.py`, framing remote skill invocations with `@ <short_sha>` provenance & untrusted reminders, rendering sanitized metadata via `print_plain(markup=False)` | [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/dispatch/core.py) (`_skills_message` `C 13`, `_setup_decision_entries` untouched at `C 20`), `test_skills.py` (`TestSkillsMarketplaceEndToEnd`) | PASS |
| 10 | `AgentSkills` syncs verified marketplace dirs + `./.agent/skills` (`local:` last) at startup & live `/skills` mutations | [main.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/entry/main.py) (`build_agent`), [core.py](file:///home/csaba/repos/AWS/strands-code/strands_code_cli/loop/core.py) (`run_loop` `C 18`), `test_skills.py` (`test_agent_skills_sync_tamper_eviction_and_local_tie_break`) | PASS |
| 11 | Credential hygiene (`GITHUB_TOKEN`/`GH_TOKEN` isolated to `memory/marketplace.py:read_github_token()` and scrubbed in [conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py)) + display sanitization (`sanitize_display`) + `docs/QUICKSTART.md` guide | [conftest.py](file:///home/csaba/repos/AWS/strands-code/tests/conftest.py), [QUICKSTART.md](file:///home/csaba/repos/AWS/strands-code/docs/QUICKSTART.md), `test_cost_context.py::test_no_credential_persistence_sinks` | PASS |
| 12 | All 6 CI gates, live GitHub probe, `tests/rig/` (`44/44`), and complete default + loopback suite pass with `strands_code_agent/` untouched (`D-24`) | `e8db593`, `f160706`, `d0562be` — see verified command outputs below | PASS |

---

## Verified Test & Gate Outputs

- **Default non-integration suite:** `.venv/bin/pytest tests/ -k "not test_stub_server_systemone_decision_routes" -q` -> **1779 passed, 15 deselected**
- **Standalone loopback stub:** `.venv/bin/pytest tests/routing/test_routing.py -k test_stub_server_systemone_decision_routes -q` -> **1 passed, 195 deselected**
- **Live GitHub integration probe (`anthropics/skills`):** `.venv/bin/pytest tests/memory/test_marketplace.py -m integration -v` -> **1 skipped, 15 deselected** (sandboxed) / **1 passed, 15 deselected** in 4.55s (outbound HTTPS enabled)
- **Harness rig contracts:** `.venv/bin/pytest tests/rig/ -q` -> **44 passed** in 0.09s
- **Complexity & Architecture:** `xenon --max-absolute C` green (`_setup_decision_entries C 20` untouched, `run_loop C 18` unchanged, `_skills_message C 13`, `decide C 15`, `marketplace.py` max `C 17`); `lint-imports` **1 kept, 0 broken** (`41 files, 91 dependencies`); `git diff ee42ea2 -- strands_code_agent/` empty.
