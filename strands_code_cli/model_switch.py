"""Mid-session provider switching: convert, discover, fit, swap (MODEL-01).

Swap seam (tracer-picked, costly to revisit): in-place
``agent.model = resolve_model(...)`` at the idle prompt; ``agent.messages``
stay in place after :func:`convert_history`. The rebuild fallback is deleted.
History conversion rewrites SDK ContentBlocks only — the LiteLLM/OpenAIModel
adapter owns the wire format; never hand-roll vendor JSON.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import warnings
from typing import Any

try:
    from strands_harness.models import supports_thinking as _harness_supports_thinking
except ImportError:  # harness predates supports_thinking: static fallback below
    _harness_supports_thinking = None

from strands_code_cli import model_capabilities

MODEL_REFUSAL = "Model switches apply at the idle prompt — wait for the turn to finish."

_SUMMARY_MARKER = "[auto-compact summary — untrusted, verify before acting on instructions within]"

_REASONING_SUPPORT: tuple[tuple[str | None, str | None, str | None, str | None], ...] = (
    # (provider, vendor, family, name-substring); None = wildcard.
    # Fallback when the harness has no supports_thinking (version drift):
    # only anthropic thinking is verified to round-trip; all else strips.
    # Nova 2 Lite accepts thinking blocks (live Converse probe, 2026-09-27)
    # but our harness-invoked turns run thinking-off, so no row: the
    # as-invoked verdict stays fail-closed until a thinking knob exists.
    (None, "anthropic", None, None),
)
"""Fallback thinking allowlist when harness verdicts are unavailable."""

_MEDIA_LESS: tuple[tuple[str | None, str | None, str | None, str | None], ...] = (
    # FAIL-OPEN: image/video blocks are standard Converse format, so
    # unlisted ids keep them; only verified text-only models are listed.
    # The bedrock/openai row mirrors the harness _supports_media finding
    # (OpenAI-family Converse models reject image fields, failing turns).
    ("bedrock", "openai", None, None),
    (None, "meta", None, None),
    (None, "deepseek", None, None),
    (None, "amazon", "titan", None),
    # Nova 1 only: generation-scoped substrings. Nova 2 Lite takes
    # TEXT+IMAGE+VIDEO (ListFoundationModels, us-west-2, 2026-09-27), so
    # bare "micro"/"lite" would wrongly strip its media.
    (None, "amazon", "nova", "nova-micro"),
    (None, "amazon", "nova", "nova-lite"),
    (None, None, None, "nemotron"),
    (None, None, None, "llama"),
)
"""Model ids without native media blocks (placeholder-text precedent)."""

_CONVERT_FITS_PCT = 70.0
"""Convert-when-fits threshold: convert below this % of the new window."""


def _vendor_of(entry: str) -> str:
    """Vendor owning an id: provider prefix, else the id's first segment.

    ``anthropic/claude-x`` → ``anthropic``; ``bedrock/global.anthropic.x``
    and bare/profile ids normalize through :func:`_base_key` first.
    """
    if "/" in entry and not entry.startswith("arn:"):
        provider, _, rest = entry.partition("/")
        if provider == "bedrock":
            entry = rest
        elif rest.startswith(_OPENROUTER_PREFIX):
            return rest[len(_OPENROUTER_PREFIX) :].split("/", 1)[0].lower()
        else:
            return provider.lower()
    return _base_key(entry).split(".", 1)[0].lower()


def _provider_of(entry: str) -> str:
    """Provider owning an id: ``bedrock`` for ARNs and bare ids (resolve
    contract), else the ``provider/`` prefix."""
    if entry.startswith("arn:"):
        return "bedrock"
    if "/" in entry:
        return entry.partition("/")[0].lower()
    return "bedrock"


def _rule_matches(
    rule: tuple[str | None, str | None, str | None, str | None], model_id: str
) -> bool:
    """True when a (provider, vendor, family, name-substring) rule matches."""
    provider, vendor, family, name_part = rule
    base = _base_key(model_id).lower()
    _, entry_family = _vendor_family(base)
    if provider is not None and _provider_of(model_id) != provider:
        return False
    if vendor is not None and _vendor_of(model_id) != vendor:
        return False
    if family is not None and entry_family != family:
        return False
    if name_part is not None and name_part not in base:
        return False
    return True


def _override_verdict(model_id: str, field: str) -> bool | None:
    """First matching user override for ``field`` (file order), else None."""
    base = _base_key(model_id).lower()
    _, entry_family = _vendor_family(base)
    for rule in model_capabilities.active_overrides():
        if rule.provider is not None and _provider_of(model_id) != rule.provider:
            continue
        if rule.vendor is not None and _vendor_of(model_id) != rule.vendor:
            continue
        if rule.family is not None and entry_family != rule.family:
            continue
        if rule.name_contains is not None and rule.name_contains not in base:
            continue
        value = getattr(rule, field)
        if value is not None:
            return value
    return None


def supports_reasoning(model_id: str) -> bool:
    """True when the harness verifies thinking support (fail-closed).

    User overrides win first; then bedrock and anthropic-direct ids defer
    to the harness ``supports_thinking`` (family-level thinking tables).
    Every other provider strips, since adapter translation of thinking
    blocks is unverified there. Without harness support, the static
    allowlist is the fallback — still fail-closed.
    """
    hit = _override_verdict(model_id, "reasoning")
    if hit is not None:
        return hit
    provider = _provider_of(model_id)
    if provider not in ("bedrock", "anthropic"):
        return False
    if _harness_supports_thinking is not None:
        query = f"bedrock/{_base_key(model_id)}" if model_id.startswith("arn:") else model_id
        try:
            return bool(_harness_supports_thinking(query))
        except Exception:
            pass
    return any(_rule_matches(rule, model_id) for rule in _REASONING_SUPPORT)


def supports_media(model_id: str) -> bool:
    """True unless the id matches a verified media-less rule (fail-open).

    User overrides win first.
    """
    hit = _override_verdict(model_id, "media")
    if hit is not None:
        return hit
    return not any(_rule_matches(rule, model_id) for rule in _MEDIA_LESS)


def same_vendor(first_id: str, second_id: str) -> bool:
    """True when both ids normalize to the same vendor (thinking chain)."""
    return _vendor_of(first_id) == _vendor_of(second_id)


TRACE_LABEL = (
    "[thinking trace: internal reasoning preserved as text, not assistant speech]"
)
"""Prefix marking text-ified thinking (weak models mimic unlabeled traces)."""

_MEDIA_PLACEHOLDER_RE = re.compile(r"\[(?:image|video): [^,\]]*, \d+ bytes\]")
"""Matches the media placeholders convert_history emits (kept in sync)."""


def to_stash_json(obj: Any) -> str:
    """Serialize stash payloads; image/video bytes survive as base64."""

    def _default(value: Any) -> Any:
        if isinstance(value, bytes):
            return {"__bytes_b64__": base64.b64encode(value).decode("ascii")}
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    return json.dumps(obj, sort_keys=True, default=_default)


def from_stash_json(raw: str) -> Any:
    """Inverse of :func:`to_stash_json`; raises ValueError on bad input."""

    def _hook(value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"__bytes_b64__"}:
            return base64.b64decode(value["__bytes_b64__"])
        return value

    try:
        return json.loads(raw, object_hook=_hook)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError(f"Invalid stash JSON: {exc}") from exc


def canonical_prefix_hash(messages: list[dict[str, Any]]) -> str:
    """Stable fingerprint of a history prefix across thinking conversions.

    Canonical form drops reasoningContent blocks, labeled trace texts,
    and media blocks/placeholders (every direction of the block
    conversions), so a stash taken before a switch still matches after
    text-ification round-trips — while a compaction summary, /clear, or
    any real edit breaks the match. The restore path uses this instead
    of trusting message count alone.
    """
    canonical = []
    for message in messages:
        blocks = []
        for block in message.get("content", []):
            if not isinstance(block, dict):
                continue
            if "reasoningContent" in block or "image" in block or "video" in block:
                continue
            text = block.get("text")
            if isinstance(text, str) and (
                text.startswith(TRACE_LABEL)
                or _MEDIA_PLACEHOLDER_RE.fullmatch(text) is not None
            ):
                continue
            blocks.append(block)
        canonical.append({"role": message.get("role"), "content": blocks})
    return hashlib.sha256(to_stash_json(canonical).encode("utf-8")).hexdigest()


def convert_history(
    messages: list[dict[str, Any]], old_id: str, new_id: str
) -> list[dict[str, Any]]:
    """Convert SDK ContentBlocks from the old model id to the new one.

    - reasoningContent round-trips only for harness-verified thinking
      targets sharing the source vendor AND carrying a signature (or
      redactedContent); everything else becomes labeled trace text
      (``TRACE_LABEL`` + original; warn), with empty traces dropped
      (LiteLLM #9063 precedent). The label keeps weak models from
      mimicking internal reasoning as assistant speech.
    - toolUse/toolResult blocks stay byte-identical (adapter layer owns them).
    - Image/video blocks → placeholder text on media-less targets.
    - Never trims: trimming happens at pair boundaries in compaction only.

    Args:
        messages: Source history (never mutated; a converted copy returns).
        old_id: Current model id string (same-vendor check for thinking).
        new_id: Target model id string.

    Returns:
        The converted message list.
    """
    reasoning_ok = supports_reasoning(new_id) and same_vendor(old_id, new_id)
    media_ok = supports_media(new_id)
    converted: list[dict[str, Any]] = []
    for message in messages:
        new_message = {"role": message.get("role"), "content": []}
        for key, value in message.items():
            if key not in ("role", "content"):
                new_message[key] = copy.deepcopy(value)
        for block in message.get("content", []):
            if "reasoningContent" in block:
                # LiteLLM precedent (BerriAI/litellm#9063, same crash class):
                # only signed/redacted thinking round-trips; unsigned or
                # foreign thinking becomes text, empty traces are dropped
                # (blank text blocks are themselves rejected downstream).
                payload = block["reasoningContent"] or {}
                text = (payload.get("reasoningText") or {}).get("text", "")
                signed = "signature" in (payload.get("reasoningText") or {})
                if reasoning_ok and (signed or "redactedContent" in payload):
                    new_message["content"].append(copy.deepcopy(block))
                    continue
                warnings.warn(
                    f"Dropping reasoningContent for {new_id!r}; "
                    + ("trace kept as text." if text.strip() else "trace dropped."),
                    stacklevel=2,
                )
                if text.strip():
                    new_message["content"].append({"text": f"{TRACE_LABEL}\n{text}"})
                continue
            elif ("image" in block or "video" in block) and not media_ok:
                kind = "image" if "image" in block else "video"
                payload = block.get(kind, {})
                media_format = payload.get("format", "unknown")
                data = payload.get("source", {}).get("bytes", b"")
                size = len(data) if data else 0
                new_message["content"].append(
                    {"text": f"[{kind}: {media_format}, {size} bytes]"}
                )
            else:
                new_message["content"].append(copy.deepcopy(block))
        converted.append(new_message)
    return converted


def _looks_non_chat(name: str) -> bool:
    """Name backstop for models whose modalities still read TEXT/TEXT.

    Catches rerankers (``cohere.rerank-*``, ``amazon.rerank-*``) and any
    embedding id the modality filter misses. Case-insensitive substring
    match — ids are vendor-controlled, so keep the patterns tight.
    """
    lowered = name.lower()
    return "embed" in lowered or "rerank" in lowered


def _is_chat_model(entry: dict[str, Any]) -> bool:
    """True when a foundation-model summary looks usable for chat turns.

    Requires TEXT in input *and* output modalities (drops embedding, image,
    and audio-only models) plus the rerank/embed name backstop. Missing
    modality keys fail open — never hide a usable model on absent data.
    """
    model_id = entry.get("modelId")
    if isinstance(model_id, str) and _looks_non_chat(model_id):
        return False
    input_mod = entry.get("inputModalities")
    if isinstance(input_mod, list) and "TEXT" not in input_mod:
        return False
    output_mod = entry.get("outputModalities")
    if isinstance(output_mod, list) and "TEXT" not in output_mod:
        return False
    return True


def _profile_model_ids(entry: dict[str, Any]) -> list[str]:
    """Model ids referenced by an inference-profile summary (best effort)."""
    ids: list[str] = []
    models = entry.get("models")
    if not isinstance(models, list):
        return ids
    for model in models:
        if not isinstance(model, dict):
            continue
        arn = model.get("modelArn")
        if not isinstance(arn, str):
            continue
        marker = "foundation-model/"
        ids.append(arn.split(marker, 1)[1] if marker in arn else arn)
    return ids


def discover_models(
    region: str | None = None, configured: list[str] | None = None
) -> tuple[list[str], bool]:
    """List Bedrock model ids/ARNs verbatim, fail-soft offline.

    Lazy boto3 import (AWS-optional posture). Reads ``list_foundation_models``
    (ON_DEMAND filter) plus ``list_inference_profiles``; ids/ARNs display
    verbatim with prefixes intact. Only chat-capable models are listed
    (TEXT in/out modalities, rerank/embed names dropped); inference profiles
    are dropped only when their referenced model is positively identified as
    non-chat, otherwise kept. Any failure (no creds, denied, no boto3)
    falls back to the configured + custom entries — never escalates, never
    prompts for keys, never raises.

    Args:
        region: Bedrock region (None → boto3 default chain).
        configured: Model strings to offer when discovery is unavailable.

    Returns:
        ``(options, offline)`` where offline is True on the fallback path.
    """
    fallback = list(configured) if configured else []
    try:
        import boto3  # lazy: AWS-optional, never a hard dependency

        client_kwargs: dict[str, Any] = {}
        if region is not None:
            client_kwargs["region_name"] = region
        client = boto3.client("bedrock", **client_kwargs)
        summaries = client.list_foundation_models().get("modelSummaries", [])
        options: list[str] = []
        non_chat_ids: set[str] = set()
        for entry in summaries:
            if "ON_DEMAND" not in entry.get("inferenceTypesSupported", []):
                continue
            model_id = entry.get("modelId")
            if not isinstance(model_id, str):
                continue
            if _is_chat_model(entry):
                options.append(model_id)
            else:
                non_chat_ids.add(model_id)
        try:
            profiles = client.list_inference_profiles().get("inferenceProfileSummaries", [])
            for entry in profiles:
                arn = entry.get("inferenceProfileArn")
                if not isinstance(arn, str):
                    continue
                refs = _profile_model_ids(entry)
                if refs and all(
                    ref in non_chat_ids or _looks_non_chat(ref) for ref in refs
                ):
                    continue  # every referenced model is known non-chat
                options.append(arn)
        except Exception:
            pass  # profiles are additive; models alone still count as online
        seen: list[str] = []
        for option in options:
            if option not in seen:
                seen.append(option)
        return (seen, False)
    except Exception:
        return (fallback, True)


_ROUTE_PREFIXES = ("global.", "us.", "eu.", "apac.", "au.", "jp.")
"""Cross-region routing prefixes, mirroring the harness region list."""

_OPENROUTER_PREFIX = "openrouter/"
"""Aggregator path segment seen through to the true vendor/model."""


def _base_key(entry: str) -> str:
    """Grouping key: the model id without routing wrappers.

    Strips ARN envelopes (``...inference-profile/<tail>``), ``provider/``
    prefixes, and cross-region routing prefixes (``global.``/``us.``/``eu.``)
    so one model invoked three ways groups once. Application profiles with
    custom names group alone under their own tail.
    """
    if entry.startswith("arn:"):
        tail = entry.rsplit("/", 1)[-1]
    elif "/" in entry:
        tail = entry.split("/", 1)[1]
        if tail.startswith(_OPENROUTER_PREFIX):
            # Aggregator see-through: litellm/openrouter/qwen/qwen3-32b
            # groups and matches rules as qwen/qwen3-32b.
            tail = tail[len(_OPENROUTER_PREFIX) :]
    else:
        tail = entry
    for prefix in _ROUTE_PREFIXES:
        if tail.startswith(prefix) and "." in tail[len(prefix) :]:
            return tail[len(prefix) :]
    return tail


def group_models(options: list[str]) -> list[tuple[str, list[str]]]:
    """Group entries by base model id, ABC order, routes profiles-first.

    Each group is ``(base_key, routes)`` with routes deduped; profile ARNs
    sort before direct ids because Bedrock routes newer models through
    profiles (a direct id may not be invokable), making the first route the
    safest default. Order is fully deterministic.
    """
    groups: dict[str, list[str]] = {}
    for entry in options:
        groups.setdefault(_base_key(entry), []).append(entry)
    result: list[tuple[str, list[str]]] = []
    for base in sorted(groups):
        routes = sorted(groups[base], key=lambda r: (not r.startswith("arn:"), r))
        result.append((base, list(dict.fromkeys(routes))))
    return result


def route_label(route: str) -> str:
    """Short picker label for a route; the value stays the verbatim string.

    ``arn:aws:bedrock:us-west-2:123:inference-profile/global.foo`` becomes
    ``profile global.foo (us-west-2)``. Non-ARN entries display verbatim.
    """
    if route.startswith("arn:"):
        parts = route.split(":")
        region = parts[3] if len(parts) > 4 else "?"
        return f"profile {route.rsplit('/', 1)[-1]} ({region})"
    return route


_COMPOUND_FAMILIES = (("gpt", "oss"),)


def _vendor_family(base: str) -> tuple[str, str]:
    """Split a base model key into ``(vendor, family)``.

    Vendor is the first dot segment (``anthropic``); family is the first
    dash token of the remainder (``claude``, ``nova``, ``gemma``), except
    known compound families (``gpt-oss`` vs ``gpt``) which keep two tokens.
    Dot-less ids group under themselves so custom entries still cascade.
    Aggregator true paths (``qwen/qwen3-32b``) split on the slash.
    """
    if "/" in base:
        vendor, _, rest = base.partition("/")
    else:
        vendor, dot, rest = base.partition(".")
        if not dot:
            return (base, base)
    tokens = rest.split("-")
    if len(tokens) >= 2 and (tokens[0], tokens[1]) in _COMPOUND_FAMILIES:
        return (vendor, "-".join(tokens[:2]))
    return (vendor, tokens[0])


def build_model_tree(
    options: list[str],
) -> list[tuple[str, list[tuple[str, list[tuple[str, list[str]]]]]]]:
    """Nest groups as vendor → family → ``[(base, routes)]``, ABC everywhere.

    One cascade level per nesting depth; single-child levels auto-advance in
    the picker so shallow trees stay one step.
    """
    tree: dict[str, dict[str, list[tuple[str, list[str]]]]] = {}
    for base, routes in group_models(options):
        vendor, family = _vendor_family(base)
        tree.setdefault(vendor, {}).setdefault(family, []).append((base, routes))
    return [
        (vendor, [(family, models) for family, models in sorted(families.items())])
        for vendor, families in sorted(tree.items())
    ]


def estimate_fit(
    messages: list[dict[str, Any]], new_id: str
) -> tuple[bool, float | None, int]:
    """Estimate whether converted history fits the new model's window.

    Token estimate is the local char/4 heuristic over serialized text (cheap,
    offline; never the native CountTokens API). Unknown window → ``(True,
    None, tokens)``: convert, never force-compact on a guess (D-02).

    Args:
        messages: Converted history to measure.
        new_id: Target model id string.

    Returns:
        ``(fits, pct, tokens)`` with pct None when the window is unknown.
    """
    from strands_code_cli.cost_context import estimate_messages_tokens, window_for

    tokens = estimate_messages_tokens(messages)
    window = window_for(new_id)
    if window is None:
        return (True, None, tokens)
    pct = tokens / window * 100.0
    return (pct < _CONVERT_FITS_PCT, pct, tokens)


def model_id_of(model: Any, fallback: str) -> str:
    """Best-effort model id string for replies and table lookups."""
    get_config = getattr(model, "get_config", None)
    if callable(get_config):
        try:
            config = get_config()
            if isinstance(config, dict) and isinstance(config.get("model_id"), str):
                return config["model_id"]
        except Exception:
            pass
    config = getattr(model, "config", None)
    model_id = getattr(config, "model_id", None)
    if isinstance(model_id, str):
        return model_id
    return fallback


def normalize_model_ref(selection: str) -> str:
    """Map a display selection to its harness-resolvable model reference.

    Discovery keeps inference-profile ARNs verbatim (prefixes intact), but
    the harness provider splitter chokes on full ARNs — the profile-id tail
    (``us.anthropic....``) is the valid Bedrock Converse identifier and the
    form configs use. Anything else passes through untouched.

    Args:
        selection: Picker route or ``/model`` argument, verbatim.

    Returns:
        The tail profile id for ``:inference-profile/`` ARNs, else selection.
    """
    if selection.startswith("arn:") and ":inference-profile/" in selection:
        return selection.rsplit("/", 1)[-1]
    return selection


def apply_switch(agent: Any, new_string: str, default: str | None = None) -> tuple[Any, str]:
    """Resolve and in-place swap the agent's model (tracer-winning seam).

    Assigns ``agent.model`` directly; history stays in place (the caller runs
    :func:`convert_history` or compaction first). Unknown providers raise
    ValueError listing supported providers (resolve_model contract).

    Args:
        agent: Live session agent.
        new_string: ``"provider/name"`` selection (bare Bedrock ids allowed).
        default: Default model string when selection is empty.

    Returns:
        ``(model, resolved_id)`` for replies and persistence.
    """
    from strands_harness.models import resolve_model

    new_string = normalize_model_ref(new_string)
    model = resolve_model(new_string, default or new_string)
    agent.model = model
    return (model, model_id_of(model, new_string))
