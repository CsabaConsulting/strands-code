"""Leading-slash dispatch and launch resume picker (D-02/D-03)."""

from __future__ import annotations

from pathlib import Path

import typer

from strands_code_agent.code_agent import DEFAULT_CODE_AGENT_CALLBACK_HANDLER
from strands_code_cli.session_index import SessionIndex

USAGE_HINT = "Available commands: /resume, /rename <title>, /exit"

_PICKER_LIMIT = 10


def dispatch(text: str, *, session_id: str, index: SessionIndex) -> tuple[str, str | None]:
    """Route one REPL line: slash commands handled, anything else is an agent turn.

    Args:
        text: Raw input line.
        session_id: Active session id (the rename target).
        index: Sidecar title index backing /resume and /rename.

    Returns:
        ``(action, message)`` where action is ``"agent"`` (caller runs the
        model turn), ``"exit"`` (caller leaves the loop), or ``"reply"``
        (caller shows message, never an agent turn).
    """
    stripped = text.strip()
    if not stripped.startswith("/"):
        return ("agent", None)
    head, _, arg = stripped.partition(" ")
    cmd = head.lower()
    rest = arg.strip()
    if cmd == "/exit":
        return ("exit", None)
    if cmd == "/resume":
        return ("reply", _resume_message(index, rest))
    if cmd == "/rename":
        return ("reply", _rename_message(index, session_id, rest))
    return ("reply", f"Unknown command {head!r}. {USAGE_HINT}")


def _resume_message(index: SessionIndex, rest: str) -> str:
    """Render /resume output: one session hint, or the recent list."""
    if rest:
        for entry in index.list_recent():
            if entry["id"] == rest:
                title = entry.get("title", "untitled")
                return f"To resume '{title}', exit and relaunch with --session-id {entry['id']}."
        return f"Unknown session id {rest!r}. {USAGE_HINT}"
    entries = index.list_recent(limit=_PICKER_LIMIT)
    if not entries:
        return "No previous sessions yet."
    lines = ["Recent sessions:"]
    for entry in entries:
        lines.append(f"  {entry['id'][:8]}  {entry.get('title', 'untitled')}")
    lines.append("Relaunch with --session-id <id> to resume.")
    return "\n".join(lines)


def _rename_message(index: SessionIndex, session_id: str, rest: str) -> str:
    """Apply /rename through index validation; failures stay REPL replies."""
    if not rest:
        return "Usage: /rename <new title>"
    try:
        entry = index.rename(session_id, rest)
    except (ValueError, KeyError) as exc:
        return f"Cannot rename: {exc}"
    return f"Session renamed to '{entry['title']}'."


def show_picker(index: SessionIndex, *, session_dir: str | Path | None = None) -> str | None:
    """Numbered resume picker over recent sessions plus start-new (D-02).

    Args:
        index: Sidecar title index (recency order).
        session_dir: When given, entries without a snapshot prefix on disk
            are treated as untrusted orphans and hidden (T-02-02).

    Returns:
        The chosen session id, or None for start-new, empty list, or an
        aborted prompt.
    """
    entries = index.list_recent(limit=_PICKER_LIMIT)
    if session_dir is not None:
        entries = [e for e in entries if _has_snapshot(session_dir, e["id"])]
    if not entries:
        return None
    console = DEFAULT_CODE_AGENT_CALLBACK_HANDLER.console
    console.print("Recent sessions:")
    for pos, entry in enumerate(entries, 1):
        console.print(f"  {pos}. {entry.get('title', 'untitled')} [{entry['id'][:8]}]")
    console.print(f"  {len(entries) + 1}. Start new session")
    while True:
        try:
            choice = typer.prompt("Select session", type=int, default=len(entries) + 1)
        except (typer.Abort, EOFError):
            return None
        if 1 <= choice <= len(entries):
            return entries[choice - 1]["id"]
        if choice == len(entries) + 1:
            return None
        console.print(f"Enter a number 1-{len(entries) + 1}.")


def _has_snapshot(session_dir: str | Path, session_id: str) -> bool:
    """True when a snapshot prefix exists for the id under the session dir."""
    try:
        return (Path(session_dir) / "session" / session_id).is_dir()
    except OSError:
        return False
