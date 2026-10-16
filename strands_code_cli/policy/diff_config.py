"""Persisted diff-review mode for the /diff gate (D-04).

Mirrors the :class:`ProviderConfig` shape exactly: dataclass, fail-soft
load, symlink refusal, atomic tmp+replace save, platformdirs home, never
repo-relative. Phase 4's mode system must not clash with this vocabulary
(``approve-each`` / ``on-demand`` / ``auto``); the ``auto`` here gates only
file mutations pending ``/diff`` review, never all tool calls (D-05).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import platformdirs
import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR_NAME = "strands-code"
_CONFIG_FILE_NAME = "diff.yaml"

MODES = ("approve-each", "on-demand", "auto")
DEFAULT_MODE = "on-demand"

_KNOWN_KEYS = {"mode"}


def default_diff_config_path() -> Path:
    """User diff-config file path (platformdirs home, never repo-relative)."""
    return Path(platformdirs.user_config_dir(_CONFIG_DIR_NAME)) / _CONFIG_FILE_NAME


@dataclass
class DiffConfig:
    """Persisted diff mode: approve-each (per-hunk), on-demand (stash), auto."""

    mode: str = DEFAULT_MODE

    @classmethod
    def load(cls, path: str | Path | None = None) -> DiffConfig:
        """Load fail-soft: missing, corrupt, or bogus-mode files yield defaults.

        Raises:
            ValueError: On symlinked paths or unknown keys.
        """
        resolved = Path(path) if path is not None else default_diff_config_path()
        if resolved.is_symlink():
            raise ValueError(f"Diff config must not be a symlink: {resolved}")
        if not resolved.exists():
            return cls()
        try:
            data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            logger.warning("Ignoring unreadable diff config: %s", exc)
            return cls()
        if data is None:
            return cls()
        if not isinstance(data, dict):
            logger.warning("Ignoring malformed diff config (not a mapping)")
            return cls()
        unknown = set(data) - _KNOWN_KEYS
        if unknown:
            raise ValueError(f"Unknown diff config keys: {sorted(unknown)}")
        mode = data.get("mode", DEFAULT_MODE)
        if mode not in MODES:
            logger.warning("Ignoring diff config with unknown mode %r", mode)
            return cls()
        return cls(mode=mode)

    def save(self, path: str | Path | None = None) -> Path:
        """Persist the diff mode; creates the config home when needed.

        Args:
            path: Override for tests; defaults to the platformdirs home.

        Returns:
            The config file path written.
        """
        if self.mode not in MODES:
            raise ValueError(f"Diff mode must be one of {MODES}, got {self.mode!r}")
        resolved = Path(path) if path is not None else default_diff_config_path()
        if resolved.is_symlink():
            raise ValueError(f"Diff config must not be a symlink: {resolved}")
        payload: dict[str, Any] = {"mode": self.mode}
        resolved.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(resolved.parent, 0o700)
        tmp = resolved.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(payload), encoding="utf-8")
        os.replace(tmp, resolved)
        return resolved
