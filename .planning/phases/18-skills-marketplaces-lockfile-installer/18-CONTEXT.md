# Phase 18: Skills Marketplaces & Lockfile Installer - Context

**Gathered:** 2026-11-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver `SKILL-03` — remote skills marketplace catalog management and lockfile-pinned skill installation under `strands-code`'s deny-first posture:
- Catalog lifecycle: `/skills marketplace add <owner/repo | local-path> [--name <alias>] [--ref <tag|sha>]`, `list`, `update [<name>]`, and `remove <name>`, stored under `~/.config/strands-code/marketplaces.yaml` (`0o700`, symlink-refused) with cached catalogs in `~/.cache/strands-code/marketplaces/<name>.json`.
- Skill lifecycle: `/skills browse [<marketplace>]`, `/skills install <marketplace>:<skill> | <skill>@<marketplace> | <owner/repo[@ref]> [--skill <name>]`, `/skills update [<name|ns:name>]`, `/skills sync`, and `/skills remove <name|ns:name>` (alias `uninstall`), keeping `AgentSkills.set_available_skills` and `SkillIndex.reload()` atomically synchronized.
- Manifest & source compatibility: `.agent-plugin/marketplace.json`, `.claude-plugin/marketplace.json`, direct GitHub `owner/repo[@ref]` auto-discovery (`SKILL.md` directories), and local filesystem catalog paths.
- Project layout & lockfile: install marketplace skills under `./.agent/skills-marketplaces/<ns>/<skill>/` (preserving `skill_dir.name == skill.name` and keeping `./.agent/skills/` purely `local:`), pinned in `./.agent/skills-lock.json` by 40-char `commit_sha`, deterministic SHA-256 `computed_hash`, and `has_scripts` metadata.
- Completion, rendering & policy defense: dynamic `/<ns>:` tab completion in `SlashCompleter`, third-party provenance framing (`@ <commit_sha[:7]>`) on slash invocation, `print_plain` rendering (`markup=False`), deny-first tarball/symlink/size/zip-slip guards, informational-only `allowed-tools`, fail-closed hash-drift verification on load, and broad repo `[[allow]]` glob downgrade on `.agent/skills*`, `.agent/skills-lock.json`, and `~/.config/strands-code/**`.

Out of scope: MCP server management (`SKILL-04` in `v2.1+`), granting tool permissions from remote `allowed-tools` frontmatter, executing `git` subprocesses for remote fetches, Strands Box OS sandboxing (**Phase 19**, `SANDBOX-01`), `/help`/`@file`/`/review` (**Phase 20**), `strands-agents-evals` (**Phase 21**), and any edits to `strands_code_agent/` (`D-24`).

</domain>

<decisions>
## Implementation Decisions

### Remote Fetch & Catalog Discovery Architecture
- **D-01 (Pure HTTPS Transport + Local-Path Catalogs — Zero `git` Subprocess Surface):**
  - Fetch remote GitHub catalogs and skill archives exclusively via HTTPS (`httpx`) + stdlib `tarfile` inside an isolated module (`strands_code_cli/memory/marketplace.py`): resolve `<ref>` (default branch, tag, branch, or 40-char commit SHA) to an immutable 40-char hex `commit_sha` via GitHub REST API (`https://api.github.com/repos/<owner>/<repo>/commits/<ref>`), then download the pinned repository tarball (`https://api.github.com/repos/<owner>/<repo>/tarball/<commit_sha>`).
  - Support local filesystem catalog directories (`local-path`) for offline / development catalogs (enforcing symlink refusal and file/byte caps identically, using recursive SHA-256 directory verification rather than a network request).
  - Enforce explicit redirect safety on HTTP downloads (`follow_redirects=False` on GitHub API metadata calls; tarball downloads may follow at most one redirect strictly to `https://codeload.github.com/...` or `https://objects.githubusercontent.com/...` without forwarding `Authorization` headers to non-GitHub origins).
  - Read optional `GITHUB_TOKEN` / `GH_TOKEN` strictly inside `strands_code_cli/memory/marketplace.py` (whitespace/control-char sanitized, header-only on `api.github.com`, never persisted to YAML/JSON/logs, and scrubbed in `tests/conftest.py:_PROVIDER_ENV_VARS` unless `@pytest.mark.integration`). Zero `git` subprocess calls. — *Reversibility: moderate — self-contained transport layer in `memory/marketplace.py`.*

