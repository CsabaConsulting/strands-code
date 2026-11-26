"""Multi-namespace skill index over ./.agent/skills and ./.agent/skills-marketplaces (SKILL-01, SKILL-03)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from strands.vended_plugins.skills import Skill

from strands_code_cli.memory.marketplace import (
    remove_installed_skill,
    sanitize_display,
    verify_installed_marketplace_skills,
)
from strands_code_cli.platform_io import refuse_symlink

SKILLS_SOURCE = "local"
"""Namespace source for local project skills; marketplace prefixes derive from directory names."""

BUILTIN_SLASH_HEADS = frozenset(
    {
        "exit",
        "resume",
        "rename",
        "forget",
        "diff",
        "search",
        "policy",
        "mode",
        "approve",
        "model",
        "models",
        "cost",
        "compact",
        "clear",
        "context",
        "skills",
        "skill",
        "memory",
        "init",
        "btw",
        "route",
        "codeact",
        "code",
        "tool",
    }
)
"""Builtin slash heads (no leading slash) that always win collisions (D-02).

Mirrors the ``dispatch`` branches.
"""


@dataclass
class SkillEntry:
    """One loaded local or marketplace skill: SDK record plus provenance metadata."""

    name: str
    source: str = SKILLS_SOURCE
    namespaced: str = ""
    description: str = ""
    path: Path | None = None
    shadowed: bool = False
    instructions: str = ""
    allowed_tools: list[str] | None = field(default=None)
    commit_sha: str | None = None
    source_url: str | None = None
    has_scripts: bool = False
    script_files: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.namespaced:
            self.namespaced = f"{self.source}:{self.name}"


def _derive_marketplace_paths(
    skills_dir: Path,
    marketplaces_dir: str | Path | None,
    lockfile_path: str | Path | None,
) -> tuple[Path, Path]:
    mp_dir = (
        Path(marketplaces_dir)
        if marketplaces_dir is not None
        else skills_dir.parent / "skills-marketplaces"
    )
    lk_path = (
        Path(lockfile_path)
        if lockfile_path is not None
        else skills_dir.parent / "skills-lock.json"
    )
    return mp_dir, lk_path


def discover_plugin_sources(
    skills_dir: str | Path,
    marketplaces_dir: str | Path | None = None,
    lockfile_path: str | Path | None = None,
) -> list[str]:
    """Return read-only AgentSkills source list with local last so local wins ties."""
    local_root = Path(skills_dir)
    mp_dir, lk_path = _derive_marketplace_paths(
        local_root, marketplaces_dir, lockfile_path
    )
    verified, _warnings = verify_installed_marketplace_skills(mp_dir, lk_path)
    return [*(str(item.path) for item in verified), str(local_root)]


class SkillIndex:
    """Load-once index over local skills and lockfile-verified marketplace skills."""

    def __init__(
        self,
        skills_dir: str | Path = Path("./.agent/skills"),
        marketplaces_dir: str | Path | None = None,
        lockfile_path: str | Path | None = None,
    ) -> None:
        raw = Path(skills_dir)
        if raw.is_symlink():
            raise ValueError(f"Skills dir must not be a symlink: {raw}")
        refuse_symlink(raw, "skills dir", max_ancestors=1)
        self.skills_dir = raw
        self.marketplaces_dir, self.lockfile_path = _derive_marketplace_paths(
            raw, marketplaces_dir, lockfile_path
        )
        self._entries: dict[str, SkillEntry] | None = None
        self._drift_warnings: list[str] = []

    def _load_local_entries(self, entries: dict[str, SkillEntry]) -> None:
        if not self.skills_dir.exists():
            return
        try:
            loaded = Skill.from_directory(self.skills_dir)
        except FileNotFoundError:
            return  # raced deletion or non-dir root: treat as empty
        for skill in loaded:
            shadowed = skill.name.lower() in BUILTIN_SLASH_HEADS
            entry = SkillEntry(
                name=skill.name,
                source=SKILLS_SOURCE,
                namespaced=f"{SKILLS_SOURCE}:{skill.name}",
                description=sanitize_display(skill.description or ""),
                path=skill.path,
                shadowed=shadowed,
                instructions=skill.instructions or "",
                allowed_tools=list(skill.allowed_tools)
                if skill.allowed_tools
                else None,
            )
            entries[entry.namespaced] = entry

    def _load_marketplace_entries(self, entries: dict[str, SkillEntry]) -> list[str]:
        verified, drift_warnings = verify_installed_marketplace_skills(
            self.marketplaces_dir, self.lockfile_path
        )
        for item in verified:
            try:
                skill = Skill.from_file(item.path, strict=True)
            except Exception as exc:
                drift_warnings.append(
                    f"Skipped invalid marketplace skill '{item.namespace}:{item.name}'"
                    f" ({sanitize_display(exc)}) — run '/skills sync'."
                )
                continue
            shadowed = skill.name.lower() in BUILTIN_SLASH_HEADS
            entry = SkillEntry(
                name=skill.name,
                source=item.namespace,
                namespaced=f"{item.namespace}:{skill.name}",
                description=sanitize_display(skill.description or ""),
                path=skill.path,
                shadowed=shadowed,
                instructions=skill.instructions or "",
                allowed_tools=list(skill.allowed_tools)
                if skill.allowed_tools
                else None,
                commit_sha=item.entry.commit_sha,
                source_url=item.entry.repo_url or item.entry.source,
                has_scripts=item.entry.has_scripts,
                script_files=tuple(item.entry.script_files),
            )
            entries[entry.namespaced] = entry
        return drift_warnings

    def _ensure_loaded(self) -> None:
        if self._entries is not None:
            return
        entries: dict[str, SkillEntry] = {}
        self._load_local_entries(entries)
        self._drift_warnings = self._load_marketplace_entries(entries)
        self._entries = entries

    def discover_plugin_sources(self) -> list[str]:
        """Discover verified marketplace skill dirs + local root without mutating cache."""
        return discover_plugin_sources(
            self.skills_dir, self.marketplaces_dir, self.lockfile_path
        )

    def resolve(self, text: str) -> SkillEntry | None:
        """Match exact ``<ns>:<name>`` or bare ``<name>`` (local wins ties; fail closed)."""
        self._ensure_loaded()
        assert self._entries is not None
        query = text.strip()
        if not query:
            return None
        if ":" in query:
            return self._entries.get(query)
        local_entry = self._entries.get(f"{SKILLS_SOURCE}:{query}")
        if local_entry is not None:
            return local_entry
        matches = [entry for entry in self._entries.values() if entry.name == query]
        if len(matches) == 1:
            return matches[0]
        return None

    def ambiguous_matches(self, name: str) -> list[SkillEntry]:
        """Return competing marketplace entries when a bare skill name is ambiguous."""
        self._ensure_loaded()
        assert self._entries is not None
        query = name.strip()
        if not query or ":" in query or f"{SKILLS_SOURCE}:{query}" in self._entries:
            return []
        matches = sorted(
            (entry for entry in self._entries.values() if entry.name == query),
            key=lambda entry: entry.namespaced,
        )
        return matches if len(matches) > 1 else []

    def list_entries(self) -> list[SkillEntry]:
        """All entries sorted stably by bare skill name, local first per collision."""
        self._ensure_loaded()
        assert self._entries is not None
        return sorted(
            self._entries.values(),
            key=lambda entry: (entry.name, entry.source != SKILLS_SOURCE, entry.source),
        )

    @property
    def warnings(self) -> list[str]:
        """Builtin-collision shadow warnings plus lockfile tamper/drift warnings."""
        entries = self.list_entries()
        shadow_warnings = [
            f"Skill {entry.name!r} shadowed by builtin '/{entry.name.lower()}'"
            " — rename the skill to invoke it."
            for entry in entries
            if entry.shadowed
        ]
        return shadow_warnings + list(self._drift_warnings)

    def reload(self) -> int:
        """Drop the cache and rescan local + verified marketplace skills."""
        self._entries = None
        self._drift_warnings = []
        self._ensure_loaded()
        assert self._entries is not None
        return len(self._entries)

    def remove(self, name: str) -> bool:
        """Delete one local or marketplace skill; evict it from the index on success."""
        query = name.strip()
        entry = self.resolve(query)
        if entry is None:
            if ":" in query and not query.startswith(f"{SKILLS_SOURCE}:"):
                outcome = remove_installed_skill(
                    query,
                    marketplaces_dir=self.marketplaces_dir,
                    lockfile_path=self.lockfile_path,
                )
                if outcome.removed:
                    self._entries = None
                    return True
            return False
        if entry.source == SKILLS_SOURCE:
            if not remove_skill(self.skills_dir, entry.name):
                return False
        else:
            outcome = remove_installed_skill(
                entry.namespaced,
                marketplaces_dir=self.marketplaces_dir,
                lockfile_path=self.lockfile_path,
            )
            if not outcome.removed:
                return False
        assert self._entries is not None
        self._entries.pop(entry.namespaced, None)
        return True


def remove_skill(skills_dir: str | Path, name: str) -> bool:
    """Delete one local skill dir; guarded against traversal and outside roots."""
    root = Path(skills_dir)
    try:
        refuse_symlink(root, "skills dir", max_ancestors=1)
    except ValueError:
        return False
    candidate = root / name
    if candidate.is_symlink():
        return False
    try:
        resolved = candidate.resolve()
        root_resolved = root.resolve()
    except OSError:
        return False
    if resolved.parent != root_resolved or resolved.name != name:
        return False
    if not resolved.is_dir():
        return False
    try:
        shutil.rmtree(resolved)
    except OSError:
        return False
    return not resolved.exists()
