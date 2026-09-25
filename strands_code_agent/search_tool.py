"""Agent-side lexical search: thin ripgrep wrapper with stdlib fallback (TOOL-04).

No persistent index is maintained (D-09): every call greps the live tree.
Symbol navigation is on-the-fly ``rg`` for ``def``/``class`` lines plus
plain-text reference matches — lexical only, no embeddings.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from strands import tool

from strands_code_cli.scope import confine

_RG_TIMEOUT_SECONDS = 30
_DEFAULT_LIMIT = 50


def run_search(
    pattern: str,
    path: str | Path | None = None,
    file_glob: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    cwd: str | Path | None = None,
) -> str:
    """Grep ``pattern`` under ``path`` (default cwd), one ``path:line:match`` per hit.

    Uses ``rg --line-number --no-heading`` via an argv list (the pattern is
    a single argv element, never shell-interpolated); falls back to
    ``os.walk`` + ``re`` when the ripgrep binary is absent. Output is capped
    at ``limit`` lines with a truncation note.
    """
    if not pattern or not pattern.strip():
        raise ValueError("search pattern must be non-empty")
    if limit <= 0:
        raise ValueError("search limit must be positive")
    base = Path(cwd) if cwd is not None else Path(os.getcwd())
    target = confine(path, base) if path is not None else confine(base, base)
    if shutil.which("rg") is not None:
        return _rg_search(pattern, target, file_glob, limit)
    return _fallback_search(pattern, target, file_glob, limit)


def _rg_search(pattern: str, target: Path, file_glob: str | None, limit: int) -> str:
    """Run ripgrep as a subprocess with the pattern as one argv element."""
    argv = ["rg", "--line-number", "--no-heading", "--color", "never", pattern, str(target)]
    if file_glob:
        argv.extend(["--glob", file_glob])
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=_RG_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return "search timed out."
    if proc.returncode == 1:
        return "No matches found."
    if proc.returncode != 0:
        return _fallback_search(pattern, target, file_glob, limit)
    return _cap(proc.stdout.splitlines(), limit)


def _fallback_search(pattern: str, target: Path, file_glob: str | None, limit: int) -> str:
    """Stdlib grep used when ``rg`` is missing (or errors): walk + regex."""
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"invalid search pattern: {exc}") from exc
    import fnmatch

    roots = [target] if target.is_file() else [p for p in target.rglob("*") if p.is_file()] if target.is_dir() else []
    hits: list[str] = []
    for candidate in sorted(roots):
        if file_glob and not fnmatch.fnmatch(candidate.name, file_glob):
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="strict")
        except (OSError, ValueError, UnicodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                hits.append(f"{candidate}:{lineno}:{line.strip()}")
    if not hits:
        return "No matches found."
    return _cap(hits, limit)


def _cap(lines: list[str], limit: int) -> str:
    """Cap output at ``limit`` lines, appending a truncation note when cut."""
    lines = [line for line in lines if line.strip()]
    if len(lines) > limit:
        kept = lines[:limit]
        kept.append(f"... truncated to {limit} of {len(lines)} matches.")
        return "\n".join(kept)
    return "\n".join(lines)


def format_hits(pattern: str, output: str) -> str:
    """Render a ``/search`` reply: header plus ``path:line`` hit lines."""
    if output in ("No matches found.", "search timed out."):
        return f"Search for {pattern!r}: {output}"
    return f"Search for {pattern!r}:\n{output}"


@tool
def search(pattern: str, path: str | None = None, file_glob: str | None = None, limit: int = _DEFAULT_LIMIT) -> str:
    """
    Lexical code search over the repo (ripgrep, stdlib fallback, no index).

    Args:
        pattern: Regex to search for (required, non-empty).
        path: File or directory to search under (default: working directory).
        file_glob: Optional glob limiting filenames (e.g. "*.py").
        limit: Maximum hits returned (default 50).
    """
    return run_search(pattern, path=path, file_glob=file_glob, limit=limit)
