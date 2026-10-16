"""Persisted provider choice for the CLI entry path (D-06)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import platformdirs
import yaml

from strands_code_cli.policy.codeact import CodeactState

logger = logging.getLogger(__name__)

_CONFIG_DIR_NAME = "strands-code"
_CONFIG_FILE_NAME = "config.yaml"

_KNOWN_KEYS = {"model", "base_url", "codeact", "codeact_remember"}


def default_config_path() -> Path:
    """User config file path (platformdirs home, never a repo-relative path)."""
    return Path(platformdirs.user_config_dir(_CONFIG_DIR_NAME)) / _CONFIG_FILE_NAME


@dataclass
class ProviderConfig:
    """Persisted provider choice for Phase 5 ``/model`` to inherit.

    The loaded ``model`` string feeds ``create_harness`` as a constructor
    kwarg; the file holds only the model string plus the non-secret
    ``base_url`` host for custom OpenAI-compatible endpoints — never keys.

    Phase 11 adds the CodeAct session-start keys (D-02/D-03):
    ``codeact`` is the persisted last interface choice, honored only
    when ``codeact_remember`` is true — otherwise sessions start on
    tool-calling.
    """

    model: str | None = None
    base_url: str | None = None
    codeact: str | None = None
    codeact_remember: bool = False

    @classmethod
    def load(cls, path: str | Path | None = None) -> ProviderConfig:
        """Load config fail-soft: missing or corrupt files yield defaults.

        Raises:
            ValueError: On unknown keys, a non-string model value, a
                codeact value outside ``tool|code|both``, or a
                non-bool codeact_remember value.
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
        base_url = data.get("base_url")
        if base_url is not None and not isinstance(base_url, str):
            raise ValueError("Provider config 'base_url' must be a string")
        codeact = data.get("codeact")
        if codeact is not None and codeact not in CodeactState.VALID:
            raise ValueError("Provider config 'codeact' must be one of tool|code|both")
        remember = data.get("codeact_remember")
        if remember is not None and not isinstance(remember, bool):
            raise ValueError("Provider config 'codeact_remember' must be a bool")
        return cls(
            model=model,
            base_url=base_url,
            codeact=codeact,
            codeact_remember=bool(remember),
        )

    def save_model_choice(self, model: str, path: str | Path | None = None) -> Path:
        """Persist a /model switch keeping other keys (never credentials)."""
        if not isinstance(model, str):
            raise ValueError("Provider config 'model' must be a string")
        self.model = model
        return self.save(path)

    def save_codeact_choice(self, codeact: str, path: str | Path | None = None) -> Path:
        """Persist a /codeact switch keeping other keys (never credentials)."""
        if codeact not in CodeactState.VALID:
            raise ValueError("Provider config 'codeact' must be one of tool|code|both")
        self.codeact = codeact
        return self.save(path)

    def save(self, path: str | Path | None = None) -> Path:
        """Persist the provider choice; creates the config home when needed.

        Args:
            path: Override for tests; defaults to the platformdirs home.

        Returns:
            The config file path written.
        """
        if self.model is not None and not isinstance(self.model, str):
            raise ValueError("Provider config 'model' must be a string")
        if self.base_url is not None and not isinstance(self.base_url, str):
            raise ValueError("Provider config 'base_url' must be a string")
        if self.codeact is not None and self.codeact not in CodeactState.VALID:
            raise ValueError("Provider config 'codeact' must be one of tool|code|both")
        if self.codeact_remember is not None and not isinstance(
            self.codeact_remember, bool
        ):
            raise ValueError("Provider config 'codeact_remember' must be a bool")
        resolved = Path(path) if path is not None else default_config_path()
        if resolved.is_symlink():
            raise ValueError(f"Provider config must not be a symlink: {resolved}")
        payload: dict[str, Any] = {}
        if self.model is not None:
            payload["model"] = self.model
        if self.base_url is not None:
            payload["base_url"] = self.base_url
        if self.codeact is not None:
            payload["codeact"] = self.codeact
        if self.codeact_remember:
            payload["codeact_remember"] = True
        resolved.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(resolved.parent, 0o700)
        tmp = resolved.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(payload), encoding="utf-8")
        os.replace(tmp, resolved)
        return resolved