- **D-02 (Zero Pre-Registered Marketplaces & Flat `owner--repo` Ad-Hoc Namespaces):**
  - Ship with **zero pre-registered remote marketplaces** (strict opt-in; empty `/skills marketplace list` / `/skills browse` prints helpful `/skills marketplace add ...` usage examples without making any unprompted network requests on startup or browse).
  - Validate user-chosen marketplace aliases strictly (`^[a-z0-9][a-z0-9-]{0,63}$`, forbidding `"local"` and reserved names like `"all"`).
  - Ad-hoc direct installs (`/skills install owner/repo[@ref] [--skill <name>]`) without a registered marketplace alias derive a flat, single-segment sanitized namespace slug `owner--repo` (lowercase alphanumeric + hyphens) under `./.agent/skills-marketplaces/<ns>/<skill>/`, ensuring one directory level between namespace and skill so `AgentSkills` and `Skill.from_directory` stay clean without colons in path components. — *Reversibility: easy — slug/alias validator in `memory/marketplace.py`.*

### Archive Unpack, Lockfile & Supply-Chain Verification
- **D-03 (Manifest Formats, Lockfile Schema & Deny-First Archive Unpack):**
  - Discover installable skills from `.agent-plugin/marketplace.json`, `.claude-plugin/marketplace.json`, or direct GitHub `owner/repo[@ref]` repositories (auto-discovering `skills/<name>/SKILL.md`, `<name>/SKILL.md`, or root `SKILL.md` for single-skill repos).
  - Enforce deny-first unpacking rules in a staging temporary directory before promoting into `./.agent/skills-marketplaces/<ns>/<skill>/`:
    - Reject every symlink, hardlink (`linkname`), FIFO, character/block device, socket, absolute path, `..` traversal component (zip-slip), and `.gitmodules` / git submodule entry.
    - Enforce compressed archive download cap (`<= 25 MiB`) and per-skill unpacked caps (`<= 256` regular files, `<= 5 MiB` total bytes).
    - Validate `SKILL.md` via `Skill.from_file(..., strict=True)` (`skill_dir.name == skill.name`, valid lowercase hyphenated slug, required description) before atomic directory replacement (`os.replace` / backup-swap rollback on failure).
  - Persist `./.agent/skills-lock.json` atomically (`tmp` + `os.replace`, symlink-refused) with schema version (`version: 1`) and per-skill records: `namespace`, `name`, `source`, `repo_url`, `subdir`, `ref`, 40-char `commit_sha`, deterministic SHA-256 `computed_hash` over sorted relative paths + file bytes, `has_scripts`, `script_files`, and ISO-8601 UTC `installed_at`. — *Reversibility: moderate — versioned lockfile schema.*

- **D-04 (Prominent `scripts/*` Warnings & Fail-Closed Lockfile Hash-Drift Verification):**
  - When an installed or updated skill contains files under `scripts/`, install/update completes with a prominent plain-text warning enumerating the bundled `scripts/*` relative paths (reminding the user scripts never auto-execute and remain gated by `shell`/`python_repl` HITL); `/skills update` reports `old_sha[:7] -> new_sha[:7]` plus any newly added or modified `scripts/*` entries.
  - Frontmatter `allowed-tools` stays strictly informational-only (displayed in `/skills show`, never granting tool approvals).
  - On every `SkillIndex` load/reload and `AgentSkills` refresh, verify every installed directory under `./.agent/skills-marketplaces/<ns>/<skill>/` against `./.agent/skills-lock.json`: any skill lacking a matching lock entry, containing any symlink, or failing the recomputed SHA-256 `computed_hash` check is **warn-and-skipped** (excluded from both `SkillIndex` and `AgentSkills.set_available_skills(...)`, surfacing a warning to run `/skills sync` or `/skills remove`).
  - Refresh `AgentSkills.set_available_skills([*verified_marketplace_dirs, DEFAULT_SKILLS_DIR])` so unverified marketplace dirs are omitted and `./.agent/skills/` (`local:`) loads last, guaranteeing `local:<skill>` wins bare-name ties inside both `SkillIndex` and `AgentSkills`. — *Reversibility: easy — hash verification & directory collection helpers.*

