"""User capability overrides for model history conversion (aider-style).

Users meet new model families before shipped tables do. This file lets them
correct a verdict without waiting for a release::

    overrides:
      - match: {provider: bedrock, vendor: amazon, family: nova}
        reasoning: true
      - match: {name_contains: gpt-oss}
        media: true

Precedence (first match wins, file order): user file → harness verdict →
static fallback. All keys optional inside ``match``; an empty match targets
every model. Unknown *match* keys skip the whole entry (ignoring them would
silently widen the rule); malformed entries warn and skip — a typo here must
never break startup or conversion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import platformdirs
import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR_NAME = "strands-code"
_CAPABILITIES_FILE_NAME = "model-capabilities.yaml"

_MATCH_KEYS = {"provider", "vendor", "family", "name_contains"}
_ENTRY_KEYS = {"match", "reasoning", "media", "streaming_tools"}


@dataclass(frozen=True)
class CapabilityOverride:
    """One normalized override rule (None fields are wildcards)."""

    provider: str | None = None
    vendor: str | None = None
    family: str | None = None
    name_contains: str | None = None
    reasoning: bool | None = None
    media: bool | None = None
    streaming_tools: bool | None = None


def default_capabilities_path() -> Path:
    """User override file path (platformdirs home, never repo-relative)."""
    return Path(platformdirs.user_config_dir(_CONFIG_DIR_NAME)) / _CAPABILITIES_FILE_NAME


def load_capability_overrides(path: str | Path | None = None) -> list[CapabilityOverride]:
    """Load override rules fail-soft: problems yield warnings, never raises.

    Raises:
        ValueError: Only when the path is a symlink (same policy as config).
    """
    resolved = Path(path) if path is not None else default_capabilities_path()
    if resolved.is_symlink():
        raise ValueError(f"Capability overrides must not be a symlink: {resolved}")
    if not resolved.exists():
        return []
    try:
        data = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        logger.warning("Ignoring unreadable capability overrides: %s", exc)
        return []
    if data is None:
        return []
    if not isinstance(data, dict) or not isinstance(data.get("overrides"), list):
        logger.warning("Ignoring malformed capability overrides (want mapping with 'overrides' list)")
        return []
    rules: list[CapabilityOverride] = []
    for pos, entry in enumerate(data["overrides"]):
        rule = _parse_entry(entry, pos)
        if rule is not None:
            rules.append(rule)
    logger.info("Loaded %d capability override(s) from %s", len(rules), resolved)
    return rules


def _parse_entry(entry: object, pos: int) -> CapabilityOverride | None:
    """Normalize one entry; warn and return None when it cannot be trusted."""
    if not isinstance(entry, dict):
        logger.warning("Ignoring capability override #%d (not a mapping)", pos)
        return None
    unknown = set(entry) - _ENTRY_KEYS
    if unknown:
        logger.warning("Ignoring capability override #%d (unknown keys: %s)", pos, sorted(unknown))
        return None
    match = entry.get("match") or {}
    if not isinstance(match, dict):
        logger.warning("Ignoring capability override #%d ('match' not a mapping)", pos)
        return None
    unknown_match = set(match) - _MATCH_KEYS
    if unknown_match:
        logger.warning(
            "Ignoring capability override #%d (unknown match keys: %s)", pos, sorted(unknown_match)
        )
        return None
    normalized: dict[str, str] = {}
    for key, value in match.items():
        if not isinstance(value, str):
            logger.warning("Ignoring capability override #%d (match %r not a string)", pos, key)
            return None
        normalized[key] = value.lower()
    effects: dict[str, bool] = {}
    for field in ("reasoning", "media", "streaming_tools"):
        value = entry.get(field)
        if value is not None and not isinstance(value, bool):
            logger.warning(
                "Ignoring capability override #%d (%r not true/false)", pos, field
            )
            return None
        if value is not None:
            effects[field] = value
    return CapabilityOverride(
        provider=normalized.get("provider"),
        vendor=normalized.get("vendor"),
        family=normalized.get("family"),
        name_contains=normalized.get("name_contains"),
        reasoning=effects.get("reasoning"),
        media=effects.get("media"),
        streaming_tools=effects.get("streaming_tools"),
    )


_overrides_cache: list[CapabilityOverride] | None = None


def active_overrides() -> list[CapabilityOverride]:
    """Cached override rules (loaded once; restart picks up file changes)."""
    global _overrides_cache
    if _overrides_cache is None:
        _overrides_cache = load_capability_overrides()
    return _overrides_cache


def _reset_overrides_cache() -> None:
    """Drop the cache (tests only)."""
    global _overrides_cache
    _overrides_cache = None
