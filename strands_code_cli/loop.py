"""Minimal REPL loop: prompt, synchronous agent turn, clean exit."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory, History
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console

from strands_code_cli.session_index import SessionIndex

logger = logging.getLogger(__name__)
console = Console()


def _history() -> History:
    """Reply history backed by a file; in-memory when the cache dir is unusable."""
    try:
        import platformdirs

        cache = Path(platformdirs.user_cache_dir("strands-code"))
        cache.mkdir(parents=True, exist_ok=True)
        return FileHistory(str(cache / "repl_history"))
    except Exception as exc:  # best-effort history must never block the loop
        logger.warning("Falling back to in-memory REPL history: %s", exc)
        return History()


def explicit_save(agent: Any) -> None:
    """Overwrite ``snapshot_latest`` so a clean exit loses nothing.

    Per-message saves already cover kill-safety; this adds determinism on
    the exit path. Failures are logged, never raised.
    """
    manager = getattr(agent, "_session_manager", None)
    save = getattr(manager, "save_snapshot", None)
    if save is None:
        return
    try:
        asyncio.run(save(agent, is_latest=True))
    except Exception as exc:
        logger.warning("Explicit session save on exit failed: %s", exc)


def run_loop(agent: Any, *, session_id: str, index: SessionIndex) -> None:
    """Run the REPL until Ctrl-D.

    One ``PromptSession`` owns input; each turn runs synchronously with the
    prompt suspended via ``patch_stdout`` while the agent streams through
    the shared callback handler. Ctrl-C cancels the line, Ctrl-D exits
    cleanly with an explicit save plus an index recency bump.
    """
    console.print(f"[dim]Session {session_id} — Ctrl-D to exit.[/dim]")
    session: PromptSession = PromptSession(history=_history())
    while True:
        try:
            text = session.prompt("> ")
        except KeyboardInterrupt:
            continue  # Ctrl-C cancels the line
        except EOFError:
            break  # Ctrl-D exits
        if not text.strip():
            continue  # empty input submits nothing; re-prompt
        try:
            with patch_stdout():
                agent(text)
        except KeyboardInterrupt:
            console.print("[yellow]Turn interrupted; earlier turns are saved.[/yellow]")
            continue
    explicit_save(agent)
    index.ensure(session_id)
    console.print("[dim]Session saved.[/dim]")