### Policy Protection, Completion & Invocation UX
- **D-05 (Protected-Path Policy Downgrade on `.agent/skills*` & `~/.config/strands-code/**`):**
  - In `strands_code_cli/policy/core.py:decide()`, evaluate explicit `[[deny]]` rules first, then check whether a `write` or `edit` target (canonicalized via `realpath`) sits inside `./.agent/skills`, `./.agent/skills/**`, `./.agent/skills-marketplaces`, `./.agent/skills-marketplaces/**`, `./.agent/skills-lock.json`, or `~/.config/strands-code/**`.
  - When `match_rule` yields `Allow()` via a broad repo `[[allow]]` glob (such as `path = "*"`, `path = "**"`, or `path = ".agent/**"`), **downgrade the verdict to `Prompt(...)`** so untrusted turns cannot silently overwrite skills, lockfiles, or marketplace configs, while still letting the user approve intentional edits interactively. — *Reversibility: easy — narrow helper in `policy/core.py`.*

- **D-06 (Dynamic `/<ns>:` Completion, Third-Party Provenance Framing & `print_plain` Rendering):**
  - Extend `SkillIndex` (`strands_code_cli/memory/skills.py`) to scan `./.agent/skills/` (`source = "local"`) alongside verified `./.agent/skills-marketplaces/<ns>/<skill>/` (`source = ns`), keeping `BUILTIN_SLASH_HEADS` collision shadowing, `local:` precedence on bare-name `resolve(name)`, and exact `<ns>:<name>` resolution (`local:<skill>` and `<marketplace>:<skill>`).
  - Update `SlashCompleter` (`strands_code_cli/ui/completer.py`) to extract valid namespaces dynamically from live `get_words()` displays (`/{ns}:{name}`) instead of hardcoding `SKILLS_SOURCE = "local"`, so `/local:` filters local skills, `/<marketplace>:` filters that marketplace's skills, and unknown `<ns>:` offers nothing.
  - Sanitize control characters / ANSI sequences on untrusted catalog/skill metadata and render all `/skills` outputs exclusively through `print_plain` (`markup=False`) so Rich markup tags (`[red]`, `[/]`) never interpret or break output.
  - When dispatching a marketplace skill (`/<ns>:<skill>` or bare `/<skill>` matching a third-party entry), frame the prompt explicitly with third-party provenance (`<ns>:<skill>`, `source`/`repo_url`, `@ <commit_sha[:7]>`) as untrusted external instructions. — *Reversibility: easy — localized to `skills.py`, `completer.py`, and `dispatch/core.py`.*

