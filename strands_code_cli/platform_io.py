"""Shared atomic file persistence, symlink refusal & directory helpers (D-06).

Dependency-free stdlib leaf imported across config, policy, routing, memory,
cost, session, loop, entry, and sandbox modules.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

_REFUSED_ROOTS: frozenset[Path] = frozenset(
    Path(p)
    for p in (
        "/",
        "/usr",
        "/bin",
        "/sbin",
        "/lib",
        "/lib64",
        "/etc",
        "/tmp",
        "/var",
        "/dev",
        "/proc",
        "/sys",
    )
)


def _read_process_umask() -> int:
    """Read current process umask thread-safely without mutating global state."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("Umask:"):
                return int(line.split(":", 1)[1].strip(), 8)
    except (OSError, ValueError):
        pass
    return 0o022


def refuse_symlink(
    path: Path | str, label: str = "path", *, max_ancestors: int = 1
) -> None:
    """Raise ``ValueError`` when ``path`` or up to ``max_ancestors`` parents is a symlink."""
    cur = Path(path)
    for step in range(max_ancestors + 1):
        if step > 0 and (cur == cur.parent or cur in _REFUSED_ROOTS):
            break
        if cur.is_symlink():
            if step == 0:
                raise ValueError(f"Refusing symlink {label}: {cur}")
            raise ValueError(f"Refusing symlink parent for {label}: {cur}")
        cur = cur.parent


def refuse_symlink_under_roots(
    path: Path | str,
    roots: Iterable[Path | str],
    label: str = "path",
) -> None:
    """Refuse symlinks on ``path`` and every ancestor down from matching ``roots``."""
    target = Path(path)
    if target.is_symlink():
        raise ValueError(f"Refusing symlink {label}: {target}")
    stop: set[Path] = set()
    for root in roots:
        rpath = Path(root)
        stop.add(rpath)
        try:
            stop.add(Path(os.path.realpath(rpath)))
        except OSError:
            pass
    cur = target.parent
    checked_parent = False
    while cur != cur.parent:
        if cur in stop:
            break
        if cur.is_symlink():
            raise ValueError(f"Refusing symlink parent for {label}: {cur}")
        checked_parent = True
        if cur in _REFUSED_ROOTS:
            break
        cur = cur.parent
    if not checked_parent:
        refuse_symlink(target, label, max_ancestors=1)


def ensure_private_dir(
    path: Path | str,
    label: str = "directory",
    *,
    mode: int = 0o700,
    max_ancestors: int = 1,
) -> Path:
    """Refuse symlinks on target and ancestors, create directory, and apply ``mode``."""
    target = Path(path)
    refuse_symlink(target, label, max_ancestors=max_ancestors)
    target.mkdir(parents=True, exist_ok=True)
    os.chmod(target, mode)
    return Path(os.path.realpath(target))


def atomic_write_text(
    path: Path | str,
    content: str,
    *,
    mode: int | None = 0o600,
    dir_mode: int | None = 0o700,
    refuse_ancestors: int = 1,
    label: str | None = None,
) -> Path:
    """Atomically write UTF-8 text via ``mkstemp`` in ``path.parent`` + ``os.replace``.

    Private state files keep ``mode=0o600`` and ``dir_mode=0o700``; git-tracked
    repo files pass ``mode=None`` to apply process umask-masked standard readable
    permissions (``0o664 & ~umask``, never world-writable even under ``umask 0o000``)
    without mutating global ``os.umask()``.
    """
    target = Path(path)
    refuse_symlink(
        target,
        label if label is not None else target.name,
        max_ancestors=refuse_ancestors,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if dir_mode is not None:
        os.chmod(target.parent, dir_mode)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    tmp_path = Path(tmp_name)
    file_mode = mode if mode is not None else (0o664 & ~_read_process_umask())
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chmod(tmp_path, file_mode)
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return target
