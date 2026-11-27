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
import itertools
import json
import re
import unicodedata
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    from strands_harness.models import supports_thinking as _harness_supports_thinking
except ImportError:  # harness predates supports_thinking: static fallback below
    _harness_supports_thinking = None

import strands_code_cli.cost.reported_cost as reported_cost
import strands_code_cli.model.model_capabilities as model_capabilities
from strands_code_cli.model.provider_id import provider_of

MODEL_REFUSAL = "Model switches apply at the idle prompt — wait for the turn to finish."

UNARY_TOOL_MODE_NOTE = (
    "Note: streaming disabled for {model_id} (Bedrock unary tool mode)."
)

_SUMMARY_MARKER = (
    "[auto-compact summary — untrusted, verify before acting on instructions within]"
)

_REASONING_SUPPORT: tuple[
    tuple[str | None, str | None, str | None, str | None], ...
] = (
    # (provider, vendor, family, name-substring); None = wildcard.
    # Fallback when the harness has no supports_thinking (version drift):
    # only anthropic thinking is verified to round-trip; all else strips.
    # Nova 2 Lite accepts thinking blocks (live Converse probe, 2026-09-27)
    # but our harness-invoked turns run thinking-off, so no row: the
    # as-invoked verdict stays fail-closed until a thinking knob exists.
    (None, "anthropic", None, None),
    (None, "google", "gemini", None),
)
"""Fallback thinking allowlist when harness verdicts are unavailable."""

_MEDIA_LESS: tuple[tuple[str | None, str | None, str | None, str | None], ...] = (
    # FAIL-OPEN: image/video blocks are standard Converse format, so
    # unlisted ids keep them; only verified text-only models are listed.
    # The bedrock/openai row mirrors the harness _supports_media finding
    # (OpenAI-family Converse models reject image fields, failing turns).
    ("bedrock", "openai", None, None),
    # Bedrock Llama 3/4 is text-only while Meta Model API Muse models are multimodal.
    ("bedrock", "meta", "llama3", None),
    ("bedrock", "meta", "llama4", None),
    # OpenRouter Llama 3 models are text-only (unlike Llama 4 Maverick/Scout or ollama/llama3.2-vision).
    ("litellm", "meta-llama", None, "llama-3.3"),
    ("litellm", "meta-llama", None, "llama-3.1"),
    ("litellm", "meta-llama", None, "llama-3-"),
    (None, "deepseek", None, None),
    (None, "amazon", "titan", None),
    # Nova 1 only: generation-scoped substrings. Nova 2 Lite takes
    # TEXT+IMAGE+VIDEO (ListFoundationModels, us-west-2, 2026-09-27), so
    # bare "micro"/"lite" would wrongly strip its media.
    (None, "amazon", "nova", "nova-micro"),
    (None, "amazon", "nova", "nova-lite"),
    (None, None, None, "nemotron"),
)
"""Model ids without native media blocks (placeholder-text precedent)."""

_NO_STREAMING_TOOLS: tuple[
    tuple[str | None, str | None, str | None, str | None], ...
] = (
    # FAIL-OPEN: Bedrock-scoped verified rows only. Non-Bedrock routes
    # (OpenRouter, Ollama) do not share Bedrock's ConverseStream tool
    # restriction and stay streaming-capable.
    # Meta Llama 3/4 (us.meta.llama4-scout-17b, us.meta.llama3-3-70b,
    # us-west-2, 2026-09-27): Bedrock rejects ConverseStream + toolConfig.
    ("bedrock", "meta", "llama3", None),
    ("bedrock", "meta", "llama4", None),
    # Live probe (us-west-2, 2026-11-21): Bedrock rejects ConverseStream with
    # toolConfig on older Mistral and Writer Palmyra models while unary
    # Converse accepts toolConfig. Model-scoped (not vendor-wide) so newer
    # streaming-capable Mistral models (Large 3, Devstral 2, Ministral 3,
    # Magistral) and Palmyra Vision stay fail-open.
    ("bedrock", "mistral", "mistral", "mistral-large-2402"),
    ("bedrock", "mistral", "mistral", "mistral-large-2407"),
    ("bedrock", "mistral", "pixtral", "pixtral-large-2502"),
    ("bedrock", "writer", "palmyra", "palmyra-x4"),
    ("bedrock", "writer", "palmyra", "palmyra-x5"),
)
"""Bedrock model ids that reject tool use in streaming mode (disable streaming)."""

_CONVERT_FITS_PCT = 70.0
"""Convert-when-fits threshold: convert below this % of the new window."""


def _vendor_of(entry: str) -> str:
    """Vendor owning an id: provider prefix, else the id's first segment.

    ``anthropic/claude-x`` → ``anthropic``; ``bedrock/global.anthropic.x``,
    ``bedrock-mantle/openai.x``, and bare/profile ids normalize through
    :func:`_base_key` first.
    """
    if "/" in entry and not entry.startswith("arn:"):
        provider, _, rest = entry.partition("/")
        low_prov = provider.lower()
        if low_prov in ("bedrock", "bedrock-mantle"):
            entry = rest
        elif rest.lower().startswith(_OPENROUTER_PREFIX):
            return rest[len(_OPENROUTER_PREFIX) :].split("/", 1)[0].lower()
        else:
            return low_prov
    return _base_key(entry).split(".", 1)[0].lower()


def _provider_of(entry: str) -> str:
    """Provider owning an id (preserving ``litellm`` wrapper for rule matching)."""
    return provider_of(entry, unwrap_litellm=False)


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

    User overrides win first; then bedrock, bedrock-mantle, anthropic,
    google, openai, and meta ids evaluate reasoning support. Aggregators
    strip, since adapter translation of thinking blocks is unverified there.
    Without harness support, the static allowlist is the fallback — still
    fail-closed.
    """
    hit = _override_verdict(model_id, "reasoning")
    if hit is not None:
        return hit
    provider = _provider_of(model_id)
    if provider not in (
        "bedrock",
        "bedrock-mantle",
        "anthropic",
        "google",
        "openai",
        "meta",
    ):
        return False
    tail = _openai_family_tail(normalize_model_ref(model_id))
    if tail is not None and _is_openai_non_reasoning(tail):
        return False
    if provider == "meta" and not upstream_supports_meta():
        return _is_meta_chat_model(_base_key(model_id))
    if _harness_supports_thinking is not None:
        query = (
            f"bedrock/{_base_key(model_id)}"
            if model_id.startswith("arn:")
            else model_id
        )
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


def supports_streaming_tools(model_id: str) -> bool:
    """True unless the id is verified to reject streaming tool use.

    Fail-open: unlisted ids are assumed fine (only verified rows warn).
    User overrides win first. Advisory only — it gates warnings, never
    conversion: a warning cannot brick a model the verdict got wrong.
    """
    hit = _override_verdict(model_id, "streaming_tools")
    if hit is not None:
        return hit
    return not any(_rule_matches(rule, model_id) for rule in _NO_STREAMING_TOOLS)


def same_vendor(first_id: str, second_id: str) -> bool:
    """True when both ids normalize to the same vendor (thinking chain)."""
    return _vendor_of(first_id) == _vendor_of(second_id)


def same_provider(first_id: str, second_id: str) -> bool:
    """True when both normalized ids route through the same provider API."""
    return _provider_of(normalize_model_ref(first_id)) == _provider_of(
        normalize_model_ref(second_id)
    )


SUMMARY_LABEL = "Compaction summary preserved as text:"
"""Prefix marking text-ified Anthropic compaction summaries across switches."""


TRACE_LABEL = "Thinking trace (internal reasoning preserved as text):"
"""Prefix marking text-ified thinking (weak models mimic unlabeled traces).