### Modularity, CI Boundaries & Verification
- **D-07 (Isolated `memory/marketplace.py` Under `xenon <= C (20)` + Hermetic & Live GitHub Probe):**
  - Keep catalog management, manifest parsing, HTTPS fetch, safe tarball unpack, lockfile persistence, and recursive SHA-256 verification inside `strands_code_cli/memory/marketplace.py`, keeping `_skills_message` (`C 14`), `dispatch` (`C 12`), `policy.core.decide` (`C 13`), `run_loop` (`C 18`), and `_setup_decision_entries` (`C 20` untouched) within `xenon --max-absolute C`, keeping zero `entry/` imports (`lint-imports`), keeping `GITHUB_TOKEN`/`GH_TOKEN` isolated from `entry/`/`model/`/`dispatch/`/`cost/`/`loop/` (`test_no_credential_persistence_sinks`), and keeping `strands_code_agent/` untouched (`D-24`).
  - Verify full end-to-end flows offline with `httpx.MockTransport` (in-memory tarballs, `commits/<ref>` + `tarball/<sha>` mocks), local directory catalogs, malicious archive rejection suites (symlinks, hardlinks, `..` zip-slip, `.gitmodules`, oversized payloads), lockfile tamper drift tests, broad `[[allow]]` policy downgrade tests, `SlashCompleter` dynamic `/<ns>:` tests, and `AgentSkills.set_available_skills` sync tests.
  - Include a `@pytest.mark.integration` live GitHub probe verifying real catalog resolution, deterministic tarball SHA-256 lockfile verification, and offline skip behavior when network/rate-limited. — *Reversibility: easy — modular files and tests.*

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/REQUIREMENTS.md` — `SKILL-03`
- `.planning/ROADMAP.md` — Phase 18 goal & 3 success criteria
- `.planning/research/ARCHITECTURE.md` (§4 Skills Marketplaces Seam), `.planning/research/FEATURES.md` (§4), `.planning/research/PITFALLS.md` (Pitfall 6), `.planning/research/STACK.md` (§4)
- `strands_code_cli/memory/skills.py` — `SKILLS_SOURCE`, `BUILTIN_SLASH_HEADS`, `SkillEntry`, `SkillIndex`, `remove_skill`
- `strands_code_cli/ui/completer.py` — `SlashCompleter.get_completions` (`L42-60` currently hardcoding `head != SKILLS_SOURCE`) & `build_completer`
- `strands_code_cli/ui/output.py` — `print_plain` (`markup=False`)
- `strands_code_cli/dispatch/core.py` — `USAGE_HINT` (`L57-67`), `_SKILLS_USAGE` (`L111`), `dispatch` dynamic skill branch (`L362-380`), `_skills_list`, `_skills_reload`, `_skills_message` (`L1875-1956`, `C 14`), `_setup_decision_entries` (`C 20` — do not inflate!)
- `strands_code_cli/entry/main.py` — `build_agent` (`L161-206` constructing `AgentSkills(skills=[...])`)
- `strands_code_cli/loop/core.py` — `_skill_words`, `_refresh_harness_skills`, `run_loop` (`L2503-2543`, `C 18`), `skill_match_note` (`L1882-1904`)
- `strands_code_cli/policy/core.py` — `PolicyConfig`, `match_rule` (`L376-413`), `decide` (`L527-565`, `C 13`)
- `.venv/lib/python3.12/site-packages/strands/vended_plugins/skills/agent_skills.py` & `skill.py` — `AgentSkills`, `set_available_skills`, `_load_skill_paths` (`L300-369`), `Skill.from_file(..., strict=True)`, `Skill.from_directory`
- `tests/conftest.py` (`_PROVIDER_ENV_VARS`), `tests/cost/test_cost_context.py` (`test_no_credential_persistence_sinks`), `tests/memory/test_skills.py`, `tests/policy/test_policy_gate.py`

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Skill.from_file(..., strict=True)` and `Skill.from_directory()` in `strands.vended_plugins.skills` already enforce the `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` slug regex, max 64 chars, `skill_dir.name == skill.name`, YAML frontmatter colon-quoting fallback, and required `description`.
- `AgentSkills.set_available_skills(sources)` accepts a list of individual skill directories (`./.agent/skills-marketplaces/<ns>/<skill>/`) AND parent directories (`DEFAULT_SKILLS_DIR` = `./.agent/skills/`), loading paths sequentially so later entries win duplicate names — meaning `[*(verified_marketplace_skill_dirs), skills.skills_dir]` automatically filters out unverified/tampered marketplace dirs while ensuring `local:<skill>` wins ties.
- `remove_skill()` in `strands_code_cli/memory/skills.py` already demonstrates `resolve()` + `is_symlink()` + `resolved.parent == root_resolved` fail-closed cleanup; sibling symlink-refusing config persistence exists in `ProviderConfig.save()` / `PolicyConfig` (`0o700` dir, `0o600` file, `tmp` + `os.replace`).
- `routing/transports.py:valid_base_url()` and `entry/provider_config.py:_validate_base_url()` establish repo conventions for HTTPS URL validation (no embedded creds, no control chars) and `httpx.Client(follow_redirects=False)`.

