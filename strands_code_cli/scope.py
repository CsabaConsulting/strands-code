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


def confine(path: str | Path, cwd: str | Path) -> Path:
    """Admit only ``cwd`` + subdirs and ``/tmp`` + subdirs.

    Symlinks are resolved (``realpath``) so a link inside scope pointing
    outside is refused, as are ``..`` escapes and sibling directories.

    Raises:
        ValueError: Naming the allowed roots when the path is out of scope.
    """
    roots = (Path(cwd), Path("/tmp"))
    # realpath resolves symlinks even when the leaf does not exist yet.
    canonical = Path(os.path.realpath(resolve(path, cwd)))
    for root in roots:
        real_root = Path(os.path.realpath(root))
        if canonical == real_root or real_root in canonical.parents:
            return canonical
    allowed = ", ".join(str(r) for r in roots)
    raise ValueError(f"Path {canonical} is outside the allowed roots: {allowed}")


class ScopeGuard:
    """Constructor-kwarg holder for a REPL cwd (repo convention: no env sniffing)."""

    def __init__(self, cwd: str | Path) -> None:
        self.cwd = Path(cwd)

    def resolve(self, path: str | Path) -> Path:
        """Resolve ``path`` against this guard's cwd."""
        return resolve(path, self.cwd)

    def confine(self, path: str | Path) -> Path:
        """Resolve then confine ``path`` to this guard's scope."""
        return confine(path, self.cwd)
