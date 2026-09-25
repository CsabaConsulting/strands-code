"""Diff gate: wrapper ``write``/``edit`` tools with approve-each/on-demand/auto (TOOL-02).

Mechanism (RESEARCH §4.2 option 2): app-level ``@tool`` functions carrying
the SAME names as the harness builtins, so the builtins must be pinned off
in the ``builtin_tools`` mapping (name-collision rule) and these wrappers
registered instead. Chosen over harness ``interventions`` to avoid building
Phase 3 TOOL-03 machinery early, and over SDK hooks as least precedented.

Each wrapper (a) resolves + confines paths via :mod:`strands_code_cli.scope`,
(b) computes a stdlib ``difflib.unified_diff`` old-vs-new preview, (c)
consults the :class:`DiffConfig` mode — ``approve-each`` prompts per hunk
inside the turn via the ``ask`` callable, ``on-demand`` stashes pending
state as sidecar JSON (``session_index.py`` pattern) for later ``/diff``
review, ``auto`` applies directly — and (d) re-reads before apply so a
stale-preview edit fails loudly (exact-once semantics), never misapplies.

Advisory holes (documented, not closed here): shell redirection
(``echo > file``, ``sed -i``) and ``python_repl`` ``open()`` calls mutate
files without touching these wrappers. Airtight mediation of all tools is
Phase 3 interventions work. Subagent turns inherit this gate through the
harness factory; note ``approve-each`` may prompt noisily inside delegated
turns. Zero Phase 3 policy-file code lives here.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from strands import tool

from strands_code_cli.diff_config import DEFAULT_MODE, MODES, DiffConfig
from strands_code_cli.scope import confine, resolve

_PENDING_NAME = "pending.json"

AskCallable = Callable[[str], bool]
AsyncReader = Callable[[str], Awaitable[str | None]]
AsyncWriter = Callable[[str, str], Awaitable[None]]


# ---------------------------------------------------------------------------
# Diff rendering helpers (shared with the callback handler)
# ---------------------------------------------------------------------------


def unified_diff(old_text: str, new_text: str, path: str) -> str:
    """Compute a unified diff of old vs new file text for ``path``."""
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def split_hunks(diff_text: str) -> list[str]:
    """Split a unified diff into per-hunk chunks (each keeps file headers)."""
    header: list[str] = []
    hunks: list[str] = []
    current: list[str] = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("@@"):
            if current:
                hunks.append("".join(header + current))
            current = [line]
        elif current:
            current.append(line)
        else:
            header.append(line)
    if current:
        hunks.append("".join(header + current))
    return hunks if hunks else ([diff_text] if diff_text else [])


def preview_for_edit(path: str, old_str: str, new_str: str) -> str:
    """Render an ``edit`` preview diff from the old/new snippets alone."""
    old_text = old_str if old_str.endswith("\n") else old_str + "\n"
    new_text = new_str if new_str.endswith("\n") else new_str + "\n"
    return unified_diff(old_text, new_text, path)


# ---------------------------------------------------------------------------
# Pending (on-demand) sidecar state
# ---------------------------------------------------------------------------


class PendingStore:
    """Sidecar-JSON stash of on-demand pending changes (session_index pattern).

    Fail-soft on read (missing/corrupt file loads as empty); fail-loud on
    tamper (symlinked roots or files raise ``ValueError``).

    Args:
        root: Directory holding ``pending.json`` (normally the session dir).
    """

    def __init__(self, root: str | Path) -> None:
        raw = Path(root)
        if raw.is_symlink():
            raise ValueError(f"Pending store root must not be a symlink: {raw}")
        self.root = raw
        self._entries: dict[str, dict[str, Any]] | None = None

    def _path(self) -> Path:
        return self.root / _PENDING_NAME

    def _ensure_loaded(self) -> None:
        if self._entries is not None:
            return
        self._entries = {}
        path = self._path()
        if path.is_symlink():
            raise ValueError(f"Pending store must not be a symlink: {path}")
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self._entries = {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def _save(self) -> None:
        assert self._entries is not None
        path = self._path()
        if path.is_symlink():
            raise ValueError(f"Pending store must not be a symlink: {path}")
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def stash(self, path: str, old_text: str | None, new_text: str, op: str) -> None:
        """Record a pending change for later ``/diff`` review."""
        self._ensure_loaded()
        assert self._entries is not None
        self._entries[path] = {"old_text": old_text, "new_text": new_text, "op": op}
        self._save()

    def list(self) -> dict[str, dict[str, Any]]:
        """Return all pending changes keyed by absolute path."""
        self._ensure_loaded()
        assert self._entries is not None
        return dict(self._entries)

    def pop(self, path: str) -> dict[str, Any] | None:
        """Remove and return one pending change, if present."""
        self._ensure_loaded()
        assert self._entries is not None
        entry = self._entries.pop(path, None)
        self._save()
        return entry

    def clear(self) -> None:
        """Drop all pending changes."""
        self._entries = {}
        self._save()


# ---------------------------------------------------------------------------
# Session binding (so the router can reach the session's store without
# changing the dispatch tri-state signature)
# ---------------------------------------------------------------------------

_bound_stores: dict[str, PendingStore] = {}


def bind_session(session_id: str, store: PendingStore) -> None:
    """Bind a session id to its pending store (wired by the entry path)."""
    _bound_stores[session_id] = store


def store_for(session_id: str) -> PendingStore | None:
    """Return the pending store bound to ``session_id``, if any."""
    return _bound_stores.get(session_id)


# ---------------------------------------------------------------------------
# Filesystem adapters (used by /diff review; in-turn tools use the sandbox)
# ---------------------------------------------------------------------------


async def _fs_read(path: str) -> str | None:
    try:
        return await asyncio.to_thread(Path(path).read_text, encoding="utf-8")
    except FileNotFoundError:
        return None


async def _fs_write(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(target.write_text, content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Core gate logic (async; shared by the tools and /diff review)
# ---------------------------------------------------------------------------


async def _current_text(path: str, reader: AsyncReader | None, tool_context: Any) -> str | None:
    if reader is not None:
        return await reader(path)
    if tool_context is not None:
        try:
            return await tool_context.agent.sandbox.read_text(path)
        except Exception:
            return None
    return await _fs_read(path)


async def _persist_text(path: str, content: str, writer: AsyncWriter | None, tool_context: Any) -> None:
    if writer is not None:
        await writer(path, content)
        return
    if tool_context is not None:
        await tool_context.agent.sandbox.write_text(path, content)
        return
    await _fs_write(path, content)


async def _gate_and_apply(
    *,
    op: str,
    raw_path: str,
    old_text: str | None,
    new_text: str,
    preview: str,
    cwd: str | Path,
    get_mode: Callable[[], str],
    ask: AskCallable | None,
    store: PendingStore | None,
    reader: AsyncReader | None,
    writer: AsyncWriter | None,
    tool_context: Any,
) -> str:
    """Run one gated mutation: scope-check, preview, mode branch, guarded apply."""
    confined = confine(resolve(raw_path, cwd), cwd)
    path = str(confined)
    mode = get_mode()
    if mode not in MODES:
        mode = DEFAULT_MODE
    hunks = split_hunks(preview)
    if mode == "approve-each":
        if ask is None:
            raise ValueError("approve-each mode needs an ask callable")
        for pos, hunk in enumerate(hunks, 1):
            if not ask(f"Apply {op} to {path} (hunk {pos}/{len(hunks)})?\n{hunk}"):
                return f"Discarded {op} to {path}."
        # Fall through to exact-once apply below.
    elif mode == "on-demand":
        if store is None:
            raise ValueError("on-demand mode needs a pending store")
        # Snapshot current content for the later TOCTOU check.
        seen = await _current_text(path, reader, tool_context)
        store.stash(path, seen if seen is not None else old_text, new_text, op)
        return f"Stashed {op} to {path} for /diff review ({len(store.list())} pending)."
    # auto, or approve-each after approval: re-read, then exact-once apply.
    seen = await _current_text(path, reader, tool_context)
    if old_text is not None and seen is not None and seen != old_text:
        raise ValueError(
            f"Refusing {op} to {path}: file changed since preview; re-read and retry."
        )
    await _persist_text(path, new_text, writer, tool_context)
    return f"Applied {op} to {path}."


async def apply_stashed(
    store: PendingStore,
    path: str | None = None,
    *,
    reader: AsyncReader | None = None,
    writer: AsyncWriter | None = None,
) -> str:
    """Apply stashed on-demand changes (``/diff apply [path]``).

    Re-reads each target first: a stale preview fails loudly per file and
    that entry is kept, never partially applied. Each entry is consumed
    (popped) only on success.
    """
    entries = store.list()
    targets = [path] if path is not None else sorted(entries)
    if not targets:
        return "No pending changes."
    applied: list[str] = []
    failed: list[str] = []
    for target in targets:
        entry = entries.get(target)
        if entry is None:
            failed.append(f"{target}: no pending change.")
            continue
        read = reader or _fs_read
        write = writer or _fs_write
        seen = await read(target)
        expected = entry.get("old_text")
        if expected is not None and seen is not None and seen != expected:
            failed.append(f"{target}: file changed since preview; kept pending.")
            continue
        await write(target, entry["new_text"])
        store.pop(target)
        applied.append(target)
    lines = [f"Applied {p}." for p in applied] + failed
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Wrapper tool factories
# ---------------------------------------------------------------------------


def _default_ask(prompt: str) -> bool:
    answer = input(f"{prompt}\nApply? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def make_gated_write(
    *,
    cwd: str | Path,
    get_mode: Callable[[], str] | None = None,
    ask: AskCallable | None = None,
    store: PendingStore | None = None,
    reader: AsyncReader | None = None,
    writer: AsyncWriter | None = None,
):
    """Build the gated ``write`` wrapper (same name as the builtin it replaces)."""
    if get_mode is None:
        get_mode = lambda: DiffConfig.load().mode  # noqa: E731
    ask_fn = ask if ask is not None else _default_ask

    @tool(name="write", context="tool_context")
    async def gated_write(path: str, content: str, tool_context: Any = None) -> str:
        """Write a file, creating it or overwriting it, subject to /diff review.

        Args:
            path: Absolute path, or relative to the working directory.
            content: The full file content to write.
        """
        old_text = await _current_text(str(confine(resolve(path, cwd), cwd)), reader, tool_context)
        preview = unified_diff(old_text or "", content, path)
        return await _gate_and_apply(
            op="write",
            raw_path=path,
            old_text=old_text,
            new_text=content,
            preview=preview,
            cwd=cwd,
            get_mode=get_mode,
            ask=ask_fn,
            store=store,
            reader=reader,
            writer=writer,
            tool_context=tool_context,
        )

    return gated_write


def make_gated_edit(
    *,
    cwd: str | Path,
    get_mode: Callable[[], str] | None = None,
    ask: AskCallable | None = None,
    store: PendingStore | None = None,
    reader: AsyncReader | None = None,
    writer: AsyncWriter | None = None,
):
    """Build the gated ``edit`` wrapper (same name as the builtin it replaces)."""
    if get_mode is None:
        get_mode = lambda: DiffConfig.load().mode  # noqa: E731
    ask_fn = ask if ask is not None else _default_ask

    @tool(name="edit", context="tool_context")
    async def gated_edit(path: str, old_str: str, new_str: str, tool_context: Any = None) -> str:
        """Replace an exact string in a file, subject to /diff review.

        Args:
            path: Absolute path, or relative to the working directory.
            old_str: Exact text to find. Must be unique within the file.
            new_str: Replacement text.
        """
        confined = confine(resolve(path, cwd), cwd)
        current = await _current_text(str(confined), reader, tool_context)
        if current is None:
            raise ValueError(f"Cannot edit {confined}: file does not exist.")
        occurrences = current.count(old_str)
        if occurrences == 0:
            raise ValueError(f"old_str did not appear verbatim in {confined}.")
        if occurrences > 1:
            raise ValueError(
                f"old_str appears {occurrences} times in {confined}; make it unique."
            )
        new_text = current.replace(old_str, new_str, 1)
        preview = unified_diff(current, new_text, path)
        return await _gate_and_apply(
            op="edit",
            raw_path=path,
            old_text=current,
            new_text=new_text,
            preview=preview,
            cwd=cwd,
            get_mode=get_mode,
            ask=ask_fn,
            store=store,
            reader=reader,
            writer=writer,
            tool_context=tool_context,
        )

    return gated_edit
