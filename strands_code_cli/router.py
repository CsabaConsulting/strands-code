"""Leading-slash dispatch and launch resume picker (D-02/D-03)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import typer

from strands_code_agent.code_agent import DEFAULT_CODE_AGENT_CALLBACK_HANDLER
from strands_code_agent.search_tool import format_hits, run_search
from strands_code_cli.diff_config import MODES, DiffConfig
from strands_code_cli.diff_gate import apply_stashed, store_for
from strands_code_cli.mode import APPROVE_EMPTY, APPROVE_EXECUTE, APPROVE_OK, MODE_USAGE, ModeState
from strands_code_cli.session_index import SessionIndex

USAGE_HINT = (
    "Available commands: /resume, /rename <title>, "
    "/diff [approve-each|on-demand|auto|show|apply [path]|discard [path]], "
    "/search <pattern>, /policy [show|last], /mode [plan|act], /approve, /exit"
)

_DIFF_USAGE = "Usage: /diff [approve-each|on-demand|auto|show|apply [path]|discard [path]]"
_SEARCH_USAGE = "Usage: /search <pattern> [--glob <glob>] [--limit <n>]"
_POLICY_USAGE = "Usage: /policy [show|last]"
_MODE_USAGE = MODE_USAGE

_PICKER_LIMIT = 10


def dispatch(
    text: str,
    *,
    session_id: str,
    index: SessionIndex,
    cwd: str | Path | None = None,
    diff_config_path: str | Path | None = None,
    mode: ModeState | None = None,
) -> tuple[str, str | None]:
    """Route one REPL line: slash commands handled, anything else is an agent turn.

    Args:
        text: Raw input line.
        session_id: Active session id (the rename target).
        index: Sidecar title index backing /resume and /rename.
        cwd: Working directory for /search and scope checks (default: process cwd).
        diff_config_path: Override for the persisted diff mode (tests only).
        mode: Session-sticky mode holder (None → Act default, keeps
            standalone/test behaviour without a loop-owned holder).

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
    if cmd == "/diff":
        return ("reply", _diff_message(session_id, rest, diff_config_path))
    if cmd == "/search":
        return ("reply", _search_message(rest, cwd if cwd is not None else os.getcwd()))
    if cmd == "/policy":
        return ("reply", _policy_message(rest))
    if cmd == "/mode":
        return ("reply", _mode_message(rest, mode))
    if cmd == "/approve":
        return _approve_message(mode)
    return ("reply", f"Unknown command {head!r}. {USAGE_HINT}")


def _mode_holder(mode: ModeState | None) -> ModeState:
    """Loop-owned holder when present, else a throwaway Act default."""
    return mode if mode is not None else ModeState()


def _mode_message(rest: str, mode: ModeState | None) -> str:
    """Handle /mode: report, switch with announcement, or usage — replies only.

    No agent turn ever leaves this branch; approval prompts never live
    here (established reply-only pattern).
    """
    holder = _mode_holder(mode)
    verb = rest.strip().lower()
    if not verb:
        return holder.announce()
    if verb in ("plan", "act"):
        return holder.set(verb)
    return _MODE_USAGE


def _approve_message(mode: ModeState | None) -> tuple:
    """Handle /approve: explicit plan handoff gated on a pending plan.

    Empty cases stay replies. On success the session flips to act and
    the caller runs an agent turn carrying the execute prompt — the
    plan text lives in session history, so approval must *run*, not
    just announce (a reply-only /approve flips the mode and drops the
    plan). Approval prompts themselves never live here.
    """
    if mode is None:
        return ("reply", APPROVE_EMPTY)
    if not mode.pending_plan:
        return ("reply", APPROVE_EMPTY)
    mode.approve()
    return ("agent", f"{APPROVE_OK}\n{APPROVE_EXECUTE}")


