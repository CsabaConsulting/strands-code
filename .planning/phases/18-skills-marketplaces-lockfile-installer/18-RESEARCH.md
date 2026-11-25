# Phase 18: Skills Marketplaces & Lockfile Installer — Research

**Researched:** 2026-11-24
**Phase:** `18-skills-marketplaces-lockfile-installer`
**Requirements:** `SKILL-03`
**Sources Inspected Directly:**
- Installed SDK `strands-agents==1.66.0`: `.venv/lib/python3.12/site-packages/strands/vended_plugins/skills/{__init__,agent_skills,skill}.py`
- Existing CLI skills, completer, dispatch, loop & policy layers: `strands_code_cli/memory/skills.py`, `strands_code_cli/ui/completer.py`, `strands_code_cli/ui/output.py`, `strands_code_cli/dispatch/core.py`, `strands_code_cli/entry/main.py`, `strands_code_cli/loop/core.py`, `strands_code_cli/policy/core.py`
- Existing tests & CI invariants: `tests/memory/test_skills.py`, `tests/policy/test_policy.py`, `tests/conftest.py`, `tests/cost/test_cost_context.py` (`test_no_credential_persistence_sinks`), `pyproject.toml` (`importlinter`, `ruff`, `xenon`)
- Ecosystem catalog conventions: `.claude-plugin/marketplace.json` (`anthropics/skills` schema) & `.agent-plugin/marketplace.json` / direct `owner/repo[@ref]` (`skills.sh`) conventions

---

## 1. Installed Upstream `strands.vended_plugins.skills` Seam (`strands-agents==1.66.0`)

Inspecting `strands/vended_plugins/skills/skill.py` and `agent_skills.py` confirms four critical invariants that Phase 18 builds on directly:

