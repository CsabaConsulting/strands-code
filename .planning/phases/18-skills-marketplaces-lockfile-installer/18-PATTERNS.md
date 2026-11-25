# Phase 18 Codebase Patterns & Extension Seams

**Created:** 2026-11-24
**Purpose:** Concrete module contracts, archive/lockfile schemas, policy downgrade rules, `SlashCompleter` / `AgentSkills` integration seams, and CI ceilings across Plans `18-01`, `18-02`, and `18-03`.

---

## 1. Marketplace, Lockfile & Safe Unpack Module (`strands_code_cli/memory/marketplace.py`)

New cohesive module under `strands_code_cli/memory/` (zero imports from `strands_code_cli.entry` so `lint-imports` stays `1 kept, 0 broken`; every function `CC <= 16`).

- **Locations & Constants (`D-01`–`D-04`):**
  - `_MARKETPLACES_DIR_NAME = "strands-code"` (`~/.config/strands-code/marketplaces.yaml`, `0o700` dir, `0o600` file, symlink-refused)
  - `_CACHE_DIR_NAME = "strands-code"` (`~/.cache/strands-code/marketplaces/<name>.json`, `0o700` dir, `0o600` file, symlink-refused)
  - `MARKETPLACES_SKILLS_REL = Path(".agent") / "skills-marketplaces"` (`./.agent/skills-marketplaces/<ns>/<skill>/`)
  - `SKILLS_LOCK_REL = Path(".agent") / "skills-lock.json"` (`version: 1`)
  - `MAX_TARBALL_BYTES = 25 * 1024 * 1024` (25 MiB compressed download cap)
  - `MAX_SKILL_FILES = 256` and `MAX_SKILL_BYTES = 5 * 1024 * 1024` (5 MiB unpacked per skill)
  - `HTTP_TIMEOUT_SECONDS = 20.0`, `_ALLOWED_TARBALL_HOSTS = frozenset({"codeload.github.com", "objects.githubusercontent.com"})`
  - `_SHA_RE = re.compile(r"^[0-9a-f]{40}$")`, `_ALIAS_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")`, `_GITHUB_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_.-]+$")`

- **Dataclasses (`D-01`–`D-03`):**
  - `MarketplaceEntry(name: str, source: str, kind: str, ref: str | None = None, added_at: str = "")` where `kind` is `"github"` or `"local"`.
  - `CatalogSkill(name: str, description: str, marketplace: str, source: str, repo_url: str, subdir: str, ref: str | None = None, commit_sha: str | None = None)`
  - `LockEntry(namespace: str, name: str, source: str, repo_url: str, subdir: str, ref: str, commit_sha: str, computed_hash: str, has_scripts: bool = False, script_files: list[str] = field(default_factory=list), installed_at: str = "")`
  - `VerifiedMarketplaceSkill(namespace: str, name: str, path: Path, entry: LockEntry)` & result dataclasses (`InstallOutcome`, `UpdateOutcome`, `SyncOutcome`).

- **HTTP Client & Credential Seam (`D-01`, `D-07`):**
  - `make_marketplace_client(timeout: float = HTTP_TIMEOUT_SECONDS) -> httpx.Client`: returns `httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=False)` so `tests/memory/test_marketplace.py` can inject `httpx.MockTransport` cleanly at one seam (exact `routing/transports.py` testability pattern!).
  - `read_github_token() -> str | None`: reads `GITHUB_TOKEN` then `GH_TOKEN` (`.strip()`, returns `None` if empty or containing control chars `< 0x20` / `0x7f`). Attached **only** to `https://api.github.com/...` requests; NEVER forwarded on redirects to `codeload.github.com` / `objects.githubusercontent.com` or written to disk/logs.
  - `sanitize_display(value: object, max_len: int = 240) -> str`: strips ASCII control chars (`< 0x20`, `0x7f`), collapses newlines/tabs to spaces, caps length — prevents ANSI terminal escape injection in catalog/skill metadata while keeping Rich `[...]` brackets literal for `print_plain(markup=False)`.

