"""Shared UI console, render lock, and untrusted display sanitization (D-07).

Dependency-free leaf module imported across loop, policy, dispatch, memory,
and sandbox modules.
"""

from __future__ import annotations

import re
import threading

from rich.console import Console

console = Console()
stderr_console = Console(stderr=True)
RENDER_LOCK = threading.RLock()

_ANSI_OSC_RE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_ANSI_ESC_RE = re.compile(r"\x1b[@-Z\\-_]")


def _strip_controls(value: object, *, collapse_ws: bool) -> str:
    text = str(value) if value is not None else ""
    text = _ANSI_OSC_RE.sub("", text)
    text = _ANSI_CSI_RE.sub("", text)
    text = _ANSI_ESC_RE.sub("", text)
    cleaned_chars: list[str] = []
    for ch in text:
        code = ord(ch)
        if ch == "\t":
            cleaned_chars.append(" " if collapse_ws else "    ")
        elif ch in ("\r", "\n"):
            cleaned_chars.append(" ")
        elif code >= 32 and not (127 <= code <= 159):
            cleaned_chars.append(ch)
    joined = "".join(cleaned_chars)
    return " ".join(joined.split()) if collapse_ws else joined


def sanitize_display(value: object, max_len: int = 240) -> str:
    """Strip ANSI CSI/OSC & control chars, collapse whitespace, keep Rich brackets literal."""
    collapsed = _strip_controls(value, collapse_ws=True)
    if len(collapsed) > max_len:
        return (
            collapsed[: max_len - 3].rstrip() + "..."
            if max_len > 3
            else collapsed[:max_len]
        )
    return collapsed


def sanitize_line(value: object, max_len: int | None = None) -> str:
    """Strip ANSI CSI/OSC & control chars on one line while preserving indentation."""
    cleaned = _strip_controls(value, collapse_ws=False)
    if max_len is not None and len(cleaned) > max_len:
        return (
            cleaned[: max_len - 3].rstrip() + "..."
            if max_len > 3
            else cleaned[:max_len]
        )
    return cleaned