| Symbol / Method | Behavior in `strands-agents 1.66.0` | Implication for `SKILL-03` |
|---|---|---|
| `Skill._SKILL_NAME_PATTERN` (`skill.py:L23-24`, `L117-167`) | `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, 1–64 chars, no `--`, no colons (`:`), and **must match parent directory name** (`dir_path.name != name` raises `ValueError` under `strict=True`!) | Installed marketplace skills MUST live at `./.agent/skills-marketplaces/<ns>/<skill>/SKILL.md` (so `skill_dir.name == skill.name`, zero colons in folder names). Colons exist only in virtual `namespaced = "<ns>:<skill>"`. |
| `Skill.from_file(..., strict=True)` (`skill.py:L222`) | Validates frontmatter YAML, `name` regex, length `<= 64`, `description`, and `dir_path.name == name` cleanly | Run `Skill.from_file(staged_skill_dir, strict=True)` inside a staging temp dir BEFORE promoting into `./.agent/skills-marketplaces/<ns>/<skill>/`. |
| `Skill.allowed_tools` (`skill.py:L183-189`, `L238`) | Parsed into `list[str] | None`; explicitly commented `"(Experimental: not yet enforced)"` | Must remain strictly informational-only in `/skills show`; NEVER convert `allowed-tools` into `PolicyConfig` `[[allow]]` rules (`T-18-05`). |
| `AgentSkills.set_available_skills(sources)` (`agent_skills.py:L261-369`) | Accepts a `list` mixing **individual skill directories** (e.g. `./.agent/skills-marketplaces/<ns>/<skill>`) and **parent directories** (e.g. `./.agent/skills`); resets `self._agent_skills`; `_load_skill_paths` iterates `self._skill_paths` in order, logging & **overwriting earlier duplicates** when `skill.name in skills` (`L333-335`) | Passing `[*(verified_marketplace_skill_dirs), str(skills.skills_dir)]` guarantees TWO security/UX invariants at once: (1) tampered/unverified marketplace skills never reach the model, and (2) `local:<skill>` (`./.agent/skills/`) loads **last**, winning bare-name ties in `AgentSkills` just as it does in `SkillIndex`. |

---

## 2. Supported Catalog & Source Formats

### 2.1 `.claude-plugin/marketplace.json` & `.agent-plugin/marketplace.json`

Ecosystem repositories (`anthropics/skills`, team plugin marketplaces, Agent Plugins 1.0 bundles) publish JSON manifests under `.claude-plugin/marketplace.json` or `.agent-plugin/marketplace.json`:

1. **Nested `plugins[]` schema (`anthropics/skills` & Agent Plugins 1.0):**
   ```json
   {
     "name": "anthropic-agent-skills",
     "description": "Official collection",
     "plugins": [
       {
         "name": "document-skills",
         "description": "PDF and Office skills",
         "source": "./packages/document-skills",
         "strict": false,
         "skills": ["./pdf", "./docx"]
       }
     ]
   }
   ```
   - `plugin["source"]` may be a relative repo subdir string (`"./"`, `"."`, `"./plugins/doc"`) **or** a source dict (`{"source": "git-subdir" | "github", "url": "https://github.com/owner/repo[.git]" | "repo": "owner/repo", "path": "packages/doc", "ref": "main", "sha": "<40-hex>"}`).
   - When `plugin.get("skills")` is present (array of relative skill paths like `["./pdf"]` or objects), resolve each entry relative to `source` (rejecting any `..` traversal or absolute path escaping repo root).
   - When `plugin.get("skills")` is absent, scan under `source` for `SKILL.md` / `skills/*/SKILL.md` / `*/SKILL.md`.
2. **Flat `skills[]` schema (`.agent-plugin/marketplace.json` / simplified catalogs):**
   ```json
   {
     "name": "team-skills",
     "description": "Curated skills",
     "skills": [
       {"name": "pdf-extract", "description": "...", "path": "skills/pdf-extract"}
     ]
   }
   ```
   - Supports `"path"`, `"subdir"`, `"source"`, or `"url"`/`"repo"` per entry cleanly with path-containment validation.
3. **Direct GitHub `owner/repo[@ref]` / local directory auto-discovery (no `marketplace.json`):**
   - When neither `.agent-plugin/marketplace.json` nor `.claude-plugin/marketplace.json` exists in a repository or local directory, scan deterministic candidate locations inside the root:
     - `skills/<name>/SKILL.md` (standard convention)
     - `<name>/SKILL.md` (flat multi-skill repo)
     - Root `SKILL.md` (single-skill repo, e.g. named from `SKILL.md` frontmatter `name`)
   - Local directory catalogs (`local-path`) share the exact same 3 discovery layers offline without hitting HTTP.

---

## 3. Transport, Redirect, Archive & Lockfile Security (`D-01`–`D-05`)

### 3.1 Pure HTTPS GitHub Fetch + Zero `git` Subprocess Surface (`D-01`)
- Validate `owner` / `repo` strictly against GitHub identifier rules (`^[A-Za-z0-9_.-]+$`, rejecting `.` / `..` / traversal / whitespace / control chars).
- Validate `https://github.com/<owner>/<repo>` URLs strictly (HTTPS only for remote catalogs; no embedded credentials, query, fragment, or control chars).
- Resolve mutable `ref` (if omitted, query `GET https://api.github.com/repos/<owner>/<repo>` for `default_branch` or resolve `commits/HEAD`) -> `GET https://api.github.com/repos/<owner>/<repo>/commits/<ref>` (strict `40`-char lowercase hex regex `^[0-9a-f]{40}$` on returned `sha`).
- Fetch archive tarball via `GET https://api.github.com/repos/<owner>/<repo>/tarball/<commit_sha>` with `follow_redirects=False`:
  - Send `Authorization: Bearer <token>` (`GITHUB_TOKEN` / `GH_TOKEN`, sanitized via control-char/whitespace check) **only** to `api.github.com`.
  - On `301`/`302`/`303`/`307`/`308` redirect, allow **at most one hop**, verify target URL uses `https://` AND hostname is in `("codeload.github.com", "objects.githubusercontent.com")`, and follow WITHOUT `Authorization` header (never leak GitHub tokens to third-party origins!). Any other redirect host or second hop fails closed.
  - Stream/enforce compressed download cap (`MAX_TARBALL_BYTES = 25 * 1024 * 1024`, checking `Content-Length` pre-read AND streamed byte count).

