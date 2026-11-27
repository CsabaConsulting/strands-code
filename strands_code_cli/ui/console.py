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

# 7-bit & 8-bit OSC/DCS/SOS/PM/APC string sequences (BEL, ST = ESC \, C1 ST = \x9c, or line/EOF)
_ANSI_STR_SEQ_RE = re.compile(
    r"(?:\x1b[\]PX^_]|[\x90\x98\x9d\x9e\x9f])[^\x07\x1b\x9c\r\n]*(?:\x07|\x1b\\|\x9c|\r|\n|$)"
)
# 7-bit & 8-bit ECMA-48 CSI sequences (parameter bytes 0x30-0x3F = [0-9:;<=>?])
_ANSI_CSI_RE = re.compile(r"(?:\x1b\[|\x9b)[0-9:;<=>?]*[ -/]*[@-~]")
# 3-byte nF charset/private ESC sequences (e.g. ESC ( 0, ESC # 8) and 2-byte ESC Fe/Fp/Fs
_ANSI_ESC_RE = re.compile(r"\x1b(?:[ -/]+[0-~]|[@-Z\\-_])")

_BIDI_CONTROLS = frozenset(
    {
        "\u061c",
        "\u200e",
        "\u200f",
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
    }
)


def _strip_ansi(value: object) -> str:
    text = str(value) if value is not None else ""
    text = _ANSI_STR_SEQ_RE.sub("", text)
    text = _ANSI_CSI_RE.sub("", text)
    return _ANSI_ESC_RE.sub("", text)


def _is_safe_char(ch: str) -> bool:
    code = ord(ch)
    return code >= 32 and not (127 <= code <= 159) and ch not in _BIDI_CONTROLS


def _strip_controls(value: object, *, collapse_ws: bool) -> str:
    text = _strip_ansi(value)
    cleaned_chars: list[str] = []
    for ch in text:
        if ch == "\t":
            cleaned_chars.append(" " if collapse_ws else "    ")
        elif ch in ("\r", "\n"):
            cleaned_chars.append(" ")
        elif _is_safe_char(ch):
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


def sanitize_multiline(value: object, max_len: int | None = None) -> str:
    """Strip ANSI CSI/OSC & unsafe control chars while preserving newlines and tabs."""
    text = _strip_ansi(value)
    cleaned_chars: list[str] = []
    for ch in text:
        if ch in ("\n", "\t") or _is_safe_char(ch):
            cleaned_chars.append(ch)
    cleaned = "".join(cleaned_chars)
    if max_len is not None and len(cleaned) > max_len:
        return (
            cleaned[: max_len - 3].rstrip() + "..."
            if max_len > 3
            else cleaned[:max_len]
        )
    return cleaned