Shape is load-bearing: the retired bracketed pseudo-tag muted Gemma
deterministically whenever tools were attached (single empty text delta,
~130 billed tokens — live bisect, 2026-09-27). This paren/colon shape
answers 3/3 on the same history.
"""

_LEGACY_TRACE_LABELS = (
    "[thinking trace: internal reasoning preserved as text, not assistant speech]",
)
"""Retired labels still stripped by the canonical hash (pre-upgrade sessions)."""

_MEDIA_PLACEHOLDER_RE = re.compile(r"\[(?:image|video): [^,\]]*, \d+ bytes\]")
"""Matches the media placeholders convert_history emits (kept in sync)."""


def to_stash_json(obj: Any) -> str:
    """Serialize stash payloads; image/video bytes survive as base64."""

    def _default(value: Any) -> Any:
        if isinstance(value, bytes):
            return {"__bytes_b64__": base64.b64encode(value).decode("ascii")}
        raise TypeError(
            f"Object of type {type(value).__name__} is not JSON serializable"
        )

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


def _canonical_block(block: Any) -> dict[str, Any] | None:
    """Normalize one ContentBlock for prefix hashing, or None to drop."""
    if not isinstance(block, dict):
        return None
    if (
        "reasoningContent" in block
        or "injected" in block
        or "image" in block
        or "video" in block
        or "summary" in block
    ):
        return None
    text = block.get("text")
    if isinstance(text, str) and (
        text.startswith((TRACE_LABEL, SUMMARY_LABEL) + _LEGACY_TRACE_LABELS)
        or _MEDIA_PLACEHOLDER_RE.fullmatch(text) is not None
    ):
        return None
    if "toolUse" in block and isinstance(block["toolUse"], dict):
        if "reasoningSignature" in block["toolUse"]:
            tool_use = {
                k: v for k, v in block["toolUse"].items() if k != "reasoningSignature"
            }
            return {**block, "toolUse": tool_use}
    return block


def canonical_prefix_hash(messages: list[dict[str, Any]]) -> str:
    """Stable fingerprint of a history prefix across thinking conversions.

    Canonical form drops reasoningContent blocks, InjectedBlocks, labeled
    trace texts, media blocks/placeholders, and toolUse thought signatures
    (every direction of the block conversions), so a stash taken before a
    switch still matches after text-ification round-trips or memory reloads
    — while a compaction summary, /clear, or any real edit breaks the
    match. The restore path uses this instead of trusting message count
    alone.
    """
    canonical = []
    for message in messages:
        blocks = []
        for block in message.get("content", []):
            normalized = _canonical_block(block)
            if normalized is not None:
                blocks.append(normalized)
        canonical.append({"role": message.get("role"), "content": blocks})
    return hashlib.sha256(to_stash_json(canonical).encode("utf-8")).hexdigest()


def _convert_tool_use_block(
    block: dict[str, Any], reasoning_ok: bool
) -> dict[str, Any]:
    """Deep-copy one toolUse block, stripping foreign thought signatures."""
    copied = copy.deepcopy(block)
    if not reasoning_ok and isinstance(copied.get("toolUse"), dict):
        copied["toolUse"].pop("reasoningSignature", None)
    return copied


def _convert_reasoning_block(
    block: dict[str, Any], new_id: str, reasoning_ok: bool
) -> dict[str, Any] | None:
    """Convert one reasoningContent block: round-trip, trace text, or drop.

    Only signed/redacted thinking round-trips; unsigned or foreign
    thinking becomes labeled trace text (warn), empty traces drop
    (blank text blocks are rejected downstream). Returns None when
    the block drops.
    """
    # LiteLLM precedent (BerriAI/litellm#9063, same crash class):
    # only signed/redacted thinking round-trips; unsigned or
    # foreign thinking becomes text, empty traces are dropped
    # (blank text blocks are themselves rejected downstream).
    payload = block["reasoningContent"] or {}
    text = (payload.get("reasoningText") or {}).get("text", "")
    signed = "signature" in (payload.get("reasoningText") or {})
    if reasoning_ok and (signed or "redactedContent" in payload):
        return copy.deepcopy(block)
    target_provider = _provider_of(normalize_model_ref(new_id))
    quiet_unsigned = (
        reasoning_ok and not signed and target_provider in ("openai", "meta")
    )
    if not quiet_unsigned:
        warnings.warn(
            f"Dropping reasoningContent for {new_id!r}; "
            + ("trace kept as text." if text.strip() else "trace dropped."),
            stacklevel=3,
        )
    if text.strip():
        return {"text": f"{TRACE_LABEL}\n{text}"}
    return None


def _migrate_trace_block(block: dict[str, Any]) -> dict[str, Any]:
    """Migrate a retired trace label to the current one (heal on switch)."""
    migrated = copy.deepcopy(block)
    for legacy in _LEGACY_TRACE_LABELS:
        if migrated["text"].startswith(legacy):
            migrated["text"] = TRACE_LABEL + migrated["text"][len(legacy) :]
            break
    return migrated


def _media_placeholder_block(block: dict[str, Any]) -> dict[str, Any]:
    """Placeholder text for an image/video block on a media-less target."""
    kind = "image" if "image" in block else "video"
    payload = block.get(kind, {})
    media_format = payload.get("format", "unknown")
    data = payload.get("source", {}).get("bytes", b"")
    size = len(data) if data else 0
    return {"text": f"[{kind}: {media_format}, {size} bytes]"}


def _convert_summary_block(block: dict[str, Any], new_id: str) -> dict[str, Any] | None:
    """Keep Anthropic SummaryBlock verbatim only on Anthropic targets."""
    payload = block.get("summary")
    if not isinstance(payload, dict):
        return None
    target_provider = _provider_of(normalize_model_ref(new_id))
    source_provider = payload.get("provider")
    if target_provider == "anthropic" and source_provider in (None, "anthropic"):
        return copy.deepcopy(block)
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return {"text": f"{SUMMARY_LABEL}\n{text}"}
    return None


def _convert_block(
    block: dict[str, Any], new_id: str, reasoning_ok: bool, media_ok: bool
) -> dict[str, Any] | None:
    """Convert one ContentBlock across providers, returning None to drop."""
    if "reasoningContent" in block:
        return _convert_reasoning_block(block, new_id, reasoning_ok)
    if "summary" in block:
        return _convert_summary_block(block, new_id)
    if isinstance(block.get("text"), str) and block["text"].startswith(
        _LEGACY_TRACE_LABELS
    ):
        return _migrate_trace_block(block)
    if "toolUse" in block:
        return _convert_tool_use_block(block, reasoning_ok)
    if ("image" in block or "video" in block) and not media_ok:
        return _media_placeholder_block(block)
    return copy.deepcopy(block)


def convert_history(
    messages: list[dict[str, Any]], old_id: str, new_id: str
) -> list[dict[str, Any]]:
    """Convert SDK ContentBlocks from the old model id to the new one.

    - reasoningContent round-trips only for harness-verified thinking
      targets sharing BOTH source vendor and provider AND carrying a
      signature (or redactedContent); everything else becomes labeled
      trace text (``TRACE_LABEL`` + original; warn), with empty traces
      dropped.
    - Anthropic ``SummaryBlock`` keeps verbatim on Anthropic targets and
      becomes ``SUMMARY_LABEL`` text elsewhere.
    - toolUse/toolResult blocks stay byte-identical (adapter layer owns them).
    - Image/video blocks → placeholder text on media-less targets.
    - Retired trace labels migrate to the current label.
    """
    reasoning_ok = (
        supports_reasoning(new_id)
        and same_vendor(old_id, new_id)
        and same_provider(old_id, new_id)
    )
    media_ok = supports_media(new_id)
    converted: list[dict[str, Any]] = []
    for message in messages:
        new_message = {"role": message.get("role"), "content": []}
        for key, value in message.items():
            if key not in ("role", "content"):
                new_message[key] = copy.deepcopy(value)
        for block in message.get("content", []):
            converted_block = _convert_block(block, new_id, reasoning_ok, media_ok)
            if converted_block is not None:
                new_message["content"].append(converted_block)
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


CURATED_GEMINI_MODELS: tuple[str, ...] = (
    "google/gemini-2.5-pro",
    "google/gemini-2.5-flash",
    "google/gemini-2.5-flash-lite",
    "google/gemini-3.8-flash",
    "google/gemini-4-hydrogen",
    "google/gemini-4-neon",
    "google/gemini-4-argon",
    "google/gemini-4-carbon",
)
"""Static fallback Gemini choices offered only when Google creds exist."""


def _append_bedrock_profiles(
    client: Any, options: list[str], non_chat_ids: set[str]
) -> None:
    """Append chat-capable Bedrock inference profile ARNs fail-soft."""
    try:
        profiles = client.list_inference_profiles().get("inferenceProfileSummaries", [])
    except Exception:
        return  # profiles are additive; foundation models still count as online
    for entry in profiles:
        arn = entry.get("inferenceProfileArn")
        if not isinstance(arn, str) or not arn.strip() or _has_unsafe_model_chars(arn):
            continue
        refs = _profile_model_ids(entry)
        if refs and all(ref in non_chat_ids or _looks_non_chat(ref) for ref in refs):
            continue  # every referenced model is known non-chat
        options.append(arn)


def _discover_bedrock_models(region: str | None) -> tuple[list[str], bool]:
    """List live Bedrock ON_DEMAND chat models + inference profiles fail-soft."""
    try:
        import boto3  # lazy: AWS-optional, never a hard dependency

        client_kwargs: dict[str, Any] = {}
        if region is not None:
            client_kwargs["region_name"] = region
        try:
            from botocore.config import Config

            client_kwargs["config"] = Config(
                connect_timeout=5, read_timeout=5, retries={"max_attempts": 0}
            )
        except ImportError:
            pass
        client = boto3.client("bedrock", **client_kwargs)
        summaries = client.list_foundation_models().get("modelSummaries", [])
        options: list[str] = []
        non_chat_ids: set[str] = set()
        for entry in summaries:
            model_id = entry.get("modelId")
            if (
                not isinstance(model_id, str)
                or not model_id.strip()
                or _has_unsafe_model_chars(model_id)
            ):
                continue
            if _is_chat_model(entry):
                if "ON_DEMAND" in entry.get("inferenceTypesSupported", []):
                    options.append(model_id)
            else:
                # Denylist learns every non-chat model, including profile-only
                # ones, so their inference profiles drop instead of leaking.
                non_chat_ids.add(model_id)
        _append_bedrock_profiles(client, options, non_chat_ids)
        return (list(dict.fromkeys(options)), True)
    except Exception:
        return ([], False)


def _is_google_chat_model(entry: Any) -> str | None:
    """Return short Gemini model id when usable for chat turns, else None."""
    raw = getattr(entry, "name", None)
    if not isinstance(raw, str):
        return None
    short = (
        raw.split("/models/", 1)[1]
        if "/models/" in raw
        else raw.removeprefix("models/")
    ).strip()
    if (
        not short
        or _has_unsafe_model_chars(short)
        or not short.lower().startswith("gemini-")
        or _looks_non_chat(short)
    ):
        return None
    actions = getattr(entry, "supported_actions", None)
    if actions is None:
        actions = getattr(entry, "supported_generation_methods", None)
    if actions is not None:
        action_list = list(actions)
        if action_list and "generateContent" not in action_list:
            return None
    return short


def _google_discovery_client_kwargs(genai_mod: Any) -> dict[str, Any]:
    """Build bounded-timeout, zero-retry kwargs for ``genai.Client``."""
    types_mod = getattr(genai_mod, "types", None)
    http_cls = getattr(types_mod, "HttpOptions", None) if types_mod else None
    retry_cls = getattr(types_mod, "HttpRetryOptions", None) if types_mod else None
    retry_val: Any = {"attempts": 1}
    if callable(retry_cls):
        try:
            retry_val = retry_cls(attempts=1)
        except Exception:
            pass
    if callable(http_cls):
        try:
            return {"http_options": http_cls(timeout=5_000, retry_options=retry_val)}
        except Exception:
            pass
    return {"http_options": {"timeout": 5_000, "retry_options": retry_val}}


def _discover_google_models() -> tuple[list[str], bool]:
    """List live Gemini chat models when Google credentials exist."""
    from strands_code_cli.entry.first_run import has_google_credentials

    if not has_google_credentials():
        return ([], False)
    try:
        from google import genai  # lazy: optional [gemini] extra

        try:
            client = genai.Client(**_google_discovery_client_kwargs(genai))
        except TypeError:
            client = genai.Client()
        found = [
            f"google/{short}"
            for entry in itertools.islice(client.models.list(), 500)
            if (short := _is_google_chat_model(entry)) is not None
        ]
        deduped = list(dict.fromkeys(found))
        if deduped:
            return (deduped, True)
    except Exception:
        pass
    return (list(CURATED_GEMINI_MODELS), False)


CURATED_OPENAI_MODELS: tuple[str, ...] = (
    "openai/gpt-6.2-sol",
    "openai/gpt-6.2-astra",
    "openai/gpt-6.1-sol",
    "openai/gpt-6.1-terra",
    "openai/gpt-6-astra",
    "openai/gpt-5.6-luna",
    "openai/gpt-5.4",
    "openai/o3",
    "openai/o4-mini",
)
"""Static fallback OpenAI choices offered only when OpenAI creds exist."""

CURATED_ANTHROPIC_MODELS: tuple[str, ...] = (
    "anthropic/claude-opus-5-5",
    "anthropic/claude-sonnet-5-5",
    "anthropic/claude-haiku-5-5",
    "anthropic/claude-fable-5-2",
    "anthropic/claude-opus-4-6",
    "anthropic/claude-sonnet-4-6",
)
"""Static fallback Anthropic choices offered only when Anthropic creds exist."""

CURATED_META_MODELS: tuple[str, ...] = (
    "meta/muse-spark-1.3-contributor",
    "meta/muse-spark-1.3",
    "meta/muse-wonder-1.0",
    "meta/muse-ember-1.0",
)
"""Static fallback Meta Model API choices offered only when Meta creds exist."""

_META_NON_CHAT_TOKENS: tuple[str, ...] = (
    "image",
    "voice",
    "transcribe",
    "audio",
    "sam-",
    "embed",
    "tts",
    "video",
    "moderation",
)

_OPENAI_NON_CHAT_TOKENS: tuple[str, ...] = (
    "embed",
    "rerank",
    "whisper",
    "tts",
    "audio",
    "transcribe",
    "realtime",
    "dall-e",
    "gpt-image",
    "sora",
    "moderation",
    "davinci",
    "babbage",
    "omni-",
    "instruct",
    "diarize",
)


def _is_openai_chat_model(model_id: str) -> bool:
    """True for Responses-capable OpenAI chat/reasoning model ids."""
    if not isinstance(model_id, str):
        return False
    stripped = model_id.strip()
    if not stripped or _has_unsafe_model_chars(stripped):
        return False
    lowered = stripped.lower()
    if any(token in lowered for token in _OPENAI_NON_CHAT_TOKENS):
        return False
    return lowered in ("o1", "o3") or lowered.startswith(
        ("gpt-", "chatgpt-", "o1-", "o3-", "o4-")
    )


def _scoped_discovery_base_url(provider: str) -> str | None:
    """Return persisted or env custom endpoint base URL scoped to ``provider``."""
    from strands_code_cli.entry.first_run import openai_base_url
    from strands_code_cli.entry.provider_config import ProviderConfig

    try:
        cfg = ProviderConfig.load()
        if cfg.base_url:
            owner = (
                provider_of(normalize_model_ref(cfg.model), unwrap_litellm=True)
                if cfg.model
                else None
            )
            scoped = scoped_base_url(cfg.base_url, owner, f"{provider}/_")
            if scoped:
                return scoped.rstrip("/")
    except ValueError:
        pass
    if provider == "openai":
        try:
            return openai_base_url()
        except ValueError:
            return None
    return None


def _discover_openai_models() -> tuple[list[str], bool]:
    """List live OpenAI chat/reasoning models when OpenAI credentials exist."""
    from strands_code_cli.entry.first_run import has_openai_credentials

    has_creds = has_openai_credentials()
    custom_url = _scoped_discovery_base_url("openai")
    if not has_creds and not custom_url:
        return ([], False)
    try:
        import openai  # lazy: optional [openai] extra

        client_kw: dict[str, Any] = {"timeout": 5.0, "max_retries": 0}
        if custom_url:
            client_kw["base_url"] = custom_url
            if not has_creds:
                client_kw["api_key"] = "not-required"
        client = openai.OpenAI(**client_kw)
        found = [
            f"openai/{item.id.strip()}"
            for item in client.models.list()
            if _is_openai_chat_model(getattr(item, "id", ""))
        ]
        deduped = list(dict.fromkeys(found))
        if deduped:
            return (deduped, True)
    except Exception:
        pass
    return (list(CURATED_OPENAI_MODELS), False)


def _serialize_capabilities(raw_caps: Any) -> dict[str, Any] | None:
    """Convert Pydantic or dict capabilities to JSON-safe dict."""
    if isinstance(raw_caps, dict):
        return dict(raw_caps)
    dump = getattr(raw_caps, "model_dump", None)
    if callable(dump):
        try:
            dumped = dump(mode="json")
            return dumped if isinstance(dumped, dict) else None
        except Exception:
            return None
    return None


def _extract_anthropic_model_meta(item: Any) -> dict[str, Any] | None:
    """Extract JSON-safe Anthropic /v1/models metadata from one SDK item."""
    raw_id = getattr(item, "id", None)
    if not isinstance(raw_id, str):
        return None
    stripped = raw_id.strip()
    if not stripped or _has_unsafe_model_chars(stripped):
        return None
    meta: dict[str, Any] = {"id": stripped}
    for field in ("max_input_tokens", "max_tokens", "line"):
        val = getattr(item, field, None)
        if val is not None:
            meta[field] = val
    caps = _serialize_capabilities(getattr(item, "capabilities", None))
    if caps is not None:
        meta["capabilities"] = caps
    retires = getattr(item, "retires_at", None)
    if hasattr(retires, "isoformat"):
        meta["retires_at"] = retires.isoformat()
    elif isinstance(retires, str) and retires.strip():
        meta["retires_at"] = retires.strip()
    return meta


def _discover_anthropic_models() -> tuple[list[str], bool]:
    """List live Anthropic models (caching metadata for 24h) when keyed."""
    from strands_code_cli.entry.first_run import has_anthropic_credentials

    has_creds = has_anthropic_credentials()
    custom_url = _scoped_discovery_base_url("anthropic")
    if not has_creds and not custom_url:
        return ([], False)
    try:
        import anthropic  # lazy: optional [anthropic] extra

        import strands_code_cli.cost.live_pricing as live_pricing

        client_kw: dict[str, Any] = {"timeout": 5.0, "max_retries": 0}
        if custom_url:
            client_kw["base_url"] = custom_url
            if not has_creds:
                client_kw["api_key"] = "not-required"
        client = anthropic.Anthropic(**client_kw)
        metas: list[dict[str, Any]] = []
        found: list[str] = []
        for item in client.models.list():
            meta = _extract_anthropic_model_meta(item)
            if meta is None:
                continue
            metas.append(meta)
            found.append(f"anthropic/{meta['id']}")
        deduped = list(dict.fromkeys(found))
        if deduped:
            live_pricing.store_anthropic_models(metas)
            return (deduped, True)
    except Exception:
        pass
    return (list(CURATED_ANTHROPIC_MODELS), False)


def _has_unsafe_model_chars(value: str) -> bool:
    """True when value contains whitespace, C0/C1 controls, or Bidi/format chars."""
    return any(ch.isspace() or unicodedata.category(ch) in ("Cc", "Cf") for ch in value)


def _meta_openai_client_args(
    endpoint: str,
    api_key: str | None,
    *,
    has_explicit_base_url: bool = False,
    openai_mod: Any = None,
) -> dict[str, Any]:
    """Build isolated OpenAI client args that block OPENAI_* env fallbacks."""
    effective_key = (
        api_key if api_key else ("not-required" if has_explicit_base_url else "")
    )
    args: dict[str, Any] = {
        "base_url": endpoint,
        "api_key": effective_key,
        "admin_api_key": "",
        "organization": "",
        "project": "",
        "webhook_secret": "",
    }
    omit = getattr(openai_mod, "omit", None)
    if omit is not None:
        args["default_headers"] = {
            "OpenAI-Organization": omit,
            "OpenAI-Project": omit,
        }
    return args


def _is_meta_chat_model(model_id: str) -> bool:
    """True for Responses-capable Meta Muse chat/reasoning model ids."""
    if not isinstance(model_id, str):
        return False
    stripped = model_id.strip()
    if not stripped or _has_unsafe_model_chars(stripped):
        return False
    lowered = stripped.lower()
    if any(token in lowered for token in _META_NON_CHAT_TOKENS):
        return False
    return lowered.startswith("muse-")


def _discover_meta_models() -> tuple[list[str], bool]:
    """List live Meta Muse models from api.meta.ai/v1 when Meta credentials exist."""
    from strands_code_cli.entry.first_run import (
        has_meta_credentials,
        meta_api_key,
        meta_base_url,
    )

    has_creds = has_meta_credentials()
    custom_url = _scoped_discovery_base_url("meta")
    if not has_creds and not custom_url:
        return ([], False)
    try:
        import openai  # lazy: optional [meta] / [openai] extra

        endpoint = custom_url or meta_base_url()
        client = openai.OpenAI(
            **_meta_openai_client_args(
                endpoint,
                meta_api_key(),
                has_explicit_base_url=custom_url is not None,
                openai_mod=openai,
            ),
            timeout=5.0,
            max_retries=0,
        )
        found = [
            f"meta/{item.id.strip()}"
            for item in client.models.list()
            if _is_meta_chat_model(getattr(item, "id", ""))
        ]
        deduped = list(dict.fromkeys(found))
        if deduped:
            return (deduped, True)
    except Exception:
        pass
    return (list(CURATED_META_MODELS), False)


def discover_models(
    region: str | None = None, configured: list[str] | None = None
) -> tuple[list[str], bool]:
    """List available chat model ids across configured/credentialed providers.

    Lazy imports keep AWS, Google, OpenAI, Anthropic, and Meta SDKs optional.
    Credentialed providers query live catalogs (or curated fallbacks
    offline); unkeyed providers never clutter another provider's picker.

    Args:
        region: Bedrock region (None -> boto3 default chain).
        configured: Model strings to offer when discovery is offline.

    Returns:
        ``(options, offline)`` where offline is True when no live catalog
        call succeeded.
    """
    bedrock_opts, bedrock_online = _discover_bedrock_models(region)
    google_opts, google_online = _discover_google_models()
    openai_opts, openai_online = _discover_openai_models()
    anthropic_opts, anthropic_online = _discover_anthropic_models()
    meta_opts, meta_online = _discover_meta_models()
    keyed_opts = google_opts + openai_opts + anthropic_opts + meta_opts
    if (
        bedrock_online
        or google_online
        or openai_online
        or anthropic_online
        or meta_online
    ):
        return (list(dict.fromkeys(bedrock_opts + keyed_opts)), False)
    fallback = list(configured) if configured else []
    return (list(dict.fromkeys(fallback + keyed_opts)), True)


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
        if tail.lower().startswith(_OPENROUTER_PREFIX):
            # Aggregator see-through: litellm/openrouter/qwen/qwen3-32b
            # groups and matches rules as qwen/qwen3-32b.
            tail = tail[len(_OPENROUTER_PREFIX) :]
    else:
        tail = entry
    low_tail = tail.lower()
    for prefix in _ROUTE_PREFIXES:
        if low_tail.startswith(prefix) and "." in tail[len(prefix) :]:
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


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def route_label(route: str) -> str:
    """Short picker label for a route; the value stays the verbatim string.

    ``arn:aws:bedrock:us-west-2:123:inference-profile/global.foo`` becomes
    ``profile global.foo (us-west-2)``. Cached Anthropic retirements
    append `` (retires YYYY-MM-DD)``. Non-ARN entries otherwise display
    verbatim.
    """
    if route.startswith("arn:"):
        parts = route.split(":")
        region = parts[3] if len(parts) > 4 else "?"
        return f"profile {route.rsplit('/', 1)[-1]} ({region})"
    try:
        import strands_code_cli.cost.live_pricing as live_pricing

        entry = live_pricing.anthropic_model_entry(route)
        retires = entry.get("retires_at") if entry else None
        if isinstance(retires, str):
            match = _ISO_DATE_RE.match(retires.strip())
            if match is not None:
                return f"{route} (retires {match.group(0)})"
    except Exception:
        pass
    return route


_COMPOUND_FAMILIES = (("gpt", "oss"),)
_PURE_VENDOR_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


def _infer_bare_vendor(base: str) -> tuple[str, str] | None:
    """Infer ``(vendor, rest)`` for bare provider-stripped catalog ids."""
    lowered = base.lower()
    if lowered == "gemini" or lowered.startswith("gemini-"):
        return ("google", base)
    if lowered.startswith("claude-"):
        return ("anthropic", base)
    if lowered.startswith("gpt-"):
        return ("openai", base)
    if lowered in ("o1", "o3") or lowered.startswith(("o1-", "o3-", "o4-")):
        return ("openai", base)
    if lowered.startswith("muse-"):
        return ("meta", base)
    return None


def _vendor_family(base: str) -> tuple[str, str]:
    """Split a base model key into ``(vendor, family)``.

    Vendor is the first dot segment (``anthropic``) when pure alphanumeric;
    family is the first dash token of the remainder (``claude``, ``nova``,
    ``gemma``), except known compound families (``gpt-oss`` vs ``gpt``)
    which keep two tokens. Bare ``gemini-*``, ``claude-*``, ``gpt-*``, and
    ``o1``/``o3``/``o4-*`` catalog ids infer their vendor cleanly while
    unknown decimal-dotted ids stay grouped under themselves.
    """
    if "/" in base:
        vendor, _, rest = base.partition("/")
    else:
        prefix, dot, rest = base.partition(".")
        if dot and _PURE_VENDOR_RE.fullmatch(prefix):
            vendor = prefix
        else:
            inferred = _infer_bare_vendor(base)
            if inferred is None:
                return (base, base)
            vendor, rest = inferred
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
    messages: list[dict[str, Any]], new_id: str, *, model: Any = None
) -> tuple[bool, float | None, int]:
    """Estimate whether converted history fits the new model's window.

    Token estimate is the local char/4 heuristic over serialized text (cheap,
    offline; never the native CountTokens API). Unknown window → ``(True,
    None, tokens)``: convert, never force-compact on a guess (D-02).

    Args:
        messages: Converted history to measure.
        new_id: Target model id string.
        model: Optional live model instance for runtime window lookup.

    Returns:
        ``(fits, pct, tokens)`` with pct None when the window is unknown.
    """
    from strands_code_cli.cost.cost_context import estimate_messages_tokens, window_for

    tokens = estimate_messages_tokens(messages)
    window = window_for(new_id, model=model)
    if window is None:
        return (True, None, tokens)
    pct = tokens / window * 100.0
    return (pct < _CONVERT_FITS_PCT, pct, tokens)


def model_id_of(model: Any, fallback: str) -> str:
    """Best-effort model id string for replies and table lookups."""
    explicit_ref = getattr(model, "_strands_model_ref", None)
    if isinstance(explicit_ref, str) and explicit_ref:
        return explicit_ref
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


def configure_streaming_for_model(model_id: str, resolved: Any) -> Any:
    """Disable streaming on Bedrock models that reject streaming tool use (D-03)."""
    if not model_id or resolved is None:
        return resolved
    normalized = normalize_model_ref(model_id)
    if _provider_of(normalized) != "bedrock" or supports_streaming_tools(normalized):
        return resolved
    update = getattr(resolved, "update_config", None)
    if callable(update):
        try:
            update(streaming=False)
        except Exception:
            pass
    return resolved


def _read_model_config(resolved: Any) -> dict[str, Any] | None:
    """Best-effort read of the config mapping from get_config() or .config."""
    get_config = getattr(resolved, "get_config", None)
    config: Any = None
    if callable(get_config):
        try:
            config = get_config()
        except Exception:
            config = None
    if not isinstance(config, dict):
        config = getattr(resolved, "config", None)
    return config if isinstance(config, dict) else None


# Google GenAI 2.5 reasoning param (model-API key; never a spend cap).
_THINKING_LIMIT_KEY = "thinking_budget"


def _gemini_25_updates(config: dict[str, Any]) -> dict[str, Any]:
    """Build Gemini 2.5 compatibility config updates from current config."""
    updates: dict[str, Any] = {}
    params = config.get("params")
    if isinstance(params, dict):
        thinking = params.get("thinking_config")
        if isinstance(thinking, dict) and "thinking_level" in thinking:
            updated_thinking = dict(thinking)
            level = updated_thinking.pop("thinking_level")
            if _THINKING_LIMIT_KEY not in updated_thinking:
                low = str(level).strip().lower() if level is not None else ""
                updated_thinking[_THINKING_LIMIT_KEY] = (
                    0 if low in ("off", "none") else -1
                )
            updated_params = dict(params)
            updated_params["thinking_config"] = updated_thinking
            updates["params"] = updated_params
    if config.get("gemini_tools"):
        # Gemini 2.5 rejects combining built-in GoogleSearch with function_declarations.
        updates["gemini_tools"] = []
    return updates


def configure_gemini_for_model(model_id: str, resolved: Any) -> Any:
    """Apply Gemini 2.5 compatibility adjustments (thinking_config & gemini_tools).

    ``strands_harness.models._gemini()`` emits Gemini-3 ``thinking_level`` and
    built-in ``gemini_tools=[GoogleSearch()]`` unconditionally; Gemini 2.5
    rejects both when paired with tool declarations. Leaves Gemini 3+ and 4+
    untouched.
    """
    if not model_id or resolved is None:
        return resolved
    normalized = normalize_model_ref(model_id)
    is_google = _provider_of(normalized) == "google" or (
        "/" not in normalized and not normalized.startswith("arn:")
    )
    base_name = _base_key(normalized).lower().removeprefix("models/")
    if not is_google or not base_name.startswith("gemini-2.5"):
        return resolved
    config = _read_model_config(resolved)
    if config is None:
        return resolved
    updates = _gemini_25_updates(config)
    if not updates:
        return resolved
    update = getattr(resolved, "update_config", None)
    if callable(update):
        try:
            update(**updates)
        except Exception:
            pass
    return resolved


_OPENAI_NON_REASONING_EXACT_OR_DASH = (
    "o1-mini",
    "o1-preview",
    "gpt-4.5",
    "gpt-4o",
    "gpt-4.1",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5",
)


def _openai_family_tail(normalized: str) -> str | None:
    """Return lowercase OpenAI model tail for ``openai/`` or ``bedrock-mantle/openai.*``."""
    provider = _provider_of(normalized)
    tail = _base_key(normalized).lower()
    if provider == "openai":
        return tail
    if provider == "bedrock-mantle" and tail.startswith("openai."):
        return tail[len("openai.") :]
    return None


def _is_openai_non_reasoning(base_key: str) -> bool:
    """True for OpenAI chat models that reject Responses reasoning.effort."""
    if "chat-latest" in base_key or base_key.startswith("chatgpt-"):
        return True
    return any(
        base_key == prefix or base_key.startswith(f"{prefix}-")
        for prefix in _OPENAI_NON_REASONING_EXACT_OR_DASH
    )


def _has_dash_prefix(base_key: str, prefixes: tuple[str, ...]) -> bool:
    """Token-boundary prefix check for exact model id or ``<prefix>-*`` snapshots."""
    return any(
        base_key == prefix or base_key.startswith(f"{prefix}-") for prefix in prefixes
    )


def _openai_effort_spec(base_key: str) -> tuple[tuple[str, ...], bool] | None:
    """Return ``(supported_levels, supports_none)`` for OpenAI reasoning tails."""
    if base_key.endswith("-pro") or "-pro-" in base_key:
        if base_key.startswith(("gpt-5.2", "gpt-5.4", "gpt-5.5")):
            return (("medium", "high", "xhigh"), False)
        return (("medium", "high"), False)
    if "-codex" in base_key:
        if base_key.startswith(("gpt-5.2", "gpt-5.3", "gpt-5.4", "gpt-5.5")):
            return (("low", "medium", "high", "xhigh"), False)
        return (("low", "medium", "high"), False)
    if _has_dash_prefix(base_key, ("gpt-oss",)):
        return (("low", "medium", "high"), False)
    if _has_dash_prefix(base_key, ("o1", "o3")) or base_key.startswith("o4-"):
        return (("low", "medium", "high"), False)
    if _has_dash_prefix(base_key, ("gpt-5.1",)):
        return (("none", "low", "medium", "high"), True)
    if _has_dash_prefix(base_key, ("gpt-5.2", "gpt-5.4", "gpt-5.5")):
        return (("none", "low", "medium", "high", "xhigh"), True)
    if base_key == "gpt-5" or base_key.startswith(("gpt-5-", "gpt-5.0")):
        return (("minimal", "low", "medium", "high"), False)
    if base_key.startswith(("gpt-6-astra", "gpt-6.1-sol", "gpt-6.2-")):
        return (("low", "medium", "high", "xhigh"), False)
    return None


def openai_supported_efforts(model_id: str) -> tuple[str, ...] | None:
    """Return supported effort tuple for ``openai/`` or ``bedrock-mantle/openai.*`` models."""
    tail = _openai_family_tail(normalize_model_ref(model_id))
    if tail is None:
        return None
    if _is_openai_non_reasoning(tail):
        return ()
    spec = _openai_effort_spec(tail)
    return spec[0] if spec is not None else None


def _target_openai_effort(base_key: str, effort: str) -> str | None:
    """Return normalized effort for OpenAI model family, or '' to strip, None if unchanged."""
    low = effort.strip().lower()
    spec = _openai_effort_spec(base_key)
    if spec is None:
        if low in ("none", "off"):
            return ""
        if low == "max":
            return "high"
        return None
    levels, supports_none = spec
    if low == "off":
        return "none" if supports_none else ""
    if low == "none":
        return None if supports_none else ""
    if low in levels:
        return None
    if low == "max":
        return "xhigh" if "xhigh" in levels else "high"
    if low == "xhigh":
        return "high"
    if low == "minimal":
        return "low" if "low" in levels else "medium"
    if low == "low" and "low" not in levels:
        return "medium"
    return None


def _openai_reasoning_params(
    base_key: str, params: dict[str, Any]
) -> dict[str, Any] | None:
    """Build updated ``params`` without mutating shared dicts in place."""
    reasoning = params.get("reasoning")
    if not isinstance(reasoning, dict):
        return None
    if _is_openai_non_reasoning(base_key):
        return {k: v for k, v in params.items() if k != "reasoning"}
    effort = reasoning.get("effort")
    if not isinstance(effort, str):
        return None
    mapped = _target_openai_effort(base_key, effort)
    if mapped is None:
        return None
    if mapped == "":
        return {k: v for k, v in params.items() if k != "reasoning"}
    return {**params, "reasoning": {**reasoning, "effort": mapped}}


def configure_openai_for_model(model_id: str, resolved: Any) -> Any:
    """Apply OpenAI compatibility guards for non-reasoning and effort-subset models.

    # Upstream: strands-agents/harness-sdk#6522 (PR #6525) — retire openai/ portion once released
    Covers both ``openai/<model>`` and ``bedrock-mantle/openai.<model>`` while
    leaving non-OpenAI Mantle models (e.g. ``bedrock-mantle/google.gemma-4-*``)
    untouched.
    """
    if not model_id or resolved is None:
        return resolved
    normalized = normalize_model_ref(model_id)
    base_key = _openai_family_tail(normalized)
    if base_key is None:
        return resolved
    config = _read_model_config(resolved)
    if config is None:
        return resolved
    params = config.get("params")
    if not isinstance(params, dict):
        return resolved
    updated_params = _openai_reasoning_params(base_key, params)
    if updated_params is None:
        return resolved
    update = getattr(resolved, "update_config", None)
    if callable(update):
        try:
            update(params=updated_params)
        except Exception:
            pass
    return resolved


_META_EFFORT_LEVELS = frozenset({"minimal", "low", "medium", "high", "xhigh", "max"})


def upstream_supports_meta() -> bool:
    """Return True once strands-harness natively registers the ``meta`` provider."""
    try:
        import strands_harness.models as harness_models
    except ImportError:
        return False
    return "meta" in getattr(harness_models, "_PROVIDERS", {})


def _normalize_meta_effort(effort: str | None) -> str | None:
    """Map harness effort onto api.meta.ai/v1 supported values (None omits reasoning)."""
    if effort is None:
        return "high"
    low = effort.strip().lower()
    if low == "auto":
        return "high"
    if low in ("none", "off"):
        return None
    return low if low in _META_EFFORT_LEVELS else "high"


def _meta_model_info() -> Any:
    """ModelInfo with automatic caching and 1M Muse window (no cache_points)."""
    from strands.models._model_info import ModelCapabilities, ModelInfo, ModelLimits

    return ModelInfo(
        capabilities=ModelCapabilities(prompt_caching="auto"),
        limits=ModelLimits(
            context_window=1_048_576,
            max_output_tokens=131_072,
        ),
    )


def build_meta_model(
    model_ref: str,
    *,
    effort: str | None = None,
    web_search: bool = True,
    caching: bool = True,
    base_url: str | None = None,
) -> Any:
    """Build a retireable OpenAIResponsesModel targeting Meta Model API."""
    import openai  # lazy: optional [meta] / [openai] extra
    from strands.models import CacheConfig
    from strands.models.openai_responses import OpenAIResponsesModel

    from strands_code_cli.entry.first_run import meta_api_key, meta_base_url
    from strands_code_cli.entry.provider_config import _validate_base_url

    normalized = normalize_model_ref(model_ref)
    provider, _, tail = normalized.partition("/")
    if provider.lower() != "meta" or not tail.strip():
        raise ValueError(f"Expected meta/<model>, got {model_ref!r}")
    tail = tail.strip()
    if _has_unsafe_model_chars(tail):
        raise ValueError(f"Invalid Meta model id {model_ref!r}")
    if base_url is not None:
        _validate_base_url(base_url)
        endpoint = base_url.rstrip("/")
    else:
        endpoint = meta_base_url()
    client_args = _meta_openai_client_args(
        endpoint,
        meta_api_key(),
        has_explicit_base_url=base_url is not None,
        openai_mod=openai,
    )
    params: dict[str, Any] = {}
    mapped_effort = _normalize_meta_effort(effort)
    if mapped_effort is not None:
        params["reasoning"] = {"effort": mapped_effort}
    if web_search:
        params["tools"] = [{"type": "web_search"}]
    extra: dict[str, Any] = {"model_info": _meta_model_info()}
    if caching:
        # Use CacheConfig() without strategy='auto' to avoid UserWarning when prompt_caching='auto'.
        extra["cache_config"] = CacheConfig()
    if params:
        extra["params"] = params
    resolved = OpenAIResponsesModel(client_args=client_args, model_id=tail, **extra)
    resolved._strands_model_ref = f"meta/{tail}"
    return resolved


def _has_reasoning(messages: list[dict[str, Any]]) -> bool:
    """True when any block carries reasoningContent, SummaryBlock, or signature."""
    return any(
        "reasoningContent" in block
        or "summary" in block
        or (
            isinstance(block.get("toolUse"), dict)
            and "reasoningSignature" in block["toolUse"]
        )
        for msg in messages
        for block in msg.get("content", [])
    )


def _resolve_resume_source(
    messages: list[dict[str, Any]], rich: Any, prior_model: str | None
) -> tuple[str, bool]:
    """Return ``(source_model_id, stale_rich)`` for resumed history checks."""
    if (
        isinstance(prior_model, str)
        and prior_model.strip()
        and prior_model != "__resumed__"
    ):
        return (normalize_model_ref(prior_model.strip()), False)
    rich_id = getattr(rich, "model_id", None)
    if isinstance(rich_id, str) and rich_id.strip() and rich_id != "__resumed__":
        if getattr(rich, "messages", None) is not None:
            if getattr(rich, "length", None) == len(messages) and getattr(
                rich, "prefix_hash", None
            ) == canonical_prefix_hash(messages):
                return (normalize_model_ref(rich_id.strip()), False)
            return ("__resumed__", True)
        return (normalize_model_ref(rich_id.strip()), False)
    return ("__resumed__", False)


def _needs_bedrock_resume_conversion(
    messages: list[dict[str, Any]], source_id: str, stale_rich: bool
) -> bool:
    """True when Bedrock resume must convert SummaryBlocks or foreign thinking."""
    if stale_rich:
        return True
    has_non_bedrock_source = (
        source_id != "__resumed__" and _provider_of(source_id) != "bedrock"
    )
    for msg in messages:
        for block in msg.get("content", []):
            if "summary" in block:
                return True
            if (
                isinstance(block.get("toolUse"), dict)
                and "reasoningSignature" in block["toolUse"]
            ):
                return True
            if has_non_bedrock_source and "reasoningContent" in block:
                return True
    return False


def prepare_resumed_history(
    agent: Any,
    current_model: str,
    rich: Any = None,
    stash_path: Path | None = None,
    *,
    prior_model: str | None = None,
) -> bool:
    """Normalize persisted session history on launch for the opening model (D-04).

    Media-capable Bedrock targets leave ``agent.messages`` untouched when
    history originates on Bedrock so upstream ``#5166`` / ``drop_block``
    strip ``reasoningContent`` dynamically on the wire without losing
    snapshot traces. Non-Bedrock targets, media-less Bedrock targets,
    and histories carrying Anthropic ``SummaryBlock``s, Gemini signatures,
    or known non-Bedrock thinking convert in place and preserve raw
    traces into ``rich``. Same-provider Anthropic/Gemini resumes with
    known matching ``prior_model`` keep signed thinking intact.

    Returns:
        ``True`` if ``agent.messages`` was converted in place, else ``False``.
    """
    messages = getattr(agent, "messages", None)
    if not messages:
        return False
    target = normalize_model_ref(current_model)
    old_id, stale_rich = _resolve_resume_source(messages, rich, prior_model)
    if (
        _provider_of(target) == "bedrock"
        and supports_media(target)
        and not _needs_bedrock_resume_conversion(messages, old_id, stale_rich)
    ):
        return False
    source = list(messages)
    converted = convert_history(source, old_id, target)
    if converted == source:
        return False
    if (
        rich is not None
        and getattr(rich, "messages", None) is None
        and _has_reasoning(source)
    ):
        rich.messages = copy.deepcopy(source)
        rich.model_id = (
            old_id if old_id != "__resumed__" else (rich.model_id or "__resumed__")
        )
        rich.length = len(source)
        rich.prefix_hash = canonical_prefix_hash(source)
        if stash_path is not None:
            rich.save(stash_path)
    del agent.messages[:]
    agent.messages.extend(converted)
    return True


def scoped_base_url(
    base_url: str | None,
    owner_provider: str | None,
    target_model: str | None,
) -> str | None:
    """Return ``base_url`` only when ``target_model`` matches ``owner_provider``."""
    if not base_url:
        return None
    if not owner_provider or not target_model:
        return base_url
    norm = normalize_model_ref(target_model)
    target_prov = (
        provider_of(norm, unwrap_litellm=False)
        if owner_provider == "litellm"
        else provider_of(norm, unwrap_litellm=True)
    )
    return base_url if target_prov == owner_provider else None


def _configure_openai_or_meta_base_url(
    provider: str, resolved: Any, cleaned: str
) -> None:
    if getattr(resolved, "_bedrock_mantle_config", None) is not None:
        return
    client_args = getattr(resolved, "client_args", None)
    if not isinstance(client_args, dict):
        return
    if provider == "meta" or not client_args.get("base_url"):
        client_args["base_url"] = cleaned
    if provider == "openai":
        from strands_code_cli.entry.first_run import has_openai_credentials

        if not has_openai_credentials() and not client_args.get("api_key"):
            client_args["api_key"] = "not-required"
    elif provider == "litellm":
        from strands_code_cli.entry.first_run import has_litellm_credentials

        if not has_litellm_credentials() and not client_args.get("api_key"):
            client_args["api_key"] = "not-required"


def _configure_anthropic_base_url(resolved: Any, cleaned: str) -> None:
    client = getattr(resolved, "client", None)
    cls_name = type(client).__name__ if client is not None else ""
    if (
        client is None
        or not hasattr(client, "base_url")
        or "Bedrock" in cls_name
        or "Vertex" in cls_name
    ):
        return
    from strands_code_cli.entry.first_run import has_anthropic_credentials

    try:
        client.base_url = cleaned
        if not has_anthropic_credentials() and not getattr(client, "api_key", None):
            client.api_key = "not-required"
    except Exception:
        pass


def configure_base_url_for_model(
    model_id: str,
    resolved: Any,
    *,
    base_url: str | None = None,
) -> Any:
    """Post-apply a persisted ProviderConfig.base_url without losing harness goodies."""
    if not base_url or not model_id or resolved is None:
        return resolved
    from strands_code_cli.entry.provider_config import _validate_base_url

    _validate_base_url(base_url)
    cleaned = base_url.rstrip("/")
    provider = _provider_of(normalize_model_ref(model_id))
    if provider in ("openai", "meta", "litellm"):
        _configure_openai_or_meta_base_url(provider, resolved, cleaned)
    elif provider == "anthropic":
        _configure_anthropic_base_url(resolved, cleaned)
    return resolved


def _build_openai_chat_model(normalized: str, base_url: str) -> Any:
    """Build legacy Chat Completions OpenAIModel for custom endpoints."""
    from strands.models.openai import OpenAIModel

    from strands_code_cli.entry.first_run import (
        has_litellm_credentials,
        has_openai_credentials,
    )
    from strands_code_cli.entry.provider_config import _validate_base_url

    _validate_base_url(base_url)
    client_args: dict[str, Any] = {"base_url": base_url.rstrip("/")}
    provider = _provider_of(normalized)
    if provider == "litellm":
        if not has_litellm_credentials():
            client_args["api_key"] = "not-required"
        chat_id = normalized
    else:
        if not has_openai_credentials():
            client_args["api_key"] = "not-required"
        chat_id = normalized.split("/", 1)[1]
    resolved = OpenAIModel(model_id=chat_id, client_args=client_args)
    resolved._strands_model_ref = normalized
    return resolved


def _stamp_model_ref(model: Any, ref: str) -> Any:
    """Attach canonical non-Bedrock ``provider/name`` ref for prefix-preserving lookups."""
    if (
        model is not None
        and isinstance(ref, str)
        and ref
        and _provider_of(ref) != "bedrock"
    ):
        try:
            model._strands_model_ref = ref
        except (AttributeError, TypeError):
            pass
    return model


def _prepare_harness_effort(normalized: str, effort: str | None) -> str | None:
    """Normalize/clamp effort into a valid harness Effort before calling resolve_model()."""
    # Upstream: strands-agents/harness-sdk#6522 (PR #6525) — retire openai/ portion once released
    if effort is None:
        return None
    low = effort.strip().lower()
    if low == "none":
        low = "off"
    base_lower = _openai_family_tail(normalized)
    if base_lower is None:
        return low
    if _is_openai_non_reasoning(base_lower):
        return None
    mapped = _target_openai_effort(base_lower, low)
    if mapped in ("", "none"):
        return "off"
    return mapped or low


def resolve_harness_model(
    model_ref: str,
    default: str | None = None,
    *,
    effort: str | None = None,
    base_url: str | None = None,
    web_search: bool = True,
    caching: bool = True,
    api_mode: str | None = None,
) -> Any:
    """Resolve a model preserving harness caching, web_search, and post-applied base_url."""
    import strands_harness.models as harness_models
    from strands_harness.models import resolve_model, supports_web_search

    normalized = normalize_model_ref(model_ref)
    provider = _provider_of(normalized)
    if provider == "meta" and not upstream_supports_meta():
        return _stamp_model_ref(
            build_meta_model(
                normalized,
                effort=effort,
                base_url=base_url,
                web_search=web_search,
                caching=caching,
            ),
            normalized,
        )
    eff_base_url = base_url
    if eff_base_url is None and provider == "openai" and api_mode == "chat":
        from strands_code_cli.entry.first_run import openai_base_url

        try:
            eff_base_url = openai_base_url()
        except ValueError:
            eff_base_url = None
    if eff_base_url and (
        provider == "litellm" or (provider == "openai" and api_mode == "chat")
    ):
        return _stamp_model_ref(
            _build_openai_chat_model(normalized, eff_base_url), normalized
        )
    target_default = default or normalized
    kwargs: dict[str, Any] = {
        "caching": bool(caching),
        "caching_explicit": not caching,
    }
    if web_search:
        try:
            has_search = bool(supports_web_search(normalized))
            kind_fn = getattr(harness_models, "_web_search_kind", None)
            if has_search and (
                not callable(kind_fn) or kind_fn(normalized) == "native"
            ):
                kwargs["web_search"] = True
        except Exception:
            pass
    effective_effort = _prepare_harness_effort(normalized, effort)
    if effective_effort is not None:
        kwargs["effort"] = effective_effort
    model = resolve_model(normalized, target_default, **kwargs)
    model = reported_cost.wrap_for_openrouter(normalized, model)
    model = configure_streaming_for_model(normalized, model)
    model = configure_gemini_for_model(normalized, model)
    model = configure_openai_for_model(normalized, model)
    model = configure_base_url_for_model(normalized, model, base_url=base_url)
    return _stamp_model_ref(model, normalized)


def _reconcile_web_search_tool(agent: Any, normalized: str) -> None:
    """Prevent duplicate/stale AgentCore web_search vs native search on switch."""
    reg_obj = getattr(agent, "tool_registry", None)
    reg = getattr(reg_obj, "registry", None)
    if not isinstance(reg, dict):
        return
    try:
        from strands_harness.models import _web_search_kind

        target_kind = (
            "native"
            if _provider_of(normalized) == "meta" and not upstream_supports_meta()
            else _web_search_kind(normalized)
        )
    except Exception:
        target_kind = "native" if _provider_of(normalized) == "meta" else None
    dyn = getattr(reg_obj, "dynamic_tools", None)
    if target_kind == "native" and "web_search" in reg:
        if getattr(agent, "_stashed_web_search_tool", None) is None:
            agent._stashed_web_search_tool = reg["web_search"]
        reg.pop("web_search", None)
        if isinstance(dyn, dict):
            dyn.pop("web_search", None)
    elif target_kind == "agentcore" and "web_search" not in reg:
        stashed = getattr(agent, "_stashed_web_search_tool", None)
        if stashed is not None:
            reg["web_search"] = stashed


def _web_search_unsupported(model: Any) -> bool:
    """True when ``create_harness`` rejects ``web_search=True`` for ``model``."""
    from strands.models import Model, ModelRouter

    if isinstance(model, (Model, ModelRouter)):
        return True
    try:
        from strands_harness.models import _web_search_kind

        return _web_search_kind(model) is None
    except Exception:
        return False


def _custom_web_fetch_model(
    target_model: Any,
    *,
    base_url: str | None = None,
    base_url_provider: str | None = None,
    api_mode: str | None = None,
) -> Any | None:
    """Resolve a dedicated ``web_fetch`` summarizer for Meta or custom-URL targets."""
    target_ref = (
        target_model
        if isinstance(target_model, str)
        else getattr(target_model, "_strands_model_ref", None)
    )
    if not isinstance(target_ref, str) or not target_ref:
        return None
    normalized = normalize_model_ref(target_ref)
    provider = _provider_of(normalized)
    scoped = scoped_base_url(base_url, base_url_provider, normalized)
    if scoped is None and provider == "openai" and api_mode == "chat":
        from strands_code_cli.entry.first_run import openai_base_url

        try:
            scoped = openai_base_url()
        except ValueError:
            scoped = None
    if provider != "meta" and not (
        scoped is not None and provider in ("openai", "anthropic", "litellm")
    ):
        return None
    try:
        wf_model = resolve_harness_model(
            normalized,
            effort="off",
            base_url=scoped,
            api_mode=api_mode if scoped is not None else None,
            web_search=False,
            caching=False,
        )
    except Exception:
        return None
    return None if isinstance(wf_model, str) else wf_model


def reconcile_delegate_builtin_tools(
    builtin_tools: Any,
    target_model: Any,
    *,
    base_url: str | None = None,
    base_url_provider: str | None = None,
    api_mode: str | None = None,
) -> Any:
    """Copy ``builtin_tools`` and reconcile ``web_search`` / ``web_fetch`` for target model."""
    if not isinstance(builtin_tools, Mapping):
        return builtin_tools
    updated = dict(builtin_tools)
    if updated.get("web_search") is True and _web_search_unsupported(target_model):
        updated["web_search"] = False
    wf_raw = updated.get("web_fetch")
    if wf_raw is False:
        return updated
    wf_enabled = wf_raw is not None or updated.get("*", True) is not False
    if not wf_enabled:
        return updated
    wf_cfg = (
        {k: v for k, v in wf_raw.items() if k != "model"}
        if isinstance(wf_raw, Mapping)
        else {}
    )
    custom_wf = _custom_web_fetch_model(
        target_model,
        base_url=base_url,
        base_url_provider=base_url_provider,
        api_mode=api_mode,
    )
    if custom_wf is not None:
        updated["web_fetch"] = {**wf_cfg, "model": custom_wf}
    elif isinstance(wf_raw, Mapping) and "model" in wf_raw:
        updated["web_fetch"] = wf_cfg if wf_cfg else True
    return updated


def apply_switch(
    agent: Any,
    new_string: str,
    default: str | None = None,
    *,
    effort: str | None = None,
    base_url: str | None = None,
    api_mode: str | None = None,
) -> tuple[Any, str]:
    """Resolve and in-place swap the agent's model (tracer-winning seam).

    Assigns ``agent.model`` directly; history stays in place (the caller runs
    :func:`convert_history` or compaction first). Unknown providers raise
    ValueError listing supported providers (resolve_model contract).

    Args:
        agent: Live session agent.
        new_string: ``"provider/name"`` selection (bare Bedrock ids allowed).
        default: Default model string when selection is empty.
        effort: Routed thinking level, forwarded to ``resolve_model``
            only when not None.
        base_url: Optional custom endpoint host override; defaults to
            ``getattr(agent, "_base_url", None)``.
        api_mode: Optional OpenAI endpoint mode override (``responses|chat``);
            defaults to ``getattr(agent, "_api_mode", None)`` when ``base_url``
            applies.

    Returns:
        ``(model, resolved_id)`` for replies and persistence.
    """
    normalized = normalize_model_ref(new_string)
    effective_base_url = (
        base_url
        if base_url is not None
        else scoped_base_url(
            getattr(agent, "_base_url", None),
            getattr(agent, "_base_url_provider", None),
            normalized,
        )
    )
    effective_api_mode = (
        api_mode
        if api_mode is not None
        else (
            getattr(agent, "_api_mode", None)
            if effective_base_url is not None
            else None
        )
    )
    model = resolve_harness_model(
        normalized,
        default,
        effort=effort,
        base_url=effective_base_url,
        api_mode=effective_api_mode,
    )
    agent.model = model
    _reconcile_web_search_tool(agent, normalized)
    return (model, model_id_of(model, normalized))
