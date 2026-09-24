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

from strands_code_cli.router import dispatch
from strands_code_cli.session_index import SessionIndex

logger = logging.getLogger(__name__)
console = Console()

TITLE_PROMPT = "Summarize this exchange in at most six words, plain words only: "
TITLE_WORDS = 6
TITLE_FALLBACK_WORDS = 8
TITLE_FALLBACK_CHARS = 60


def _history() -> History:
    """Reply history backed by a file; in-memory when the cache dir is unusable.

    History holds typed asks (T-01-03): the cache dir and file get the same
    0o700 treatment as the session/index dirs.
    """
    import os

    try:
        import platformdirs

        cache = Path(platformdirs.user_cache_dir("strands-code"))
        cache.mkdir(parents=True, exist_ok=True)
        os.chmod(cache, 0o700)
        history_file = cache / "repl_history"
        history_file.touch(exist_ok=True)
        os.chmod(history_file, 0o600)
        return FileHistory(str(history_file))
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


def _fallback_title(first_text: str) -> str:
    """First-ask truncation used when the model title call fails."""
    clipped = " ".join(first_text.split()[:TITLE_FALLBACK_WORDS])
    return clipped[:TITLE_FALLBACK_CHARS].strip() or "untitled"


def _maybe_auto_title(agent: Any, session_id: str, index: SessionIndex, first_text: str) -> None:
    """Title once from the first exchange (D-04); a manual rename always wins.

    A cheap direct model call is attempted first; any failure falls back to
    first-ask truncation. ``update_title`` no-ops on user-renamed sessions.
    """
    title = _fallback_title(first_text)
    try:
        generate = getattr(getattr(agent, "model", None), "generate", None)
        if generate is None:
            raise AttributeError("agent exposes no direct model call")
        raw = generate(f"{TITLE_PROMPT}{first_text[:500]}")
        candidate = raw if isinstance(raw, str) else getattr(raw, "text", "") or ""
        words = candidate.split()
        if words:
            title = " ".join(words[:TITLE_WORDS])
    except Exception:
        pass  # fallback title stands
    title = title.replace("/", "-").replace("\\", "-")
    try:
        index.update_title(session_id, title)
    except (KeyError, ValueError) as exc:
        logger.warning("Auto-title skipped for session %s: %s", session_id, exc)


def run_loop(agent: Any, *, session_id: str, index: SessionIndex) -> None:
    """Run the REPL until Ctrl-D or /exit.

    One ``PromptSession`` owns input; slash lines dispatch through the
    router while plain text runs synchronously with the prompt suspended
    via ``patch_stdout``. Ctrl-C cancels the line, Ctrl-D exits cleanly
    with an explicit save plus an index recency bump.
    """
    console.print(f"[dim]Session {session_id} — Ctrl-D to exit.[/dim]")
    session: PromptSession = PromptSession(history=_history())
    titled = False
    while True:
        try:
            text = session.prompt("> ")
        except KeyboardInterrupt:
            continue  # Ctrl-C cancels the line
        except EOFError:
            break  # Ctrl-D exits
        if not text.strip():
            continue  # empty input submits nothing; re-prompt
        action, message = dispatch(text, session_id=session_id, index=index)
        if action == "exit":
            break
        if action == "reply":
            if message:
                console.print(message)
            continue
        try:
            with patch_stdout():
                agent(text)
        except KeyboardInterrupt:
            console.print("[yellow]Turn interrupted; earlier turns are saved.[/yellow]")
        if not titled:
            titled = True
            _maybe_auto_title(agent, session_id, index, text)
    explicit_save(agent)
    index.ensure(session_id)
    console.print("[dim]Session saved.[/dim]")