- **Catalog Discovery & Extraction (`D-02`, `D-03`):**
  - `github_repo_slug(owner: str, repo: str) -> str`: derives sanitized flat namespace `<owner>--<repo>` (lowercase alphanumeric + hyphens, truncated `<= 64` chars without trailing hyphens) matching `Skill._SKILL_NAME_PATTERN` style so `owner/repo` installs use `./.agent/skills-marketplaces/<owner--repo>/<skill>/`.
  - `parse_github_spec(spec: str) -> tuple[str, str, str | None]`: accepts `owner/repo`, `owner/repo@ref`, or `https://github.com/owner/repo[.git][@ref]`, rejecting embedded credentials, queries, fragments, `.` / `..` segments, and non-HTTPS remotes.
  - `discover_catalog_from_tree(root: Path, ...) -> list[CatalogSkill]`: checks `.agent-plugin/marketplace.json`, then `.claude-plugin/marketplace.json` (`plugins[]` w/ `skills[]` or relative `source`, plus flat `skills[]`, supporting cross-repo `git-subdir` / `github` dicts too), then direct auto-discovery (`skills/*/SKILL.md`, `*/SKILL.md`, root `SKILL.md`).
  - `extract_tarball_subdir_safe(tar_bytes: bytes, *, subdir: str, skill_name: str, staging_dir: Path) -> tuple[Path, list[str]]`: validates tar archive members safely (strips single top-level `<repo>-<sha>/` prefix, refuses any `.gitmodules`, symlinks, hardlinks, FIFOs, devices, absolute paths, `..` zip-slip, `> MAX_SKILL_FILES`, `> MAX_SKILL_BYTES`, runs `Skill.from_file(target_dir, strict=True)`), and returns `(target_dir, script_files)`.
  - `compute_skill_dir_hash(skill_dir: Path) -> str`: raises `ValueError` on any symlink/non-regular file in the tree; feeds sorted POSIX relative paths + byte counts + contents into `hashlib.sha256()`, returning `f"sha256:{digest}"`.
  - `verify_installed_marketplace_skills(cwd: Path) -> tuple[list[VerifiedMarketplaceSkill], list[str]]`: scans `./.agent/skills-marketplaces/` cleanly; refuses symlinks at every depth; compares `compute_skill_dir_hash(skill_dir)` against `./.agent/skills-lock.json` (`LockEntry.computed_hash`); returns `(verified, warnings)` where tampered/unlocked skills are omitted (`warn-and-skip`) and emit actionable `/skills sync` / `/skills remove` warnings.

---

## 2. Multi-Namespace `SkillIndex` & Dynamic `SlashCompleter` (`D-04`, `D-06`)

- **`strands_code_cli/memory/skills.py`:**
  - Extend `SkillEntry` with optional provenance metadata (`commit_sha: str | None = None`, `source_url: str | None = None`, `has_scripts: bool = False`).
  - Extend `SkillIndex.__init__(self, skills_dir=Path("./.agent/skills"), marketplaces_dir=None, lockfile_path=None)`:
    - Preserve exact `SkillIndex(skills_dir=...)` zero-extra-arg signature for all existing callers & `test_skills.py`!
    - When `marketplaces_dir` / `lockfile_path` are `None`, derive siblings cleanly from `self.skills_dir.parent` (`skills_dir.parent / "skills-marketplaces"`, `skills_dir.parent / "skills-lock.json"`), so `tmp_path`-based tests overriding only `skills_dir=tmp_path / ".agent" / "skills"` work hermetic-by-default!
  - `_ensure_loaded()`:
    1. Load `./.agent/skills/` (`SKILLS_SOURCE = "local"`) via `Skill.from_directory(self.skills_dir)` preserving Phase 6 behavior (`test_remove_symlinked_skill_dir_refused`).
    2. Load verified marketplace skills via `verify_installed_marketplace_skills(marketplaces_dir, lockfile_path)` (recording drift warnings into `self._warnings`). Skip symlinked marketplace roots/entries and skip unverified/drifted skills cleanly!
    3. Keep entries deterministically indexed by `<ns>:<name>` and bare-name map where `local:` wins bare-name resolution (`local` > unambiguous single marketplace match > fail-closed ambiguous notice or explicit `<ns>:<name>`).
  - `plugin_skill_sources(self) -> list[str]` (AND read-only `discover_plugin_sources(skills_dir)` helper): returns `[*(sorted verified marketplace skill dirs), str(self.skills_dir)]` directly from disk **without mutating cached `_entries`** so `test_failed_harness_refresh_leaves_index_stale` continues to hold.

