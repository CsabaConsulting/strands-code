"""Sidecar session title index — CLI presentation state only.

Snapshot blobs under the session dir are SDK-owned; titles, rename state,
and recency timestamps live here, keyed by session id. This module never
reads or writes snapshot blob content.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_INDEX_NAME = "index.json"
_TITLE_MAX_CHARS = 120


def _utcnow() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


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
        if raw.is_symlink():
            raise ValueError(f"Session index root must not be a symlink: {raw}")
        self.root = raw.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
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
        if path.is_symlink():
            raise ValueError(f"Session index must not be a symlink: {path}")
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
        if path.is_symlink():
            raise ValueError(f"Session index must not be a symlink: {path}")
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        os.replace(tmp, path)

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
