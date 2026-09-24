"""Persisted provider choice for the CLI entry path (D-06)."""

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
_CONFIG_FILE_NAME = "config.yaml"

_KNOWN_KEYS = {"model"}


def default_config_path() -> Path:
    """User config file path (platformdirs home, never a repo-relative path)."""
    return Path(platformdirs.user_config_dir(_CONFIG_DIR_NAME)) / _CONFIG_FILE_NAME


@dataclass
class ProviderConfig:
    """Persisted provider choice for Phase 5 ``/model`` to inherit.

    The loaded ``model`` string feeds ``create_harness`` as a constructor
    kwarg; the file holds only the provider string, never credentials.
    """

    model: str | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> ProviderConfig:
        """Load config fail-soft: missing or corrupt files yield defaults.

        Raises:
            ValueError: On unknown keys or a non-string model value.
        """
        resolved = Path(path) if path is not None else default_config_path()
        if resolved.is_symlink():
            raise ValueError(f"Provider config must not be a symlink: {resolved}")
        if not resolved.exists():
            return cls()
        try:
            data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            logger.warning("Ignoring unreadable provider config: %s", exc)
            return cls()
        if data is None:
            return cls()
        if not isinstance(data, dict):
            logger.warning("Ignoring malformed provider config (not a mapping)")
            return cls()
        unknown = set(data) - _KNOWN_KEYS
        if unknown:
            raise ValueError(f"Unknown provider config keys: {sorted(unknown)}")
        model = data.get("model")
        if model is not None and not isinstance(model, str):
            raise ValueError("Provider config 'model' must be a string")
        return cls(model=model)

    def save(self, path: str | Path | None = None) -> Path:
        """Persist the provider choice; creates the config home when needed.

        Args:
            path: Override for tests; defaults to the platformdirs home.

        Returns:
            The config file path written.
        """
        if self.model is not None and not isinstance(self.model, str):
            raise ValueError("Provider config 'model' must be a string")
        resolved = Path(path) if path is not None else default_config_path()
        if resolved.is_symlink():
            raise ValueError(f"Provider config must not be a symlink: {resolved}")
        payload: dict[str, Any] = {}
        if self.model is not None:
            payload["model"] = self.model
        resolved.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(resolved.parent, 0o700)
        tmp = resolved.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(payload), encoding="utf-8")
        os.replace(tmp, resolved)
        return resolved