- **`strands_code_cli/ui/completer.py`:**
  - Replace hardcoded `if head != SKILLS_SOURCE: return` / `display.startswith(f"/{SKILLS_SOURCE}:")` with dynamic prefix inspection over live `words = self._get_words()`:
    - When `"/"` contains `":"`, `prefix = f"/{head}:"`; emit matching completions `(bare, display)` where `display.startswith(prefix)` and `bare.startswith(tail)`.
    - If `head` matches no `/{head}:` entry in `get_words()`, yields `[]` cleanly (`test_unknown_namespace_suggests_nothing` stays green!).

---

## 3. Protected-Path Policy Downgrade (`strands_code_cli/policy/core.py`)

- Add `_is_protected_skills_or_config_path(raw: object, base: Path) -> bool`:
  - Uses `os.path.realpath(resolve(raw, base))` against:
    - `base / ".agent" / "skills"` (`==` or inside `parents`)
    - `base / ".agent" / "skills-marketplaces"` (`==` or inside `parents`)
    - `base / ".agent" / "skills-lock.json"` (`==`)
    - `Path(os.path.realpath(platformdirs.user_config_dir("strands-code")))` (`==` or inside `parents`)
  - Called in `decide()` **after** `[[deny]]` checks and **after** `[[allow]]` match: when `tool_name in ("write", "edit")` and `_is_protected_skills_or_config_path(tool_input.get("path", ""), base)`, return `Prompt(reason=f"Protected path ({raw}): approve explicit {tool_name}")` instead of `Allow()`. (`decide` CC rises from `13` -> `15`, safely below `C 20`).

---

## 4. `/skills` Dispatch, Provenance Framing & `AgentSkills` Sync

- **`strands_code_cli/dispatch/core.py`:**
  - Keep `_setup_decision_entries` (`CC 20`) untouched.
  - Route `_skills_message(rest, skills, harness_refresh)` via a small dispatch table / helper delegating `marketplace`, `browse`, `install`, `update`, `sync`, `remove|uninstall`, `show`, `reload|refresh` (`_skills_message` stays `<= C 15`).
  - Mutating commands (`install`, `update`, `sync`, `remove`) perform atomic harness refresh + `skills.reload()` via `_skills_reload()`, reporting any deferral note and printing bundled `scripts/*` / `old_sha -> new_sha` warnings cleanly through `print_plain`.
  - Dynamic slash invocation (`dispatch()` `L362-380`):
    - Keep exact `"The user explicitly invoked the 'local:...' skill..."` wording when `entry.source == "local"` (`test_skill_slash_routes_agent_with_instructions_and_input`).
    - When `entry.source != "local"`, prepend explicit third-party provenance framing:
      `"The user explicitly invoked third-party marketplace skill '{entry.namespaced}' ({entry.source_url or entry.source} @ {short_sha})..."` alongside untrusted-directive reminder.

- **`strands_code_cli/entry/main.py` & `strands_code_cli/loop/core.py`:**
  - `entry/main.py:L167`: initialize `AgentSkills(skills=discover_plugin_sources(Path(DEFAULT_SKILLS_DIR)))` so verified marketplace skills are available from turn 1.
  - `loop/core.py:L2538`: call `plugin.set_available_skills(skills.discover_plugin_sources())` inside `_refresh_harness_skills()` so runtime installs/updates/syncs/removals/reloads sync `AgentSkills` without mutating `skills._entries` prematurely (`test_failed_harness_refresh_leaves_index_stale`).
  - Pass `cwd=skills.skills_dir.parent.parent` (or `skills.skills_dir`) context cleanly via `skills` object without adding any `os.environ` read in `dispatch/`, `entry/main.py`, or `loop/core.py` (`test_no_credential_persistence_sinks` stays green).