def _diff_message(session_id: str, rest: str, config_path: str | Path | None) -> str:
    """Handle /diff: mode switch, status show, pending apply/discard — replies only.

    Approval prompts never live here (they would race the prompt); per-hunk
    approval happens inside the turn via the gate's ask callable.
    """
    config = DiffConfig.load(config_path)
    store = store_for(session_id)
    pending = store.list() if store is not None else {}
    if not rest or rest == "show":
        lines = [f"Diff mode: {config.mode} ({len(pending)} pending)."]
        for path in sorted(pending):
            lines.append(f"  {pending[path].get('op', 'edit')}: {path}")
        return "\n".join(lines)
    verb, _, arg = rest.partition(" ")
    verb = verb.lower()
    if verb in MODES:
        config.mode = verb
        config.save(config_path)
        return f"Diff mode set to {verb}."
    if verb == "apply":
        if store is None:
            return "No pending-change store for this session."
        target = arg.strip() or None
        return asyncio.run(apply_stashed(store, target))
    if verb == "discard":
        if store is None:
            return "No pending-change store for this session."
        target = arg.strip()
        if target:
            entry = store.pop(target)
            return f"Discarded pending change to {target}." if entry else f"No pending change to {target}."
        count = len(pending)
        store.clear()
        return f"Discarded {count} pending change(s)."
    return f"Unknown /diff mode {verb!r}. {_DIFF_USAGE}"


def _policy_message(rest: str) -> str:
    """Handle /policy: inspect-only replies (show rules, last covered).

    Approval prompts never live here (they would race the prompt); this
    only reports the effective policy and the gate's covered-action log.
    """
    from strands_code_cli.policy import PolicyConfig
    from strands_code_cli.policy_gate import last_covered

    verb = rest.strip().lower()
    if verb in ("", "show"):
        try:
            config = PolicyConfig.load()
        except ValueError as exc:
            return f"Policy config error: {exc}"
        lines = ["Effective policy (deny-wins across home + repo union):"]
        lines.append("Builtins: allow read, search; allow GET-shaped fetch, git fetch.")
        for rule in config.allow:
            lines.append(f"  allow {rule.describe()}")
        for rule in config.deny:
            lines.append(f"  deny {rule.describe()}")
        if config.options.trust_delegated:
            lines.append("  options: trust_delegated = true")
        return "\n".join(lines)
    if verb == "last":
        covered = last_covered()
        if not covered:
            return "No gated actions this session yet."
        return "Covered actions:\n" + "\n".join(f"  {line}" for line in covered)
    return f"Unknown /policy mode {verb!r}. {_POLICY_USAGE}"


def _search_message(rest: str, cwd: str | Path) -> str:
    """Run the search tool synchronously; never triggers a model turn."""
    pattern, file_glob, limit = _parse_search_args(rest)
    if not pattern:
        return _SEARCH_USAGE
    try:
        output = run_search(pattern, file_glob=file_glob, limit=limit, cwd=cwd)
    except ValueError as exc:
        return f"Cannot search: {exc}"
    return format_hits(pattern, output)


def _parse_search_args(rest: str) -> tuple[str, str | None, int]:
    """Split ``/search <pattern> [--glob <glob>] [--limit <n>]`` args."""
    tokens = rest.split()
    pattern_parts: list[str] = []
    file_glob: str | None = None
    limit = 50
    pos = 0
    while pos < len(tokens):
        token = tokens[pos]
        if token == "--glob" and pos + 1 < len(tokens):
            file_glob = tokens[pos + 1]
            pos += 2
        elif token == "--limit" and pos + 1 < len(tokens):
            try:
                limit = max(1, int(tokens[pos + 1]))
            except ValueError:
                pass
            pos += 2
        else:
            pattern_parts.append(token)
            pos += 1
    return (" ".join(pattern_parts), file_glob, limit)


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
    if sys.stdin.isatty():
        # Arrow-key dialog (choice.radio_choice): same SIGINT-safe prompt
        # as the approval gate. ESC/failure means start-new (None);
        # Ctrl-C re-raises so startup cancel still works.
        from strands_code_cli.choice import radio_choice

        picked = radio_choice(
            "Recent sessions",
            [(e["id"], f"{e.get('title', 'untitled')} [{e['id'][:8]}]") for e in entries]
            + [(None, "Start new session")],
            default=len(entries),
        )
        return picked if isinstance(picked, str) else None
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
