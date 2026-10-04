"""Live price/window layers over the static almanac (MODEL-02).

Resolution is display-only and every layer fails soft to the next:

prices
    Bedrock Price List (24h disk cache, standard on-demand tier only)
    -> OpenRouter ``/models`` (24h disk cache, openrouter-routed ids only)
    -> LiteLLM bundled ``model_cost`` (when installed)
    -> static ``MODEL_PRICING``
windows
    OpenRouter ``context_length`` -> LiteLLM ``max_input_tokens``
    -> static ``MODEL_LIMITS`` (no AWS API exposes windows)

Nothing here ever raises to a caller: any failure (no boto3, no creds,
denied, unreachable, corrupt cache) yields None and the next layer is
tried. ``STRANDS_CODE_NO_LIVE_PRICING=1`` forces static-only resolution
(tests set this; see tests/conftest.py).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

CACHE_TTL_SECONDS = 24 * 3600
"""Disk-cache freshness for both live sources."""

FETCH_TIMEOUT_SECONDS = 15
"""Per-request network ceiling; turns never wait longer than this."""

_COOLDOWN_SECONDS = 10 * 60
"""In-process quiet period after a failed refresh (serve stale, don't spin)."""

_PRICING_ENDPOINT_REGION = "us-east-1"
"""Price List API exists only here, regardless of the queried region."""

_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
"""Public endpoint: per-model pricing + context_length, no key needed."""

_ROUTE_PREFIXES = ("global.", "us.", "eu.", "apac.", "au.", "jp.")
"""Cross-region routing prefixes (mirrors model_switch; routed ids skip live).

A routed id (``us.anthropic...``) pays cross-region pricing, not the base
on-demand records below, so it must NOT match them — it falls through to
LiteLLM (which prices routed forms) or the static table.
"""

_REGION_PREFIX_RE = re.compile(r"^[A-Z]{2,4}[0-9]?-")
_USAGE_RE = re.compile(r"^(?P<core>.+)-(?P<direction>input|output)-tokens(?P<tier>.*)$")
_STANDARD_TIERS = ("", "-standard")


def _live_disabled() -> bool:
    """Kill switch for every non-static layer (tests + offline determinism)."""
    return os.environ.get("STRANDS_CODE_NO_LIVE_PRICING", "0") not in ("", "0")


def live_disabled() -> bool:
    """Public read of the static-only kill switch (resolution gating)."""
    return _live_disabled()


def _cache_dir() -> Path:
    """Writable cache home (overridable for tests)."""
    override = os.environ.get("STRANDS_CODE_CACHE_DIR")
    if override:
        return Path(override)
    return Path.home() / ".cache" / "strands-code"


_cooldown_until: dict[str, float] = {}


def _in_cooldown(key: str) -> bool:
    return _cooldown_until.get(key, 0.0) > time.time()


def _note_failure(key: str) -> None:
    _cooldown_until[key] = time.time() + _COOLDOWN_SECONDS


def _reset_cooldowns() -> None:
    """Test hook: clear the in-process failure backoff."""
    _cooldown_until.clear()


def _read_cache(path: Path) -> dict[str, Any] | None:
    """Parsed cache payload, or None when missing/corrupt/wrong-shaped."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    """Best-effort cache store (never raises)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def normalize(text: str) -> str:
    """Lowercase alnum-only fold for fuzzy record matching."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def parse_usagetype(usagetype: str) -> tuple[str, str] | None:
    """Split a Price List usagetype into (core, direction), or None.

    Standard on-demand records end in exactly ``-input-tokens`` /
    ``-output-tokens`` (optionally ``-standard``); batch, priority, flex,
    cache, and cross-region variants are rejected. The ``inferenceType``
    / ``feature`` attributes are NOT reliable discriminators (a priority
    record carries ``feature='On-demand Inference'`` while batch records
    share ``inferenceType='Input tokens'``), so the usagetype suffix is
    the arbiter. A trailing ``-mantle`` host marker is stripped.
    """
    core = _REGION_PREFIX_RE.sub("", usagetype, count=1)
    match = _USAGE_RE.match(core.lower())
    if match is None:
        return None
    if match.group("tier") not in _STANDARD_TIERS:
        return None
    body = match.group("core")
    if body.endswith("-mantle"):
        body = body[: -len("-mantle")]
    if not body:
        return None
    return (body, match.group("direction"))


def _strip_version(text: str) -> str:
    """Drop Bedrock date/version suffixes (``-20240307``, ``-v1:0``)."""
    text = re.sub(r"-\d{8}(?![0-9])", "", text)
    text = re.sub(r"[-_]v\d+:\d+$", "", text)
    return text


def model_candidates(model_id: str) -> list[str]:
    """Normalized match forms, most specific first.

    Routed ids (``us.``/``global.``/...) yield only the full form so they
    never match base on-demand records — they pay cross-region prices
    and fall through to LiteLLM/static instead.
    """
    tail = model_id.rsplit("/", 1)[-1]
    lowered = tail.lower()
    for prefix in _ROUTE_PREFIXES:
        if lowered.startswith(prefix):
            return [normalize(tail)]
    forms = [tail]
    if "." in tail:
        novendor = tail.split(".", 1)[1]
        forms.append(novendor)
        forms.append(_strip_version(novendor))
    return [normalize(form) for form in forms]


def _unit_to_per_1m(unit: str) -> float | None:
    """Scale a price-unit amount to per-1M-tokens, or None when unknown."""
    lowered = unit.lower()
    if "1k" in lowered:
        return 1000.0
    if "1m" in lowered:
        return 1.0
    if "token" in lowered:
        return 1_000_000.0
    return None


def parse_price_record(item: dict[str, Any]) -> tuple[str, str, float] | None:
    """Reduce one Price List item to (core, direction, per-1M USD).

    The core keeps its raw (lowercased) shape for display; callers
    normalize for matching. Returns None for non-standard tiers,
    non-token units, and malformed items — the caller keeps scanning.
    """
    attributes = item.get("product", {}).get("attributes", {})
    if not isinstance(attributes, dict):
        return None
    usagetype = attributes.get("usagetype")
    if not isinstance(usagetype, str):
        return None
    parsed = parse_usagetype(usagetype)
    if parsed is None:
        return None
    core, direction = parsed
    terms = item.get("terms", {}).get("OnDemand", {})
    if not isinstance(terms, dict):
        return None
    for term in terms.values():
        dimensions = term.get("priceDimensions", {})
        if not isinstance(dimensions, dict):
            continue
        for dimension in dimensions.values():
            if not isinstance(dimension, dict):
                continue
            scale = _unit_to_per_1m(str(dimension.get("unit", "")))
            amount = dimension.get("pricePerUnit", {}).get("USD")
            if scale is None:
                continue
            try:
                return (core, direction, float(amount) * scale)
            except (TypeError, ValueError):
                continue
    return None


def fetch_bedrock_records(region: str) -> list[dict[str, Any]] | None:
    """Raw standard-tier token records for a region, or None on failure.

    Two direction-filtered queries (server-side cut only; the usagetype
    suffix stays the tier arbiter). Lazy boto3 import, tight timeouts.
    """
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        return None
    try:
        client = boto3.client(
            "pricing",
            region_name=_PRICING_ENDPOINT_REGION,
            config=Config(
                connect_timeout=5,
                read_timeout=FETCH_TIMEOUT_SECONDS,
                retries={"max_attempts": 1},
            ),
        )
        items: list[dict[str, Any]] = []
        for direction in ("Input tokens", "Output tokens"):
            token: str | None = None
            while True:
                kwargs: dict[str, Any] = {
                    "ServiceCode": "AmazonBedrock",
                    "Filters": [
                        {
                            "Type": "TERM_MATCH",
                            "Field": "regionCode",
                            "Value": region,
                        },
                        {
                            "Type": "TERM_MATCH",
                            "Field": "inferenceType",
                            "Value": direction,
                        },
                    ],
                    "MaxResults": 100,
                }
                if token:
                    kwargs["NextToken"] = token
                page = client.get_products(**kwargs)
                for raw in page.get("PriceList", []):
                    try:
                        items.append(json.loads(raw))
                    except ValueError:
                        continue
                token = page.get("NextToken")
                if not token:
                    break
        return items
    except Exception:
        return None


def _store_bedrock(region: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse records into the region cache payload and persist it."""
    prices: dict[str, dict[str, Any]] = {}
    publication: str | None = None
    for item in items:
        parsed = parse_price_record(item)
        if parsed is None:
            continue
        core, direction, per_1m = parsed
        slot = prices.setdefault(normalize(core), {"name": core})
        slot["in" if direction == "input" else "out"] = per_1m
        publication = publication or item.get("publicationDate")
    payload = {"fetched_at": time.time(), "publication": publication, "prices": prices}
    _write_cache(_cache_dir() / f"bedrock-pricing-{region}.json", payload)
    return payload


def _bedrock_cache(region: str) -> dict[str, Any] | None:
    """Parsed core map for a region: fresh cache, refresh, or stale cache."""
    if _live_disabled():
        return None
    key = f"bedrock:{region}"
    path = _cache_dir() / f"bedrock-pricing-{region}.json"
    payload = _read_cache(path)
    if payload is not None and time.time() - float(payload.get("fetched_at", 0)) < CACHE_TTL_SECONDS:
        return payload
    if _in_cooldown(key):
        return payload  # serve stale (or miss) without another attempt
    items = fetch_bedrock_records(region)
    if items is None:
        _note_failure(key)
        return payload
    return _store_bedrock(region, items)


def bedrock_live_price(
    model_id: str, region: str | None
) -> tuple[float, float, str] | None:
    """Standard on-demand (in, out) per-1M USD + provenance, else None."""
    if region is None or _live_disabled():
        return None
    cache = _bedrock_cache(region)
    if not cache:
        return None
    prices = cache.get("prices", {})
    if not isinstance(prices, dict):
        return None
    for candidate in model_candidates(model_id):
        slot = prices.get(candidate)
        if isinstance(slot, dict) and "in" in slot and "out" in slot:
            publication = cache.get("publication") or "undated"
            return (
                float(slot["in"]),
                float(slot["out"]),
                f"Bedrock live {region} (pub {publication})",
            )
    return None


def resolve_region(explicit: str | None = None) -> str | None:
    """Bedrock region for live pricing: explicit, boto3 chain, or env."""
    if explicit:
        return explicit
    for variable in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        value = os.environ.get(variable)
        if value:
            return value
    try:
        import boto3
    except ImportError:
        return None
    try:
        return boto3.Session().region_name
    except Exception:
        return None


def _openrouter_id(model_id: str) -> str | None:
    """OpenRouter model id for aggregator-routed refs, else None."""
    lowered = model_id.lower()
    for prefix in ("litellm/openrouter/", "openrouter/"):
        if lowered.startswith(prefix):
            return model_id[len(prefix) :]
    return None


def is_openrouter_id(model_id: str) -> bool:
    """True when the ref routes through OpenRouter (either prefix form)."""
    return _openrouter_id(model_id) is not None


def fetch_openrouter_models() -> list[dict[str, Any]] | None:
    """Raw ``/models`` payload (public, no key), or None on failure."""
    import urllib.request

    try:
        request = urllib.request.Request(
            _OPENROUTER_MODELS_URL, headers={"User-Agent": "strands-code"}
        )
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        models = payload.get("data", [])
        return models if isinstance(models, list) else None
    except Exception:
        return None


def _store_openrouter(models: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse a /models payload into the cache payload and persist it."""
    entries: dict[str, dict[str, float]] = {}
    for model in models:
        if not isinstance(model, dict):
            continue
        model_key = model.get("id")
        pricing = model.get("pricing", {})
        if not isinstance(model_key, str) or not isinstance(pricing, dict):
            continue
        try:
            entry: dict[str, float] = {
                "in": float(pricing.get("prompt", 0.0)) * 1_000_000,
                "out": float(pricing.get("completion", 0.0)) * 1_000_000,
            }
        except (TypeError, ValueError):
            continue
        window = model.get("context_length")
        if isinstance(window, (int, float)) and window > 0:
            entry["window"] = float(window)
        entries[model_key] = entry
    payload = {"fetched_at": time.time(), "models": entries}
    _write_cache(_cache_dir() / "openrouter-models.json", payload)
    return payload


def _openrouter_cache() -> dict[str, Any] | None:
    """Parsed id map: fresh cache, refresh, or stale cache."""
    if _live_disabled():
        return None
    key = "openrouter"
    path = _cache_dir() / "openrouter-models.json"
    payload = _read_cache(path)
    if payload is not None and time.time() - float(payload.get("fetched_at", 0)) < CACHE_TTL_SECONDS:
        return payload
    if _in_cooldown(key):
        return payload
    models = fetch_openrouter_models()
    if models is None:
        _note_failure(key)
        return payload
    return _store_openrouter(models)


def openrouter_entry(model_id: str) -> dict[str, float] | None:
    """Cached (in/out per-1M, window) for openrouter-routed ids, else None."""
    target = _openrouter_id(model_id)
    if target is None or _live_disabled():
        return None
    cache = _openrouter_cache()
    if not cache:
        return None
    models = cache.get("models", {})
    if not isinstance(models, dict):
        return None
    entry = models.get(target)
    return dict(entry) if isinstance(entry, dict) else None


def litellm_entry(model_id: str) -> dict[str, float] | None:
    """Bundled-model-cost (in/out per-1M, window) when installed, else None.

    Partial entries are fine — a price without a window (or vice versa)
    still merges with the other layers field by field.
    """
    try:
        import litellm
    except ImportError:
        return None
    table = getattr(litellm, "model_cost", None)
    if not isinstance(table, dict):
        return None
    # bedrock_mantle/ is LiteLLM's prefix for Bedrock-hosted third-party
    # models (31 keys across 7 vendors: openai, qwen, google, deepseek,
    # anthropic, moonshotai, xai) — the only layer pricing GPT-on-Bedrock.
    tail = model_id.rsplit("/", 1)[-1]
    keys = [model_id, f"bedrock/{model_id}", f"bedrock_mantle/{tail}"]
    target = _openrouter_id(model_id)
    if target is not None:
        keys.extend([target, f"openrouter/{target}", f"litellm/openrouter/{target}"])
    for key in keys:
        raw = table.get(key)
        if not isinstance(raw, dict):
            continue
        entry: dict[str, float] = {}
        try:
            if raw.get("input_cost_per_token") is not None:
                entry["in"] = float(raw["input_cost_per_token"]) * 1_000_000
            if raw.get("output_cost_per_token") is not None:
                entry["out"] = float(raw["output_cost_per_token"]) * 1_000_000
        except (TypeError, ValueError):
            continue
        window = raw.get("max_input_tokens")
        if isinstance(window, (int, float)) and window > 0:
            entry["window"] = float(window)
        if entry:
            return entry
    return None


def refresh_caches(region: str | None = None) -> dict[str, Any]:
    """Force-refetch both live sources, bypassing TTL and cooldown.

    Explicit user action (``/cost refresh``): failures are reported in
    the summary, never raised, and previously cached data is kept.
    """
    summary: dict[str, Any] = {}
    if _live_disabled():
        return {"disabled": True}
    resolved = region or resolve_region()
    if resolved is None:
        summary["bedrock"] = {"region": None, "error": "no region resolved"}
    else:
        items = fetch_bedrock_records(resolved)
        if items is None:
            summary["bedrock"] = {
                "region": resolved,
                "error": "fetch failed (no creds, denied, or unreachable)",
            }
        else:
            payload = _store_bedrock(resolved, items)
            _cooldown_until.pop(f"bedrock:{resolved}", None)
            summary["bedrock"] = {
                "region": resolved,
                "models": len(payload.get("prices", {})),
                "publication": payload.get("publication"),
            }
    models = fetch_openrouter_models()
    if models is None:
        summary["openrouter"] = {"error": "fetch failed (unreachable)"}
    else:
        payload = _store_openrouter(models)
        _cooldown_until.pop("openrouter", None)
        summary["openrouter"] = {"models": len(payload.get("models", {}))}
    return summary


def cached_tables(region: str | None = None) -> dict[str, Any]:
    """Cached payloads for inspection (no network, failures read as None)."""
    resolved = region or resolve_region()
    bedrock = None
    if resolved is not None:
        payload = _read_cache(_cache_dir() / f"bedrock-pricing-{resolved}.json")
        if isinstance(payload, dict):
            bedrock = payload
    openrouter = _read_cache(_cache_dir() / "openrouter-models.json")
    if not isinstance(openrouter, dict):
        openrouter = None
    return {"region": resolved, "bedrock": bedrock, "openrouter": openrouter}