### Constraints & Watchpoints
- **No relative `:` in skill dir names:** `Skill.from_directory` / `AgentSkills._load_skill_paths` check `skill.path.name == skill.name` (`^[a-z0-9-]+$`), so colons (`ns:skill`) must NEVER appear in filesystem directory names — keep namespaces strictly as the parent directory (`./.agent/skills-marketplaces/<ns>/<skill>/`) and only synthesize `<ns>:<skill>` in `SkillEntry.namespaced` and `SlashCompleter`.
- **Complexity ceilings (`xenon --max-absolute C`):** `_skills_message` (`C 14`), `dispatch` (`C 12`), `policy.core.decide` (`C 13`), `run_loop` (`C 18`), and `_setup_decision_entries` (`C 20` — untouched) must remain within `<= C (20)`. Delegate subcommand routing (`marketplace`, `browse`, `install`, `update`, `sync`, `remove`) into `memory/marketplace.py` or a small `dispatch` helper rather than bloating `_skills_message`.
- **`test_no_credential_persistence_sinks` (`tests/cost/test_cost_context.py:1070`):** asserts zero `os.environ`/`os.getenv` in `model/model_switch.py`, `cost/cost_context.py`, `dispatch/core.py`, `loop/core.py`, `loop/pump.py`, and `entry/main.py` — keep optional `GITHUB_TOKEN`/`GH_TOKEN` reads strictly inside `memory/marketplace.py`.
- **`build_agent` & `run_loop` wiring (`entry/main.py` & `loop/core.py`):** Notice `entry/main.py:167` currently passes `AgentSkills(skills=[DEFAULT_SKILLS_DIR])` at agent construction and `loop/core.py:2538` calls `plugin.set_available_skills([str(skills.skills_dir)])` on refresh — BOTH call sites must supply the verified `skills.plugin_skill_sources()` (verified marketplace skill dirs + `./.agent/skills`) so newly started sessions AND `/skills reload` / install / update / sync / remove see marketplace skills seamlessly (including respecting `btw_session.has_live` deferral).
- **Protected-path policy check in `policy/core.py`:** `match_rule` checks raw, absolute, `realpath`, and relative candidates; protected-path downgrade must inspect `realpath` against resolved cwd `.agent/skills*` + `.agent/skills-lock.json` AND `platformdirs.user_config_dir("strands-code")` so symlinks inside the workspace pointing into `~/.config/strands-code/` cannot bypass via relative glob matching.
- **`strands_code_agent/` immutability (`D-24`) & `lint-imports`:** Zero edits under `strands_code_agent/`, zero `entry/` imports from `memory/`.

</code_context>

<specifics>
## Specific Ideas

- **Deterministic skill directory hash:** Walk sorted POSIX relative file paths under the skill directory (refusing any symlink anywhere in the tree via `lstat`/`is_symlink`), feed `b"{rel_path}\0{size}\0{sha256_or_bytes}"` into `hashlib.sha256()`, and format `"sha256:<hexdigest>"` so cross-platform line/mtime differences do not cause spurious drift while any byte edit, added file, deleted file, or symlink fails verification deterministically.
- **Friendly empty marketplace guidance & `docs/QUICKSTART.md` note:** Empty `/skills marketplace list` or `/skills browse` prints concise copy-pasteable commands (`/skills marketplace add owner/repo`, `/skills install owner/repo`) without hitting the network; Wave 3 adds a short Skills Marketplaces section to `docs/QUICKSTART.md`.
- **Clean subcommand ergonomics:**
  - Accept both `marketplace:skill` and `skill@marketplace` on `/skills install`.
  - Accept bare `<skill>` (when unambiguous across installed non-local skills, or explicit `<ns>:<skill>`) on `/skills remove` / `/skills uninstall`, while refusing to delete `./.agent/skills/` local skills unless targeting `./.agent/skills/` cleanly as before (preserving all existing MVP `/skills remove` tests).
  - `/skills show <name>` works cleanly for both `local:<name>` and `<ns>:<name>`, showing source/URL, pinned `commit_sha[:7]`, verified status, bundled `scripts/*`, and informational `allowed-tools`.

</specifics>

<deferred>
## Deferred Ideas

- Guarded `git` CLI fallback for arbitrary non-GitHub HTTPS/SSH Git hosts (GitLab, Bitbucket, private Gitea).
- `--allow-scripts` explicit opt-in gate or cryptographic signature / Sigstore attestation verification layered onto `skills-lock.json`.
- MCP server registry & tool consumption (`SKILL-04`, `v2.1+`).
- Strands Box Linux sandbox floor & Dogwood policy — **Phase 19 (`SANDBOX-01`)**.
- `/help`, `@file` / `/file`, `/review` — **Phase 20 (`LOOP-06`, `TOOL-05`, `REVIEW-01`)**.
- `strands-agents-evals` & red-team suite — **Phase 21 (`EVAL-01`)**.

</deferred>

*Phase: 18-skills-marketplaces-lockfile-installer*
*Context gathered: 2026-11-24*
