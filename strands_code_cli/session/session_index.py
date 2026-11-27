"""Sidecar session title index — CLI presentation state only.

Snapshot blobs under the session dir are SDK-owned; titles, rename state,
and recency timestamps live here, keyed by session id. This module never
reads or writes snapshot blob content.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strands_code_cli.platform_io import (
    atomic_write_text,
    ensure_private_dir,
    refuse_symlink,
)

_INDEX_NAME = "index.json"
_TITLE_MAX_CHARS = 120
_RICH_STASH_DIRNAME = "rich_history"


def _utcnow() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def rich_stash_path(index_root: Path, session_id: str) -> Path | None:
    """Sidecar path for the persisted thinking stash (None when unsafe).

    CLI-owned state next to the session index — never inside a snapshot
    blob. Over-strict id characters fail soft (no stash) rather than
    risking path traversal through a user-supplied session id.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", session_id):
        return None
    return Path(index_root) / _RICH_STASH_DIRNAME / f"{session_id}.json"


class SessionIndex:
    """JSON sidecar mapping session ids to titles and timestamps.

    Fail-soft on read: a missing or corrupt index loads as empty, never
    raises. Fail-loud on tamper: symlinked roots or index files raise
    ``ValueError`` instead of being followed.

    Args:
        root: Directory holding ``index.json``. Created with ``0o700``
            permissions when absent.
    """

    def __init__(self, root: str | Path) -> None:
        raw = Path(root)
        self.root = ensure_private_dir(
            raw, "session index root", mode=0o700, max_ancestors=1
        )
        self._entries: dict[str, dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _index_path(self) -> Path:
        """Path of the sidecar file (never inside a snapshot blob)."""
        return self.root / _INDEX_NAME

    def _ensure_loaded(self) -> None:
        if self._entries is not None:
            return
        self._entries = {}
        path = self._index_path()
        refuse_symlink(path, "session index", max_ancestors=2)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self._entries = {
                str(sid): entry
                for sid, entry in data.items()
                if isinstance(entry, dict)
            }
            for entry in self._entries.values():
                entry.setdefault("renamed_by_user", False)

    def _save(self) -> None:
        assert self._entries is not None
        path = self._index_path()
        atomic_write_text(
            path,
            json.dumps(self._entries, indent=2),
            mode=0o600,
            dir_mode=0o700,
            refuse_ancestors=2,
            label="session index",
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def mint(self, title: str = "untitled") -> str:
        """Create a new session entry with a fresh UUID.

        Args:
            title: Initial title; replaced by rename/update_title later.

        Returns:
            The new session id.
        """
        self._ensure_loaded()
        assert self._entries is not None
        session_id = str(uuid.uuid4())
        now = _utcnow()
        self._entries[session_id] = {
            "title": self._validate_title(title),
            "created_at": now,
            "updated_at": now,
            "renamed_by_user": False,
        }
        self._save()
        return session_id

    def ensure(self, session_id: str) -> dict[str, Any]:
        """Register a session id if unknown and bump its recency stamp."""
        self._validate_id(session_id)
        self._ensure_loaded()
        assert self._entries is not None
        entry = self._entries.get(session_id)
        if entry is None:
            now = _utcnow()
            entry = {
                "title": "untitled",
                "created_at": now,
                "updated_at": now,
                "renamed_by_user": False,
            }
            self._entries[session_id] = entry
        else:
            entry["updated_at"] = _utcnow()
        self._save()
        return {"id": session_id, **entry}

    def list_recent(self, limit: int | None = None) -> list[dict[str, Any]]:
        """List known sessions ordered by recency (newest first)."""
        self._ensure_loaded()
        assert self._entries is not None
        ordered = sorted(
            self._entries.items(),
            key=lambda item: item[1].get("updated_at", ""),
            reverse=True,
        )
        if limit is not None:
            ordered = ordered[:limit]
        return [{"id": sid, **entry} for sid, entry in ordered]

    def forget(self, session_id: str) -> bool:
        """Drop a session entry entirely (the /forget core).

        Removes the title/recency record and persists. Snapshot blobs and
        sidecars live outside the index; the caller deletes those.

        Returns:
            True when an entry existed, False for unknown ids.
        """
        self._ensure_loaded()
        assert self._entries is not None
        if session_id not in self._entries:
            return False
        del self._entries[session_id]
        self._save()
        return True

    def rename(self, session_id: str, title: str) -> dict[str, Any]:
        """Rename a known session; marks it user-named so auto-title backs off.

        Raises ``KeyError`` when unknown, ``ValueError`` on invalid titles.
        """
        self._ensure_loaded()
        assert self._entries is not None
        if session_id not in self._entries:
            raise KeyError(f"Unknown session id: {session_id}")
        self._entries[session_id]["title"] = self._validate_title(title)
        self._entries[session_id]["renamed_by_user"] = True
        self._entries[session_id]["updated_at"] = _utcnow()
        self._save()
        return {"id": session_id, **self._entries[session_id]}

    def model_of(self, session_id: str) -> str | None:
        """Return the last persisted model id for ``session_id``, or None."""
        self._ensure_loaded()
        assert self._entries is not None
        entry = self._entries.get(session_id)
        if not isinstance(entry, dict):
            return None
        model = entry.get("model")
        return model.strip() if isinstance(model, str) and model.strip() else None

    def set_model(self, session_id: str, model_id: str) -> None:
        """Persist the active model id for ``session_id`` across resumes."""
        if not isinstance(model_id, str) or not model_id.strip():
            return
        self._ensure_loaded()
        assert self._entries is not None
        if session_id not in self._entries:
            return
        cleaned = model_id.strip()
        if self._entries[session_id].get("model") == cleaned:
            return
        self._entries[session_id]["model"] = cleaned
        self._entries[session_id]["updated_at"] = _utcnow()
        self._save()

    def update_title(self, session_id: str, title: str) -> dict[str, Any]:
        """Model auto-title path; never overwrites a manual rename (D-04)."""
        self._ensure_loaded()
        assert self._entries is not None
        if session_id not in self._entries:
            raise KeyError(f"Unknown session id: {session_id}")
        if self._entries[session_id].get("renamed_by_user"):
            return {"id": session_id, **self._entries[session_id]}
        self._entries[session_id]["title"] = self._validate_title(title)
        self._entries[session_id]["updated_at"] = _utcnow()
        self._save()
        return {"id": session_id, **self._entries[session_id]}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_id(session_id: str) -> str:
        """Reject empty ids; ids are dict keys, never path segments."""
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        return session_id

    @staticmethod
    def _validate_title(title: str) -> str:
        """Validate titles (T-02-01): reject blanks and path separators, cap length."""
        if not title or not title.strip():
            raise ValueError("title must be a non-empty string")
        cleaned = title.strip()
        if any(sep in cleaned for sep in ("/", "\\", "\x00")):
            raise ValueError("title must not contain path separators")
        return cleaned[:_TITLE_MAX_CHARS]


def resolve_session_prefix(
    known: set[str], target: str
) -> tuple[str | None, str | None, list[str]]:
    """Resolve an exact session id or a unique prefix against ``known`` ids.

    Returns ``(resolved_id, error_message, matches)``:
    - Exact match: ``(target, None, [])``
    - Unique prefix: ``(matches[0], None, matches)``
    - Ambiguous prefix: ``(None, msg, matches)``
    - No match: ``(None, None, [])``
    """
    if target in known:
        return (target, None, [])
    if not target:
        return (None, None, [])
    matches = sorted(sid for sid in known if sid.startswith(target))
    if len(matches) == 1:
        return (matches[0], None, matches)
    if len(matches) > 1:
        preview = ", ".join(matches[:5])
        suffix = f" (+{len(matches) - 5} more)" if len(matches) > 5 else ""
        return (
            None,
            f"Ambiguous session prefix {target!r}: matches {preview}{suffix}.",
            matches,
        )
    return (None, None, [])
