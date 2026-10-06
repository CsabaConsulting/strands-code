"""Local skill index over ./.agent/skills (SKILL-01, D-02/D-03).

Skills load through the SDK ``Skill.from_directory`` seam (never a hand
parser); this module adds the CLI-owned layer: the ``local:`` namespace
map, builtin-collision shadow warnings, and exact-match resolution.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from strands.vended_plugins.skills import Skill

SKILLS_SOURCE = "local"
"""Single namespace source for MVP; marketplace prefixes arrive with SKILL-03."""

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
    }
)
"""Builtin slash heads (no leading slash) that always win collisions (D-02).

Mirrors the ``dispatch`` branches.
"""


@dataclass
class SkillEntry:
    """One loaded local skill: SDK record plus CLI namespace state.

    Args:
        name: Bare skill name (colon-free, per the SDK name regex).
        source: Namespace source, always ``"local"`` for MVP.
        namespaced: ``source:name`` form; derived when left empty.
        description: One-line skill description from SKILL.md frontmatter.
        path: Skill directory on disk (None when not loaded from disk).
        shadowed: True when the bare name collides with a builtin head.
        instructions: Full markdown skill body (untrusted repo content).
        allowed_tools: Frontmatter tool list; informational only, never enforced.
    """

    name: str
    source: str = SKILLS_SOURCE
    namespaced: str = ""
    description: str = ""
    path: Path | None = None
    shadowed: bool = False
    instructions: str = ""
    allowed_tools: list[str] | None = field(default=None)

    def __post_init__(self) -> None:
        if not self.namespaced:
            self.namespaced = f"{self.source}:{self.name}"


class SkillIndex:
    """Load-once index of local skills under a skills dir.

    Fail-soft on read: a missing skills dir loads as empty, malformed
    skills warn-and-skip inside the SDK loader. Fail-loud on tamper:
    a symlinked skills root raises ``ValueError`` (T-03-02 precedent).

    Args:
        skills_dir: Directory holding one subdirectory per skill.
    """

    def __init__(self, skills_dir: str | Path = Path("./.agent/skills")) -> None:
        raw = Path(skills_dir)
        if raw.is_symlink():
            raise ValueError(f"Skills dir must not be a symlink: {raw}")
        self.skills_dir = raw
        self._entries: dict[str, SkillEntry] | None = None

    def _ensure_loaded(self) -> None:
        if self._entries is not None:
            return
        self._entries = {}
        if not self.skills_dir.exists():
            return
        try:
            loaded = Skill.from_directory(self.skills_dir)
        except FileNotFoundError:
            return  # raced deletion or non-dir root: treat as empty
        for skill in loaded:
            shadowed = skill.name.lower() in BUILTIN_SLASH_HEADS
            self._entries[skill.name] = SkillEntry(
                name=skill.name,
                source=SKILLS_SOURCE,
                namespaced=f"{SKILLS_SOURCE}:{skill.name}",
                description=skill.description or "",
                path=skill.path,
                shadowed=shadowed,
                instructions=skill.instructions or "",
                allowed_tools=list(skill.allowed_tools) if skill.allowed_tools else None,
            )

    def resolve(self, text: str) -> SkillEntry | None:
        """Exact-match a bare or namespaced skill name; never guesses.

        Returns:
            The entry, or None for unknown names (callers fall through
            to the existing Unknown-command reply).
        """
        self._ensure_loaded()
        assert self._entries is not None
        query = text.strip()
        if not query:
            return None
        if query in self._entries:
            return self._entries[query]
        prefix = f"{SKILLS_SOURCE}:"
        if query.startswith(prefix):
            return self._entries.get(query[len(prefix) :])
        return None

    def list_entries(self) -> list[SkillEntry]:
        """All entries sorted by bare skill name (stable across runs)."""
        self._ensure_loaded()
        assert self._entries is not None
        return sorted(self._entries.values(), key=lambda entry: entry.name)

    @property
    def warnings(self) -> list[str]:
        """One shadow warning per builtin-colliding skill (D-02)."""
        return [
            f"Skill {entry.name!r} shadowed by builtin '/{entry.name.lower()}'"
            " — rename the skill to invoke it."
            for entry in self.list_entries()
            if entry.shadowed
        ]

    def reload(self) -> int:
        """Drop the cache and rescan the skills dir; returns live entry count.

        New skill dirs appear without a CLI restart; deleted ones
        drop out. A missing dir reloads as empty (fail-soft, same as
        the first load).
        """
        self._entries = None
        self._ensure_loaded()
        assert self._entries is not None
        return len(self._entries)

    def remove(self, name: str) -> bool:
        """Delete one skill by bare name; evict it from the index on success.

        Returns:
            True when a skill dir was deleted, False when refused
            (unknown name, traversal, symlink, or filesystem trouble).
        """
        entry = self.resolve(name)
        if entry is None:
            return False
        if not remove_skill(self.skills_dir, entry.name):
            return False
        assert self._entries is not None
        self._entries.pop(entry.name, None)
        return True


def remove_skill(skills_dir: str | Path, name: str) -> bool:
    """Delete one skill dir; guarded against traversal and outside roots.

    Mirrors ``_remove_snapshot_dir``: resolve, same-parent check,
    name-equality check, symlinked skill dirs refused. Only plain
    directories directly inside the skills root are ever deleted.

    Returns:
        True when a skill dir was deleted, False otherwise.
    """
    root = Path(skills_dir)
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
