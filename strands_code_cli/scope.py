"""Default filesystem scope for file tools: cwd + subdirs + /tmp (D-07).

The harness builtins (``read``/``write``/``edit``) only require absolute
paths without ``..`` segments — they do not confine writes to the working
directory. This module adds that confinement in app code so a cwd-centric
REPL cannot touch sibling repos.

Shell commands pass through unscoped (D-06 full shell); shell redirection
(``echo > file``, ``sed -i``) and ``python_repl`` ``open()`` calls bypass
both this guard and the :mod:`strands_code_cli.diff_gate` review gate.
That bypass is a documented advisory — airtight mediation of every tool
is Phase 3 (TOOL-03) work, not closed here.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable


def resolve(path: str | Path, cwd: str | Path) -> Path:
    """Map a REPL-supplied path to an absolute path against the REPL cwd.

    Relative paths resolve against ``cwd``; absolute paths pass through.
    ``~`` is expanded. Call this BEFORE the harness absolute-path check
    so cwd-centric input stops erroring.
    """
    text = os.path.expanduser(str(path))
    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = Path(cwd) / candidate
    return candidate


def confine(path: str | Path, cwd: str | Path, extra_roots: Iterable[str | Path] = ()) -> Path:
    """Admit ``cwd`` + subdirs, ``/tmp`` + subdirs, plus policy-granted roots.

    Symlinks are resolved (``realpath``) so a link inside scope pointing
    outside is refused, as are ``..`` escapes and sibling directories.
    Policy match runs BEFORE confinement (risk 6): pass
    ``effective_roots(cwd, policy)`` extras so an allow rule for an
    outside path grants roots the confiner then admits.

    Raises:
        ValueError: Naming the allowed roots when the path is out of scope.
    """
    roots = (Path(cwd), Path("/tmp"), *(Path(r) for r in extra_roots))
    # realpath resolves symlinks even when the leaf does not exist yet.
    canonical = Path(os.path.realpath(resolve(path, cwd)))
    for root in roots:
        real_root = Path(os.path.realpath(root))
        if canonical == real_root or real_root in canonical.parents:
            return canonical
    allowed = ", ".join(str(r) for r in roots)
    raise ValueError(f"Path {canonical} is outside the allowed roots: {allowed}")


def _rule_base_dir(pattern: str) -> Path | None:
    """Base dir of an absolute path-glob: text before the first glob char."""
    if not Path(pattern).is_absolute():
        return None
    cut = len(pattern)
    for char in ("*", "?", "["):
        pos = pattern.find(char)
        if pos != -1:
            cut = min(cut, pos)
    head = pattern[:cut]
    if not head or head.endswith("/"):
        base = Path(head or "/")
    else:
        base = Path(head).parent
    return base


def effective_roots(cwd: str | Path, policy: Any) -> list[Path]:
    """Union of default roots plus realpaths of absolute allow-rule bases.

    Takes the policy object duck-typed (``.allow`` rules with ``.path``)
    so this module never imports the policy store.
    """
    roots = [Path(cwd), Path("/tmp")]
    for rule in getattr(policy, "allow", []) or []:
        pattern = getattr(rule, "path", None)
        if not pattern:
            continue
        base = _rule_base_dir(pattern)
        if base is None:
            continue
        try:
            real = Path(os.path.realpath(base))
        except OSError:
            continue
        if real not in roots:
            roots.append(real)
    return roots


class ScopeGuard:
    """Constructor-kwarg holder for a REPL cwd (repo convention: no env sniffing)."""

    def __init__(self, cwd: str | Path) -> None:
        self.cwd = Path(cwd)

    def resolve(self, path: str | Path) -> Path:
        """Resolve ``path`` against this guard's cwd."""
        return resolve(path, self.cwd)

    def confine(self, path: str | Path, extra_roots: Iterable[str | Path] = ()) -> Path:
        """Resolve then confine ``path`` to this guard's scope plus extras."""
        return confine(path, self.cwd, extra_roots)
