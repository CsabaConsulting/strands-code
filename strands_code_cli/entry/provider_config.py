"""Persisted provider choice for the CLI entry path (D-06)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import platformdirs
import yaml

from strands_code_cli.model.provider_id import provider_of
from strands_code_cli.platform_io import atomic_write_text, refuse_symlink
from strands_code_cli.policy.codeact import CodeactState

logger = logging.getLogger(__name__)

_CONFIG_DIR_NAME = "strands-code"
_CONFIG_FILE_NAME = "config.yaml"

_KNOWN_KEYS = {"model", "base_url", "api_mode", "codeact", "codeact_remember"}
VALID_API_MODES = ("responses", "chat")


def default_config_path() -> Path:
    """User config file path (platformdirs home, never a repo-relative path)."""
    return Path(platformdirs.user_config_dir(_CONFIG_DIR_NAME)) / _CONFIG_FILE_NAME


def _provider_of_model(model: str) -> str:
    """Normalized provider owning ``model`` (unwrapping openrouter/ollama under litellm)."""
    return provider_of(model, unwrap_litellm=True)


def _validate_base_url(base_url: str) -> None:
    """Validate persisted custom endpoint host: http(s) URL without embedded creds."""
    if not base_url or any(
        ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in base_url
    ):
        raise ValueError(
            "Provider config 'base_url' must be a non-empty URL without whitespace"
        )
    parsed = urlsplit(base_url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError(
            "Provider config 'base_url' must be an http:// or https:// URL with a host"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Provider config 'base_url' must not embed credentials")


def _validate_provider_fields(
    *,
    model: Any,
    base_url: Any,
    api_mode: Any,
    codeact: Any,
    codeact_remember: Any,
) -> None:
    """Validate persisted provider configuration field types and enums."""
    if model is not None and not isinstance(model, str):
        raise ValueError("Provider config 'model' must be a string")
    if base_url is not None:
        if not isinstance(base_url, str):
            raise ValueError("Provider config 'base_url' must be a string")
        _validate_base_url(base_url)
    if api_mode is not None and (
        not isinstance(api_mode, str) or api_mode not in VALID_API_MODES
    ):
        raise ValueError("Provider config 'api_mode' must be one of responses|chat")
    if codeact is not None and codeact not in CodeactState.VALID:
        raise ValueError("Provider config 'codeact' must be one of tool|code|both")
    if codeact_remember is not None and not isinstance(codeact_remember, bool):
        raise ValueError("Provider config 'codeact_remember' must be a bool")


@dataclass
class ProviderConfig:
    """Persisted provider choice for Phase 5 ``/model`` to inherit.

    The loaded ``model`` string feeds ``create_harness`` as a constructor
    kwarg; the file holds only the model string plus the non-secret
    ``base_url`` host and optional ``api_mode`` (``responses|chat``) for
    custom OpenAI-compatible endpoints — never keys.

    Phase 11 adds the CodeAct session-start keys (D-02/D-03):
    ``codeact`` is the persisted last interface choice, honored only
    when ``codeact_remember`` is true — otherwise sessions start on
    tool-calling.
    """

    model: str | None = None
    base_url: str | None = None
    api_mode: str | None = None
    codeact: str | None = None
    codeact_remember: bool = False

    @classmethod
    def load(cls, path: str | Path | None = None) -> ProviderConfig:
        """Load config fail-soft: missing or corrupt files yield defaults.

        Raises:
            ValueError: On unknown keys, invalid field types, an
                ``api_mode`` outside ``responses|chat``, or a ``codeact``
                value outside ``tool|code|both``.
        """
        resolved = Path(path) if path is not None else default_config_path()
        refuse_symlink(resolved, "provider config", max_ancestors=1)
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
        base_url = data.get("base_url")
        api_mode = data.get("api_mode")
        codeact = data.get("codeact")
        remember = data.get("codeact_remember")
        _validate_provider_fields(
            model=model,
            base_url=base_url,
            api_mode=api_mode,
            codeact=codeact,
            codeact_remember=remember,
        )
        return cls(
            model=model,
            base_url=base_url,
            api_mode=api_mode,
            codeact=codeact,
            codeact_remember=bool(remember),
        )

    def save_model_choice(self, model: str, path: str | Path | None = None) -> Path:
        """Persist a /model switch keeping other keys (never credentials).

        Clears ``base_url`` and ``api_mode`` when switching across providers so
        one vendor's API key never routes to another vendor's custom proxy host.
        """
        if not isinstance(model, str):
            raise ValueError("Provider config 'model' must be a string")
        if self.model is not None and _provider_of_model(
            self.model
        ) != _provider_of_model(model):
            self.base_url = None
            self.api_mode = None
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
        _validate_provider_fields(
            model=self.model,
            base_url=self.base_url,
            api_mode=self.api_mode,
            codeact=self.codeact,
            codeact_remember=self.codeact_remember,
        )
        resolved = Path(path) if path is not None else default_config_path()
        payload: dict[str, Any] = {}
        if self.model is not None:
            payload["model"] = self.model
        if self.base_url is not None:
            payload["base_url"] = self.base_url
        if self.api_mode is not None:
            payload["api_mode"] = self.api_mode
        if self.codeact is not None:
            payload["codeact"] = self.codeact
        if self.codeact_remember:
            payload["codeact_remember"] = True
        return atomic_write_text(
            resolved,
            yaml.safe_dump(payload),
            mode=0o600,
            dir_mode=0o700,
            refuse_ancestors=1,
            label="provider config",
        )
