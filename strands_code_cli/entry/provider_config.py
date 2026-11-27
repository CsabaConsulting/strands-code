"""Persisted provider choice for the CLI entry path (D-06)."""

from __future__ import annotations

import logging
import unicodedata
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

_KNOWN_KEYS = {
    "model",
    "base_url",
    "api_mode",
    "codeact",
    "diff_mode",
    "memory_mode",
}
VALID_API_MODES = ("responses", "chat")
VALID_DIFF_MODES = ("on-demand", "auto")
VALID_MEMORY_MODES = ("curate", "silent")


def default_config_path() -> Path:
    """User config file path (platformdirs home, never a repo-relative path)."""
    return Path(platformdirs.user_config_dir(_CONFIG_DIR_NAME)) / _CONFIG_FILE_NAME


def _provider_of_model(model: str) -> str:
    """Normalized provider owning ``model`` (unwrapping openrouter/ollama under litellm)."""
    return provider_of(model, unwrap_litellm=True)


def _has_unsafe_str_chars(value: str) -> bool:
    """True when ``value`` contains whitespace or ASCII/C1/Bidi control chars."""
    return any(
        ch.isspace()
        or ord(ch) < 32
        or ord(ch) == 127
        or unicodedata.category(ch) in ("Cc", "Cf")
        for ch in value
    )


def _validate_base_url(base_url: str) -> None:
    """Validate persisted custom endpoint host: http(s) URL without embedded creds/query."""
    if not base_url or _has_unsafe_str_chars(base_url):
        raise ValueError(
            "Provider config 'base_url' must be a non-empty URL without whitespace or control characters"
        )
    try:
        parsed = urlsplit(base_url)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(
            "Provider config 'base_url' has an invalid URL or port"
        ) from exc
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ValueError(
            "Provider config 'base_url' must be an http:// or https:// URL with a host"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Provider config 'base_url' must not embed credentials")
    if parsed.query or parsed.fragment:
        raise ValueError(
            "Provider config 'base_url' must not include a query or fragment"
        )


def _validate_provider_fields(
    *,
    model: Any,
    base_url: Any,
    api_mode: Any,
    codeact: Any,
    diff_mode: Any,
    memory_mode: Any,
) -> None:
    """Validate persisted provider configuration field types and enums."""
    if model is not None:
        if not isinstance(model, str) or not model or _has_unsafe_str_chars(model):
            raise ValueError(
                "Provider config 'model' must be a non-empty model id without whitespace or control characters"
            )
    if base_url is not None:
        if not isinstance(base_url, str):
            raise ValueError("Provider config 'base_url' must be a string")
        _validate_base_url(base_url)
    enum_checks: tuple[tuple[str, Any, tuple[str, ...]], ...] = (
        ("api_mode", api_mode, VALID_API_MODES),
        ("codeact", codeact, CodeactState.VALID),
        ("diff_mode", diff_mode, VALID_DIFF_MODES),
        ("memory_mode", memory_mode, VALID_MEMORY_MODES),
    )
    for field_name, val, allowed in enum_checks:
        if val is not None and (not isinstance(val, str) or val not in allowed):
            raise ValueError(
                f"Provider config '{field_name}' must be one of {'|'.join(allowed)}"
            )


@dataclass
class ProviderConfig:
    """Persisted provider choice and session-start toggle defaults.

    The loaded ``model`` string feeds ``create_harness`` as a constructor
    kwarg; the file holds only non-secret provider settings and optional
    startup defaults (``codeact``, ``diff_mode``, ``memory_mode``) for
    session-sticky toggles — never credentials.
    """

    model: str | None = None
    base_url: str | None = None
    api_mode: str | None = None
    codeact: str | None = None
    diff_mode: str | None = None
    memory_mode: str | None = None

    @classmethod
    def load(cls, path: str | Path | None = None) -> ProviderConfig:
        """Load config fail-soft: missing or corrupt files yield defaults.

        Raises:
            ValueError: On unknown keys, invalid field types, or invalid enum values.
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
        diff_mode = data.get("diff_mode")
        memory_mode = data.get("memory_mode")
        _validate_provider_fields(
            model=model,
            base_url=base_url,
            api_mode=api_mode,
            codeact=codeact,
            diff_mode=diff_mode,
            memory_mode=memory_mode,
        )
        return cls(
            model=model,
            base_url=base_url,
            api_mode=api_mode,
            codeact=codeact,
            diff_mode=diff_mode,
            memory_mode=memory_mode,
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
            diff_mode=self.diff_mode,
            memory_mode=self.memory_mode,
        )
        resolved = Path(path) if path is not None else default_config_path()
        payload: dict[str, Any] = {}
        for key in (
            "model",
            "base_url",
            "api_mode",
            "codeact",
            "diff_mode",
            "memory_mode",
        ):
            val = getattr(self, key)
            if val is not None:
                payload[key] = val
        return atomic_write_text(
            resolved,
            yaml.safe_dump(payload),
            mode=0o600,
            dir_mode=0o700,
            refuse_ancestors=1,
            label="provider config",
        )