### 3.2 Deny-First Archive Unpack & Deterministic SHA-256 Lockfile (`D-03`, `D-04`)
- Extract **only** the selected `subdir` inside GitHub's single top-level strip prefix (`<owner>-<repo>-<shortsha>/`) into an isolated temporary directory using `tarfile.open(..., "r:*")`:
  - Reject ANY member (across the selected subdir — and reject `.gitmodules` anywhere in the selected tree) where:
    - `member.issym()` or `member.islnk()` or `member.isfifo()` or `member.ischr()` or `member.isblk()` or `member.isdev()` (`not (member.isdir() or member.isreg())`), OR non-empty `member.linkname`.
    - Path contains `\x00`, starts with `/` or `\`, or has `..` components (zip-slip).
    - Member basename equals `.gitmodules` (submodule guard).
    - Unpacked regular file count exceeds `MAX_SKILL_FILES = 256` or unpacked byte total exceeds `MAX_SKILL_BYTES = 5 * 1024 * 1024` (reading bounded bytes per member via `extractfile` instead of blindly trusting headers, avoiding `tarfile.extractall()` quirks).
- Normalize `SKILL.md` / `skill.md`, validate `Skill.from_file(staged_skill_dir, strict=True)` (`skill_dir.name == skill.name`), scan `scripts/*` files (`has_scripts = bool(script_files)`), and compute deterministic hash:
  - Sort all relative POSIX file paths in `staged_skill_dir` recursively (refusing symlinks anywhere); update `hashlib.sha256()` with `f"{rel_posix}\0{len(data)}\0".encode("utf-8") + data` per file; format `"sha256:<hexdigest>"`.
- Atomically swap staged directory into `./.agent/skills-marketplaces/<ns>/<skill>/` (refusing symlinks along parent chain: `./.agent`, `skills-marketplaces`, `<ns>`), then write `./.agent/skills-lock.json` (`version: 1`, symlink-refused, `tmp` + `os.replace`).

### 3.3 Protected-Path Policy Downgrade (`D-05`)
- In `strands_code_cli/policy/core.py:decide()`:
  - Keep explicit `[[deny]]` evaluation FIRST (deny still wins unconditionally).
  - After evaluating `[[allow]]` and before returning `Allow()`, check when `tool_name in ("write", "edit")` if the canonicalized target (`os.path.realpath(resolve(raw, base))`) sits inside or equals:
    - `base / ".agent" / "skills"` (or any descendant),
    - `base / ".agent" / "skills-marketplaces"` (or any descendant),
    - `base / ".agent" / "skills-lock.json"`, OR
    - `Path(os.path.realpath(platformdirs.user_config_dir("strands-code")))` (containing `marketplaces.yaml`, `policy.toml`, `routing.yaml`, `config.yaml`, etc.).
  - When matched by an `[[allow]]` rule, return `Prompt(reason=f"Protected skills/config path ({raw}): approve explicit {tool_name}")` instead of silent `Allow()`. Deliberate manual user approval still works, while broad repo `[[allow]]` globs (`path = "*"`, `path = ".agent/**"`) are blocked from silent tampering.

---

## 4. Existing Codebase Touchpoints & Compatibility Traps

Reading the existing codebase surfaced **seven exact invariants** that plans `18-01`..`18-03` must preserve:

1. **MVP Symlink Test Preserved for `./.agent/skills/` (`tests/memory/test_skills.py:L350`):** `test_remove_symlinked_skill_dir_refused` intentionally creates a symlinked skill dir inside `./.agent/skills/` and asserts `index.resolve("linky") is not None` followed by `Refused to remove skill 'local:linky'` on `/skills remove`. Therefore:
   - `./.agent/skills/` (`local:`) keeps exact MVP `Skill.from_directory()` loading + `remove_skill()` symlink refusal.
   - `./.agent/skills-marketplaces/` (`D-04`) strictly refuses any symlinked root, symlinked namespace dir, symlinked skill dir, or symlinked inner file — warn-and-skipping from both `SkillIndex` and `AgentSkills`.
2. **Exact Backward-Compatible Reply Strings (`tests/memory/test_skills.py`):**
   - `test_bare_list_empty_or_missing_reports_no_skills` (`L264`) asserts `"No skills loaded (./.agent/skills missing or empty)."` when zero skills exist -> keep exact string for empty `/skills`!
   - `test_remove_deletes_skill_dir` (`L314`) asserts `"Removed skill 'local:gone'."` -> keep exact string for removing a skill!
   - `test_skill_slash_routes_agent_with_instructions_and_input` (`L110`) asserts `"The user explicitly invoked the 'local:pdf-tools' skill..."` -> keep exact template for `entry.source == "local"`, and use the provenance-framed template (`'@ <commit_sha[:7]>'`, third-party source URL) when `entry.source != "local"`.
   - `test_unknown_verb_returns_usage` (`L370`) & `test_usage_hint_advertises_skills` (`L383`) intentionally check `_SKILLS_USAGE` and `USAGE_HINT` -> update both constants AND those two tests in Plan `18-02` Task 2 when expanding `/skills` subcommands.
3. **Atomic Reload Order (`test_failed_harness_refresh_leaves_index_stale`, `L615`):** `_skills_reload(skills, harness_refresh)` MUST refresh `harness_refresh()` **before** calling `skills.reload()`. That means `loop/core.py:_refresh_harness_skills()` must read verified skill dirs from disk via `skills.plugin_skill_sources()` **without** mutating `skills._entries`, so if `harness_refresh()` raises, `skills._entries` remains stale cleanly matching the test.
4. **Two Construction/Sync Call Sites for `AgentSkills`:** `entry/main.py:L167` (`build_agent`) initializes `AgentSkills(skills=[DEFAULT_SKILLS_DIR])`, and `loop/core.py:L2538` (`_refresh_harness_skills`) refreshes `plugin.set_available_skills([str(skills.skills_dir)])`. BOTH sites must use `SkillIndex(...).plugin_skill_sources()` so marketplace skills load on fresh sessions, `/skills install|update|sync|remove`, AND `/skills reload`!
5. **Dynamic Namespaces in `SlashCompleter` (`strands_code_cli/ui/completer.py:L49-57`):** Currently hardcodes `if head != SKILLS_SOURCE: return` and `display.startswith(f"/{SKILLS_SOURCE}:")`. Generalizing this to inspect `/{ns}:{bare}` prefixes present in `self._get_words()` keeps `/local:` working identically while enabling `/<marketplace>:` tab completion automatically and still returning `[]` for unknown prefixes (`test_unknown_namespace_suggests_nothing`, `L703`).
6. **`xenon --max-absolute C` Ceilings & `lint-imports`:**
   - `_setup_decision_entries` (`C 20` — NEVER touch), `run_loop` (`C 18` — do not add branches), `_skills_message` (`C 14` — dispatch subcommands cleanly via helpers into `memory/marketplace.py` so `_skills_message` stays `<= C 15`), `policy.core.decide` (`C 13` — extract `_is_protected_write()` helper so `<= C 14`), `dispatch` (`C 12`).
   - `lint-imports`: `memory/` must NEVER import from `entry/`.
7. **Credential Isolation (`tests/cost/test_cost_context.py:L1070` & `tests/conftest.py`):** Keep `os.environ` reads for `GITHUB_TOKEN`/`GH_TOKEN` strictly inside `strands_code_cli/memory/marketplace.py` (never in `dispatch/`, `loop/`, `entry/main.py`, `model/`, `cost/`), and add `GITHUB_TOKEN` + `GH_TOKEN` to `tests/conftest.py:_PROVIDER_ENV_VARS` so host tokens never leak into default offline tests while honoring `@pytest.mark.integration`.
