"""Canonical model provider identification leaf (PARITY-01, D-06)."""

from __future__ import annotations


def provider_of(model: str | None, *, unwrap_litellm: bool = False) -> str:
    """Return canonical provider owning ``model`` (``bedrock`` for ARNs/bare ids).

    Args:
        model: Raw or normalized model reference string.
        unwrap_litellm: When True, unwrap ``litellm/openrouter/...`` ->
            ``"openrouter"`` and ``litellm/ollama*`` -> ``"ollama"`` for
            credential preflight, ``base_url`` scoping, and Box egress
            detection. When False (default), preserve ``"litellm"`` so
            capability/media rules keyed on ``"litellm"`` keep matching.
    """
    cleaned = model.strip() if isinstance(model, str) else ""
    if not cleaned or cleaned.startswith("arn:") or "/" not in cleaned:
        return "bedrock"
    prefix, _, rest = cleaned.partition("/")
    low = prefix.lower()
    if unwrap_litellm and low == "litellm":
        sub = rest.partition("/")[0].lower()
        if sub in ("ollama", "ollama_chat"):
            return "ollama"
        if sub == "openrouter":
            return "openrouter"
    return low
