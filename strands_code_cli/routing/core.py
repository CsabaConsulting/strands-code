"""Per-ask model routing via a cheap decision model (MODEL-03).

A routing strategy (candidate model set + freeform directives, global or
repo file with repo winning whole-file) arms routing; without one the
CLI behaves exactly as before (D-01). Each configured ask routes
pre-turn at idle through an ordered engine registry — the OpenRouter
Decisions API first, the local Ollama System One daemon second,
hold-current last — and the pick applies through the existing switch
machinery. The model judges (typed probability tables); code gates
(threshold plus tie-margin) and computes. No heuristic ever picks a
model: every engine, validation, gate, or resolve failure holds the
current model with history byte-identical (D-08).
"""

from __future__ import annotations

import json  # noqa: F401 — kept for test & facade callers
import logging
import math
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import platformdirs
import yaml

from strands_code_cli.cost.cost_context import (
    cost_for,
    estimate_messages_tokens,
    price_for,
)
from strands_code_cli.model.model_switch import (
    normalize_model_ref,
    openai_supported_efforts,
    supports_reasoning,
)
from strands_code_cli.platform_io import atomic_write_text, refuse_symlink
from strands_code_cli.routing import transports as _transports
from strands_code_cli.routing.transports import (
    ASK_TRUNCATE_CHARS,
    DECISION_TIMEOUT_SECONDS,
    OLLAMA_DEFAULT_HOST,
    OLLAMA_TIMEOUT_SECONDS,
    TRUNCATION_MARKER,
    EngineResult,
    _is_loopback_host,
    ollama_base,
    ollama_headers,
    preflight_get,
    read_env_api_key,
    run_decisions_api_decision,
    run_llm_decision,
    run_ollama_decision,
    run_openrouter_decision,
    run_typesafe_decision,
    valid_base_url,
    valid_model_id,
)

DECISION_BODY_MAX_BYTES = _transports.DECISION_BODY_MAX_BYTES
OPENROUTER_DECISIONS_URL = _transports.OPENROUTER_DECISIONS_URL
TYPESAFE_DECISIONS_URL = _transports.TYPESAFE_DECISIONS_URL
DECISIONS_API_URL = _transports.DECISIONS_API_URL
DECISIONS_API_DEFAULT_MODEL = _transports.DECISIONS_API_DEFAULT_MODEL
TYPESAFE_INPUT_USD_PER_MTOK = _transports.TYPESAFE_INPUT_USD_PER_MTOK
OLLAMA_KEEP_ALIVE = _transports.OLLAMA_KEEP_ALIVE
OLLAMA_PREFLIGHT_TIMEOUT_SECONDS = _transports.OLLAMA_PREFLIGHT_TIMEOUT_SECONDS
_fit_decision_payload = _transports.fit_decision_payload
_transport_retryable_error = _transports.is_retryable_decision_error
_transport_failure_reason = _transports.failure_reason
_TRANSPORT_RETRYABLE_STATUS = _transports._RETRYABLE_STATUS

logger = logging.getLogger(__name__)

_STRATEGY_DIR_NAME = "strands-code"
_STRATEGY_FILE_NAME = "routing.yaml"
_REPO_STRATEGY_REL = Path(".agent") / "routing.yaml"

NATIVE_JEV_PIN = "jev-1.13.0"
"""Pinned native Jev id (full semver; the minor-only form 400s)."""

NATIVE_JEV_ALIAS = "jev-latest"
"""Explicit-opt-in native alias (a moving target; setup warns of drift)."""

_NATIVE_MODEL_IDS = frozenset({NATIVE_JEV_PIN, NATIVE_JEV_ALIAS})
"""Native model strings verified live (D-05 corrected)."""

DEFAULT_TIE_MARGIN = 0.04
"""Near-tie gap: top-two within this routes the cheaper one (D-14).

Probe-derived 2026-10-12 (``evals/routing-probe/baseline.json``):
max observed near-tie margin 0.03 (Jev 0.51-vs-0.48 split) plus one
0.01 grid step of headroom — the grid floor is Jev's 2-decimal
rounding granularity (Pitfall 2). Below every routed margin (0.34
min), so zero probe outcomes change; arms the tie-break for future
threshold-clearing near-ties.
"""

DEFAULT_CONFIDENCE_THRESHOLD = 0.62
"""Model gate: top-1 probability below this holds current (D-16).

Probe-derived 2026-10-12 (``evals/routing-probe/baseline.json``):
midpoint of the observed (0.51 wrong-catchable max, 0.73 correct
min) gap, with 0.11 margin each side. One shared value serves both
pinned engines — neither misfires in the dangerous direction.
Always compared against the pick's top-1 probability, never the
vendor confidence field (Pitfall 1).
"""

_RETRYABLE_STATUS = _TRANSPORT_RETRYABLE_STATUS
"""Decision-API codes worth one retry; every 4xx holds immediately."""

MAX_CANDIDATES = 26
"""Hard candidate cap: the binding ``choice`` option limit is 26."""

_TOP_LEVEL_KEYS = {
    "candidates",
    "directives",
    "engine",
    "quiet",
    "tie_margin",
    "confidence_threshold",
}
_CANDIDATE_KEYS = {"id", "tier", "note", "levels", "benchmarks", "criteria"}
_BENCHMARK_KEYS = {"swe_verified", "lmarena_coding", "aa_index", "pulled"}
_ENGINE_KEYS = {
    "decision_model",
    "local_model",
    "local_base_url",
    "order",
    "native_model",
    "decisions_api_model",
    "llm_model",
    "skip_notes",
}
_VALID_ORDER_ENGINES = ("native", "openrouter", "local", "decisions_api", "llm")
_ENGINE_STRING_KEYS = (
    "decision_model",
    "local_model",
    "local_base_url",
    "native_model",
    "decisions_api_model",
    "llm_model",
)
_ENGINE_MODEL_ID_KEYS = (
    "decision_model",
    "local_model",
    "native_model",
    "decisions_api_model",
    "llm_model",
)


@dataclass
class RoutingCandidate:
    """One routable model entry from the strategy file."""

    id: str
    tier: str | None = None
    note: str | None = None
    levels: list[str] | None = None
    benchmarks: dict[str, Any] | None = None
    criteria: str | None = None


@dataclass
class RoutingEngine:
    """Decision engine selection from the strategy file."""

    decision_model: str | None = None
    local_model: str | None = None
    local_base_url: str | None = None
    order: list[str] = field(default_factory=lambda: ["openrouter", "local"])
    native_model: str | None = None
    decisions_api_model: str | None = None
    llm_model: str | None = None
    skip_notes: bool = True


@dataclass
class RoutingStrategy:
    """Parsed strategy: candidates + directives + engine + gate knobs."""

    candidates: list[RoutingCandidate] = field(default_factory=list)
    directives: str = ""
    engine: RoutingEngine = field(default_factory=RoutingEngine)
    quiet: bool = False
    tie_margin: float = DEFAULT_TIE_MARGIN
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    source: Path | None = None


@dataclass(frozen=True)
class RoutingPick:
    """One gated decision: model id + thinking level + confidences.

    ``model_confidence`` is the routed model's own table probability
    (the tie-break runner-up read when substituted, never the vendor
    confidence field); ``effort_confidence`` is the second call's
    top-1 level probability, None when no effort question ran (the
    lone level of a single-level pick rides through instead).
    """

    model: str
    effort: str
    model_confidence: float | None = None
    effort_confidence: float | None = None
    tie_break: bool = False


def default_global_strategy_path() -> Path:
    """Global strategy file path (platformdirs home, never repo-relative)."""
    return Path(platformdirs.user_config_dir(_STRATEGY_DIR_NAME)) / _STRATEGY_FILE_NAME


def default_repo_strategy_path() -> Path:
    """Repo strategy file path (cwd-anchored ``./.agent/routing.yaml``)."""
    return Path(os.getcwd()) / _REPO_STRATEGY_REL


def _candidate_skip_reason(entry: object, pos: int) -> str | None:
    """None when the entry parses; else the exact loader skip reason.

    Single source of truth for candidate validity: the loader warns
    with this reason and ``validate_strategy`` reports it, so the
    command shows exactly what the loader would do.
    """
    if not isinstance(entry, dict):
        return "not a mapping"
    unknown = set(entry) - _CANDIDATE_KEYS
    if unknown:
        return f"unknown keys: {sorted(unknown)}"
    candidate_id = entry.get("id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        return "missing id"
    tier = entry.get("tier")
    if tier is not None and not isinstance(tier, str):
        return "'tier' not a string"
    note = entry.get("note")
    if note is not None and not isinstance(note, str):
        return "'note' not a string"
    levels = entry.get("levels")
    if levels is not None and (
        not isinstance(levels, list)
        or any(not isinstance(level, (str, bool)) for level in levels)
    ):
        return "'levels' not a string list"
    benchmarks = entry.get("benchmarks")
    if benchmarks is not None:
        if not isinstance(benchmarks, dict):
            return "'benchmarks' not a mapping"
        unknown_bench = set(benchmarks) - _BENCHMARK_KEYS
        if unknown_bench:
            return f"unknown benchmark keys: {sorted(unknown_bench)}"
    criteria = entry.get("criteria")
    if criteria is not None and not isinstance(criteria, str):
        return "'criteria' not a string"
    return None


def _parse_candidate(entry: object, pos: int) -> RoutingCandidate | None:
    """Normalize one candidate entry; warn and return None when untrusted."""
    reason = _candidate_skip_reason(entry, pos)
    if reason is not None:
        logger.warning("Ignoring routing candidate #%d (%s)", pos, reason)
        return None
    if not isinstance(entry, dict):  # unreachable: a None reason proves a dict
        return None
    levels = entry.get("levels")
    if levels is not None:
        # YAML 1.1 folds unquoted on/off to bools: honor the intent as level
        # strings so hand-edited strategies load as usable candidates.
        levels = [
            "on" if level is True else "off" if level is False else level
            for level in levels
        ]
    benchmarks = entry.get("benchmarks")
    return RoutingCandidate(
        id=entry["id"],
        tier=entry.get("tier"),
        note=entry.get("note"),
        levels=list(levels) if levels is not None else None,
        benchmarks=dict(benchmarks) if benchmarks is not None else None,
        criteria=entry.get("criteria"),
    )


_valid_base_url = valid_base_url


def _parse_engine_order(raw: dict[str, Any], engine: RoutingEngine) -> None:
    """Normalize the engine try-order list; unknown entries warn and drop."""
    order = raw.get("order")
    if order is not None:
        if not isinstance(order, list):
            logger.warning("Ignoring routing engine 'order' (not a list)")
        else:
            names: list[str] = []
            for entry in order:
                if entry not in _VALID_ORDER_ENGINES:
                    logger.warning(
                        "Ignoring unknown routing engine %r in 'order'", entry
                    )
                    continue
                if entry not in names:
                    names.append(entry)
            engine.order = names


def _assign_engine_string(engine: RoutingEngine, key: str, value: object) -> None:
    if not isinstance(value, str):
        logger.warning("Ignoring routing engine %r (not a string)", key)
        return
    if key in _ENGINE_MODEL_ID_KEYS:
        if not value.strip():
            setattr(engine, key, None)
            return
        if not valid_model_id(value):
            logger.warning(
                "Ignoring routing engine %r (contains whitespace or control characters)",
                key,
            )
            return
    setattr(engine, key, value)


def _parse_engine(raw: object) -> RoutingEngine:
    """Normalize the engine mapping; unknown keys warn and fall to defaults."""
    engine = RoutingEngine()
    if raw is None:
        return engine
    if not isinstance(raw, dict):
        logger.warning("Ignoring routing 'engine' (not a mapping); using defaults")
        return engine
    unknown = set(raw) - _ENGINE_KEYS
    if unknown:
        logger.warning("Ignoring unknown routing engine keys: %s", sorted(unknown))
    for key in _ENGINE_STRING_KEYS:
        value = raw.get(key)
        if value is not None:
            _assign_engine_string(engine, key, value)
    _parse_engine_order(raw, engine)
    skip_notes = raw.get("skip_notes", True)
    if not isinstance(skip_notes, bool):
        logger.warning("Ignoring routing engine 'skip_notes' (not true/false)")
    else:
        engine.skip_notes = skip_notes
    base_url = engine.local_base_url
    if base_url is not None and not base_url.strip():
        engine.local_base_url = None
    elif base_url is not None and not _valid_base_url(base_url):
        logger.warning(
            "Ignoring routing local_base_url %r (http/https only); using %s",
            base_url,
            OLLAMA_DEFAULT_HOST,
        )
        engine.local_base_url = OLLAMA_DEFAULT_HOST
    return engine


def _parse_knob(value: object, name: str, default: float) -> float:
    """One gate knob: missing defaults silently, wrong warns and defaults.

    The loader stays fail-soft (routing keeps running on the default);
    ``validate_strategy`` is the strict judge that fails out-of-range
    knobs with a fix line.
    """
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        logger.warning("Ignoring routing %r (not a number); using %s", name, default)
        return default
    number = float(value)
    if not 0.0 <= number <= 1.0:
        logger.warning(
            "Ignoring routing %r (%s outside 0..1); using %s", name, value, default
        )
        return default
    return number


def _parse_strategy(data: dict[str, Any], source: Path) -> RoutingStrategy:
    """Normalize one parsed YAML mapping (unknown top-level keys default)."""
    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        logger.warning("Ignoring unknown routing keys: %s", sorted(unknown))
    raw_candidates = data.get("candidates", [])
    candidates: list[RoutingCandidate] = []
    if raw_candidates is None:
        raw_candidates = []
    if not isinstance(raw_candidates, list):
        logger.warning("Ignoring routing 'candidates' (not a list)")
    else:
        for pos, entry in enumerate(raw_candidates):
            candidate = _parse_candidate(entry, pos)
            if candidate is not None:
                candidates.append(candidate)
    directives = data.get("directives", "")
    if directives is None:
        directives = ""
    if not isinstance(directives, str):
        logger.warning("Ignoring routing 'directives' (not a string)")
        directives = ""
    quiet = data.get("quiet", False)
    if not isinstance(quiet, bool):
        logger.warning("Ignoring routing 'quiet' (not true/false)")
        quiet = False
    return RoutingStrategy(
        candidates=candidates,
        directives=directives,
        engine=_parse_engine(data.get("engine")),
        quiet=quiet,
        tie_margin=_parse_knob(
            data.get("tie_margin"), "tie_margin", DEFAULT_TIE_MARGIN
        ),
        confidence_threshold=_parse_knob(
            data.get("confidence_threshold"),
            "confidence_threshold",
            DEFAULT_CONFIDENCE_THRESHOLD,
        ),
        source=source,
    )


def _load_one(path: Path) -> RoutingStrategy | None:
    """Parse one strategy file: None when missing or unparsable (warned)."""
    refuse_symlink(path, "routing strategy", max_ancestors=1)
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        logger.warning("Ignoring unreadable routing strategy %s: %s", path, exc)
        return None
    if data is None:
        return None
    if not isinstance(data, dict):
        logger.warning("Ignoring malformed routing strategy %s (not a mapping)", path)
        return None
    return _parse_strategy(data, path)


def load_strategy(
    global_path: str | Path | None = None,
    repo_path: str | Path | None = None,
) -> RoutingStrategy | None:
    """Load the routing strategy: repo wins whole-file, else global.

    Returns None when both files are missing or unparsable (routing off)
    and when the winning strategy sets ``engine.order: []`` — the off
    switch lives at the load layer, so the hook skips silently with zero
    engine calls and no hold note.

    Raises:
        ValueError: When either resolved path is a symlink (fail-loud,
            same policy as provider config and capability overrides).
    """
    repo = Path(repo_path) if repo_path is not None else default_repo_strategy_path()
    strategies = _load_one(repo)
    if strategies is not None:
        if not strategies.engine.order:
            return None
        local_url = strategies.engine.local_base_url
        if local_url and not _is_loopback_host(local_url):
            msg = f"Ignoring non-loopback engine.local_base_url {local_url!r} in repo strategy {repo}"
            logger.warning(msg)
            warnings.warn(msg, stacklevel=2)
            strategies.engine.local_base_url = None
        return strategies
    home = (
        Path(global_path) if global_path is not None else default_global_strategy_path()
    )
    strategies = _load_one(home)
    if strategies is not None and not strategies.engine.order:
        return None
    return strategies


def _is_secret_shaped_key(key: object) -> bool:
    """True when a mapping key looks like a credential slot (T-08-10).

    Matches ``api_key`` in any case/separator spelling (``API_KEY``,
    ``api-key``, ``apikey``, ``apiKey``); anything matching is dropped
    on save so guided setup can never persist a key next to the
    strategy — keys stay runtime env per 08-01.
    """
    if not isinstance(key, str):
        return False
    folded = key.lower().replace("_", "").replace("-", "")
    return "apikey" in folded


def _resolve_strategy_write_path(
    scope: str, global_path: str | Path | None, repo_path: str | Path | None
) -> Path:
    if scope == "global":
        return (
            Path(global_path)
            if global_path is not None
            else default_global_strategy_path()
        )
    if scope == "repo":
        return (
            Path(repo_path) if repo_path is not None else default_repo_strategy_path()
        )
    raise ValueError(f"Unknown strategy scope {scope!r}: expected global|repo")


def _scrub_secret_engine(engine: dict[Any, Any]) -> dict[Any, Any]:
    cleaned = {k: v for k, v in engine.items() if not _is_secret_shaped_key(k)}
    for dropped in set(engine) - set(cleaned):
        logger.warning(
            "Dropping secret-shaped routing engine key %r (keys stay runtime env)",
            dropped,
        )
    return cleaned


def _scrub_secret_keys(data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in data.items():
        if _is_secret_shaped_key(key):
            logger.warning(
                "Dropping secret-shaped routing key %r (keys stay runtime env)", key
            )
            continue
        payload[key] = (
            _scrub_secret_engine(value)
            if key == "engine" and isinstance(value, dict)
            else value
        )
    return payload


def _count_usable_candidates(payload: dict[str, Any]) -> int:
    raw_candidates = payload.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return 0
    return sum(
        1
        for pos, entry in enumerate(raw_candidates)
        if _parse_candidate(entry, pos) is not None
    )


def save_strategy(
    data: dict[str, Any],
    scope: str,
    *,
    global_path: str | Path | None = None,
    repo_path: str | Path | None = None,
) -> Path:
    """Write one guided-setup strategy atomically (D-13)."""
    if not isinstance(data, dict):
        raise ValueError("Routing strategy must be a mapping")
    resolved = _resolve_strategy_write_path(scope, global_path, repo_path)
    payload = _scrub_secret_keys(data)
    if _count_usable_candidates(payload) == 0:
        raise ValueError(
            "Refusing to write a routing strategy with zero usable candidates"
        )
    return atomic_write_text(
        resolved,
        yaml.safe_dump(payload),
        mode=0o600,
        dir_mode=0o700,
        refuse_ancestors=1,
        label="routing strategy",
    )


@dataclass
class ValidationReport:
    """One strategy validity judgment for ``/route validate``."""

    valid: bool
    source: Path | None
    lines: list[str] = field(default_factory=list)
    """Detail lines in display order: candidates, knobs, engine, directives."""

    def format(self) -> str:
        """Render the full report as the ``/route validate`` reply."""
        head = "Routing strategy VALID" if self.valid else "Routing strategy INVALID"
        source = str(self.source) if self.source is not None else "(no file)"
        return "\n".join([f"{head} — {source}"] + self.lines)


def _read_strategy_data(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Raw YAML mapping plus failure reason (None reason when absent-or-ok).

    Missing and empty files read as absent (None, None) — the loader
    falls through them; corrupt and non-mapping files read as broken
    with the loader's reason.
    """
    if not path.exists():
        return (None, None)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return (None, f"unreadable: {exc}")
    if data is None:
        return (None, None)
    if not isinstance(data, dict):
        return (None, "not a mapping")
    return (data, None)


def _candidate_fix(reason: str, pos: int) -> str:
    """Manual-edit fix line for one loader skip reason."""
    if reason == "not a mapping":
        return f"make candidates[{pos}] a mapping like {{id: provider/model}}"
    if reason.startswith("unknown keys:"):
        return (
            f"remove the unknown keys from candidates[{pos}] "
            "(allowed: id, tier, note, levels, benchmarks, criteria)"
        )
    if reason == "missing id":
        return f"add id: <provider/model> to candidates[{pos}]"
    if reason == "'tier' not a string":
        return f"make candidates[{pos}].tier a string"
    if reason == "'note' not a string":
        return f"make candidates[{pos}].note a string"
    if reason == "'levels' not a string list":
        return f"make candidates[{pos}].levels a list like [low, high]"
    if reason == "'benchmarks' not a mapping":
        return f"make candidates[{pos}].benchmarks a mapping"
    if reason.startswith("unknown benchmark keys:"):
        return (
            f"remove the unknown keys from candidates[{pos}].benchmarks "
            "(allowed: swe_verified, lmarena_coding, aa_index, pulled)"
        )
    if reason == "'criteria' not a string":
        return f"make candidates[{pos}].criteria a string"
    return f"repair candidates[{pos}] ({reason})"


def _cached_decision_ids() -> set[str] | None:
    """Decisions-catalog ids from the disk cache only (None when absent).

    Never fetches: validate judges the real file against cached entries
    only and must report without network (D-13).
    """
    from strands_code_cli.cost.live_pricing import cached_tables

    try:
        tables = cached_tables()
    except Exception:
        return None
    decisions = tables.get("decisions")
    if not isinstance(decisions, dict):
        return None
    models = decisions.get("models")
    if not isinstance(models, dict):
        return None
    return {key for key in models if isinstance(key, str)}


def _bare_catalog_id(model_id: str) -> str:
    """Strip an aggregator prefix for the cached-catalog membership check."""
    lowered = model_id.lower()
    for prefix in ("litellm/openrouter/", "openrouter/"):
        if lowered.startswith(prefix):
            return model_id[len(prefix) :]
    return model_id


def _catalog_known(model_id: str, catalog: set[str]) -> bool:
    """True when the id is catalog-known verbatim or prefix-stripped.

    Verbatim wins: genuine catalog ids can start with ``openrouter/``
    (e.g. ``openrouter/auto``), so stripping first would mangle them
    (UAT R1). The stripped form stays as a fallback for aggregator
    routes like ``litellm/openrouter/<id>``.
    """
    return model_id in catalog or _bare_catalog_id(model_id) in catalog


def _openrouter_catalog_lines(decision_model: str) -> tuple[bool, list[str]]:
    """Catalog verdict lines for one OpenRouter decision model.

    Unchecked when the cached decisions catalog is unreachable, known
    when the id matches, INVALID with a fix line otherwise.
    """
    catalog = _cached_decision_ids()
    if catalog is None:
        return True, [
            f"engine: decision model {decision_model} — unchecked "
            "(no cached decisions catalog; run /cost refresh, then re-validate)"
        ]
    if _catalog_known(decision_model, catalog):
        return True, [
            f"engine: decision model {decision_model} — "
            "known in the cached decisions catalog"
        ]
    return False, [
        f"engine: INVALID — decision model {decision_model} "
        "not in the cached decisions catalog",
        "fix: pick a live id from the decisions listing "
        "(re-run /route setup), then /cost refresh and re-validate",
    ]


def _validate_single_order_engine(
    name: str, engine: RoutingEngine, lines: list[str]
) -> bool:
    """Validate one engine entry in ``engine.order`` without network I/O."""
    if name == "openrouter":
        if not engine.decision_model:
            lines.append(
                "engine: INVALID — order lists openrouter with no decision_model"
            )
            lines.append(
                "fix: set engine.decision_model to a decisions-catalog id, "
                "or re-run /route setup"
            )
            return False
        passed, extra = _openrouter_catalog_lines(engine.decision_model)
        lines.extend(extra)
        return passed
    if name == "local":
        if not engine.local_model:
            lines.append("engine: INVALID — order lists local with no local_model")
            lines.append(
                "fix: set engine.local_model to your Ollama tag, "
                "or drop local from engine.order"
            )
            return False
        lines.append(f"engine: local model {engine.local_model} — ok")
        return True
    if name == "native":
        if not engine.native_model:
            lines.append("engine: INVALID — order lists native with no native_model")
            lines.append(
                f"fix: set engine.native_model to {NATIVE_JEV_PIN}, or re-run /route setup"
            )
            return False
        if engine.native_model not in _NATIVE_MODEL_IDS:
            lines.append(
                "engine: INVALID — native model "
                f"{engine.native_model!r} is not a verified native id"
            )
            lines.append(
                f"fix: set engine.native_model to {NATIVE_JEV_PIN} "
                "(full semver pin; minor-only and prefixed forms are rejected)"
            )
            return False
        lines.append(f"engine: native model {engine.native_model} — ok")
        return True
    if name == "decisions_api":
        model_id = engine.decisions_api_model or DECISIONS_API_DEFAULT_MODEL
        lines.append(f"engine: decisions_api model {model_id} — ok")
        return True
    if name == "llm":
        if not engine.llm_model:
            lines.append("engine: INVALID — order lists llm with no llm_model")
            lines.append(
                "fix: set engine.llm_model to a provider/model id (e.g. openai/gpt-4o-mini)"
            )
            return False
        lines.append(f"engine: llm model {engine.llm_model} — ok")
        return True
    return True


def _validate_engine_order_chain(
    raw_engine: object,
    engine: RoutingEngine,
    lines: list[str],
) -> bool:
    """Judge the engine.order chain shape plus each named engine (strict)."""
    ok = True
    if isinstance(raw_engine, dict) and "order" in raw_engine:
        raw_order = raw_engine.get("order")
        if not isinstance(raw_order, list):
            ok = False
            lines.append(
                "engine: INVALID — engine.order is not a list (the loader ignores it)"
            )
            lines.append("fix: set engine.order to a list like [native, openrouter]")
        else:
            for entry in raw_order:
                if entry not in _VALID_ORDER_ENGINES:
                    ok = False
                    lines.append(
                        f"engine: INVALID — unknown engine {entry!r} in engine.order"
                    )
                    lines.append(
                        f"fix: remove {entry!r} from engine.order "
                        "(expected native|openrouter|local|decisions_api|llm)"
                    )
    order = _effective_order(engine)
    if not order:
        lines.append("engine: order empty — routing disabled by config")
    else:
        for name in order:
            if not _validate_single_order_engine(name, engine, lines):
                ok = False
    return ok


def _validate_candidates(data: dict[str, Any], lines: list[str]) -> bool:
    """Judge the candidates list: one line per entry plus the 26-cap."""
    ok = True
    raw_candidates: object = data.get("candidates", [])
    if raw_candidates is None:
        raw_candidates = []
    if not isinstance(raw_candidates, list):
        lines.append("candidates: INVALID — not a list (the loader ignores it)")
        lines.append("fix: make candidates: a list of {id: ...} entries")
        return False
    usable = 0
    for pos, entry in enumerate(raw_candidates):
        reason = _candidate_skip_reason(entry, pos)
        if reason is None:
            usable += 1
            lines.append(f"candidate #{pos} {entry['id']}: ok")
        else:
            ok = False
            lines.append(f"candidate #{pos}: SKIP — {reason}")
            lines.append(f"fix: {_candidate_fix(reason, pos)}")
    if len(raw_candidates) > MAX_CANDIDATES:
        ok = False
        lines.append(
            f"candidates: INVALID — {len(raw_candidates)} entries "
            f"exceeds the {MAX_CANDIDATES}-candidate cap"
        )
        lines.append(
            f"fix: keep at most {MAX_CANDIDATES} candidates "
            "(the choice call caps at 26 options)"
        )
    if usable == 0:
        ok = False
        lines.append("no usable candidates — routing stays off")
        lines.append(
            "fix: add at least one candidates entry with a model id, "
            "or re-run /route setup"
        )
    return ok


def _validate_knobs(data: dict[str, Any], lines: list[str]) -> bool:
    """Judge the gate knobs: explicit in-range numbers or noted defaults."""
    ok = True
    for knob, default in (
        ("tie_margin", DEFAULT_TIE_MARGIN),
        ("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD),
    ):
        raw_knob = data.get(knob)
        if raw_knob is None:
            lines.append(f"{knob}: {default} (default)")
        elif isinstance(raw_knob, bool) or not isinstance(raw_knob, (int, float)):
            ok = False
            lines.append(f"{knob}: INVALID — {raw_knob!r} is not a number")
            lines.append(f"fix: set {knob} to a number between 0 and 1")
        elif not 0.0 <= float(raw_knob) <= 1.0:
            ok = False
            lines.append(f"{knob}: INVALID — {raw_knob} is outside 0..1")
            lines.append(f"fix: set {knob} to a number between 0 and 1")
        else:
            lines.append(f"{knob}: {float(raw_knob)}")
    return ok


def _validate_directives(data: dict[str, Any], lines: list[str]) -> None:
    """Note the directives presence (advisory only; never fails validation)."""
    directives = data.get("directives", "")
    if directives is None:
        directives = ""
    if not isinstance(directives, str):
        lines.append("note: directives is not a string (the loader ignores it)")
    elif directives.strip():
        lines.append(f"directives: present ({len(directives)} chars)")
        if len(directives) > 4096:
            lines.append(
                "warning: directives exceed ~4K chars — they ride every "
                "decision call twice, so trim for cost and accuracy"
            )
    else:
        lines.append("note: no directives — the decider picks without guidance")


def _select_strategy_source(
    repo: Path, home: Path
) -> ValidationReport | tuple[dict[str, Any], Path, str | None]:
    """Pick the winning strategy file (repo wins whole-file, else global).

    Returns a ``ValidationReport`` directly for the symlink and
    neither-file cases, else ``(data, source, fallback-note)``.
    """
    for path in (repo, home):
        try:
            refuse_symlink(path, "routing strategy", max_ancestors=1)
        except ValueError as exc:
            return ValidationReport(
                valid=False,
                source=None,
                lines=[
                    f"strategy path is a symlink: {exc}",
                    "fix: replace the symlink with a real file",
                ],
            )
    repo_data, repo_reason = _read_strategy_data(repo)
    home_data, home_reason = _read_strategy_data(home)
    if repo_data is not None:
        return repo_data, repo, None
    if home_data is not None:
        fallback = (
            f"note: repo strategy {repo} is {repo_reason} "
            "(using the global file instead) — fix the repo file or delete it"
            if repo_reason is not None
            else None
        )
        return home_data, home, fallback
    lines = []
    if repo_reason is not None:
        lines.append(f"repo strategy {repo} is {repo_reason}")
        lines.append("fix: repair the YAML or delete the file and re-run /route setup")
    if home_reason is not None:
        lines.append(f"global strategy {home} is {home_reason}")
        lines.append("fix: repair the YAML or delete the file and re-run /route setup")
    if not lines:
        lines.append("no strategy file found")
        lines.append("fix: run /route setup to create one")
    return ValidationReport(valid=False, source=None, lines=lines)


def _validate_engine_model_ids(raw_engine: object, lines: list[str]) -> bool:
    if not isinstance(raw_engine, dict):
        return True
    ok = True
    for key in _ENGINE_MODEL_ID_KEYS:
        raw_val = raw_engine.get(key)
        if isinstance(raw_val, str) and raw_val.strip() and not valid_model_id(raw_val):
            ok = False
            lines.append(
                f"engine: INVALID — {key} contains whitespace or control characters"
            )
            lines.append(
                f"fix: remove whitespace and control characters from engine.{key}"
            )
    return ok


def _validate_engine_head(
    raw_engine: object,
    lines: list[str],
) -> bool:
    """Judge the engine model ids plus the local base URL (strict)."""
    if isinstance(raw_engine, dict):
        unknown_eng = sorted(set(raw_engine) - _ENGINE_KEYS)
        if unknown_eng:
            hint = (
                " (legacy 'primary' was retired — use engine.order)"
                if "primary" in unknown_eng
                else " (the loader warns and continues)"
            )
            lines.append(f"note: unknown engine keys ignored: {unknown_eng}{hint}")
    ok = _validate_engine_model_ids(raw_engine, lines)
    raw_base_url = (
        raw_engine.get("local_base_url") if isinstance(raw_engine, dict) else None
    )
    if (
        isinstance(raw_base_url, str)
        and raw_base_url.strip()
        and not _valid_base_url(raw_base_url)
    ):
        ok = False
        lines.append(
            f"engine: INVALID — local_base_url {raw_base_url!r} "
            "is not an http/https URL"
        )
        lines.append("fix: set engine.local_base_url to an http(s) URL or remove it")
    return ok


def validate_strategy(
    global_path: str | Path | None = None,
    repo_path: str | Path | None = None,
) -> ValidationReport:
    """Judge the winning strategy file without network, writes, or engines.

    Mirrors ``load_strategy`` precedence (repo wins whole-file, broken
    files fall back with a note) and reports the winning source, one
    line per candidate (ok or the exact loader skip reason), the
    26-candidate cap, the effective gate knobs (explicit or default),
    engine checks with the decision model looked up in the cached
    decisions catalog only (unchecked when the cache is unreachable),
    and the directives presence note. Every failure class carries a
    manual-edit fix.
    """
    repo = Path(repo_path) if repo_path is not None else default_repo_strategy_path()
    home = (
        Path(global_path) if global_path is not None else default_global_strategy_path()
    )
    selected = _select_strategy_source(repo, home)
    if isinstance(selected, ValidationReport):
        return selected
    data, source, fallback = selected
    lines = [fallback] if fallback is not None else []
    valid = True
    unknown_top = set(data) - _TOP_LEVEL_KEYS
    if unknown_top:
        lines.append(
            f"note: unknown top-level keys ignored: {sorted(unknown_top)} "
            "(the loader warns and continues)"
        )
    if not _validate_candidates(data, lines):
        valid = False
    if not _validate_knobs(data, lines):
        valid = False
    engine = _parse_engine(data.get("engine"))
    raw_engine = data.get("engine")
    if not _validate_engine_head(raw_engine, lines):
        valid = False
    if not _validate_engine_order_chain(raw_engine, engine, lines):
        valid = False
    _validate_directives(data, lines)
    return ValidationReport(valid=valid, source=source, lines=lines)


_MODEL_INSTRUCTIONS_BASE = (
    "Which candidate model should serve the ask in `ask`? "
    "Judge the ask, not its length. "
)


def build_decision_state(*, ask: str, directives: str, side: bool) -> dict[str, Any]:
    """Build the Decision-API state for one ask (T-08-23).

    Ask plus directives plus the side flag only — no history, tool
    results, file contents, or candidate stats. Ask and directives are
    each truncated to ASK_TRUNCATE_CHARS so a malicious repo strategy
    file cannot inject unbounded text into the paid decision call.
    """
    return {
        "ask": ask[:ASK_TRUNCATE_CHARS],
        "directives": directives[:ASK_TRUNCATE_CHARS] if directives else "",
        "side": side,
    }


def _criteria_text(candidate: RoutingCandidate) -> str:
    """One criteria prose line: criteria, else note, tier, or the id.

    The option name describing itself is the last resort (the Clef
    ``criteria: null`` precedent); blank strings count as missing.
    """
    for text in (candidate.criteria, candidate.note, candidate.tier):
        if isinstance(text, str) and text.strip():
            return text.strip()[:500]
    return candidate.id[:500]


def build_model_question(
    *, candidates: list[RoutingCandidate], directives: str
) -> dict[str, Any]:
    """Build the pick_model choice question (D-02, D-07).

    Criteria map each candidate id to its criteria prose; directives
    append to the instructions so they shape the judgment directly.
    Prices, windows, and benchmarks never enter the call — decision
    models do no quantities, so they stay code-side (the tie-break
    reads the almanac instead). No ``none`` criterion: below-threshold
    tables hold code-side (D-16).
    """
    shaped = directives[:ASK_TRUNCATE_CHARS] if directives else ""
    return {
        "type": "choice",
        "instructions": _MODEL_INSTRUCTIONS_BASE + shaped,
        "criteria": {
            candidate.id: _criteria_text(candidate) for candidate in candidates
        },
    }


_EFFORT_CRITERIA = {
    "auto": "Let the model decide how much thinking this ask needs",
    "off": "Answer directly with no thinking budget",
    "minimal": "Minimal thinking for trivial asks answerable at a glance",
    "low": "Light thinking for simple asks with a clear answer",
    "medium": "Moderate thinking for everyday implementation and debugging",
    "high": "Deep thinking for complex refactors and multi-step work",
    "xhigh": "Extended thinking for the hardest asks needing careful reasoning",
    "max": "Maximum thinking budget for the most demanding asks",
}
"""Fixed code-side prose per known effort level (the harness Effort set).

Unknown levels fall back to the bare level name, never operator
prose — the map is code, not strategy text (T-08-26).
"""


def build_effort_question(
    *, candidate: RoutingCandidate, directives: str
) -> dict[str, Any]:
    """Build the pick_effort choice question over one candidate (D-05, D-15).

    Criteria cover exactly the picked candidate's advertised levels —
    the second call judges only levels the pick can serve. Directives
    append to the instructions so they shape the effort judgment like
    the model one (D-07).
    """
    shaped = directives[:ASK_TRUNCATE_CHARS] if directives else ""
    return {
        "type": "choice",
        "instructions": (
            f"How much thinking budget does the ask in `ask` need "
            f"on {candidate.id}? "
            "Judge the ask, not its length. " + shaped
        ),
        "criteria": {
            level: _EFFORT_CRITERIA.get(level, level)
            for level in candidate.levels or []
        },
    }


def _retryable_error(exc: BaseException) -> bool:
    """True for the one-retry class: retryable codes plus timeouts."""
    return _transport_retryable_error(exc)


_CONNECTION_ERRORS = frozenset({"refused", "unreachable"})
"""Failure classes that pause routing when they take every link (D-09)."""


def _failure_reason(exc: BaseException) -> str:
    """Short failure class for one transport exception (never secrets)."""
    return _transport_failure_reason(exc)


def _with_truncation(detail: str, truncated: bool) -> str:
    """Append the truncation marker once when the payload shrank."""
    if not truncated or TRUNCATION_MARKER in detail:
        return detail
    return f"{detail}; {TRUNCATION_MARKER}" if detail else TRUNCATION_MARKER


def decide_via_openrouter(
    *,
    decision_model: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via OpenRouterDecisionModel."""
    return run_openrouter_decision(
        decision_model=decision_model,
        state=state,
        questions=questions,
        timeout=timeout,
    )


def decide_via_typesafe(
    *,
    native_model: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via upstream TypeSafeDecisionModel."""
    return run_typesafe_decision(
        native_model=native_model,
        state=state,
        questions=questions,
        timeout=timeout,
    )


def decide_via_decisions_api(
    *,
    model_id: str | None = None,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via upstream DecisionsAPIDecisionModel."""
    return run_decisions_api_decision(
        model_id=model_id,
        state=state,
        questions=questions,
        timeout=timeout,
    )


def decide_via_llm(
    *,
    llm_model: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = DECISION_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via upstream LLMDecisionModel."""
    return run_llm_decision(
        llm_model=llm_model,
        state=state,
        questions=questions,
        timeout=timeout,
    )


_ollama_base = ollama_base
_ollama_headers = ollama_headers


def _preflight_get(url: str, headers: dict[str, str]) -> dict[str, Any] | None:
    """One daemon preflight GET: parsed mapping or None on any failure."""
    return preflight_get(url, headers)


def _version_tuple(text: object) -> tuple[int, ...] | None:
    """Dotted version to ints; None when unparseable (fail closed)."""
    if not isinstance(text, str) or not text:
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except ValueError:
        return None


def native_engine_ready() -> bool:
    """True when a native call is worth attempting: key present (D-06).

    No network: like the OpenRouter link (which has no preflight),
    attempted-call failure carries the detail (401 bad key, 403 no
    key, 400 unknown model). Presence only — the value never leaves
    the environment. The setup proposal and the hidden-until-key
    gate read this; env reads stay in the engine layer, never the
    presentation layer.
    """
    return read_env_api_key("TYPESAFE_API_KEY") is not None


def decisions_api_engine_ready() -> bool:
    """True when a decisionapi.net call is worth attempting: JEV_API_KEY present."""
    return read_env_api_key("JEV_API_KEY") is not None


def local_engine_ready(base: str | None, tag: str) -> bool:
    """True when the Ollama daemon meets the floor and has the tag pulled.

    Probes GET ``<base>/api/version`` for the 0.35 floor (0.35.1 for
    tags starting with ``clef``) and GET ``<base>/api/tags`` for the
    tag (exact or ``:latest``-suffixed daemon names match). A None
    base resolves the default daemon base (the setup proposal
    probe); an empty base or tag still reads unready. Any
    transport or parse failure returns False without raising — the
    chain treats unready as skip, never as ready (T-08-30).
    """
    if base is None:
        base = _ollama_base(None)
    if not base or not tag or not _valid_base_url(base):
        return False
    root = base.rstrip("/")
    version = _preflight_get(f"{root}/api/version", _ollama_headers(base))
    if version is None:
        return False
    parsed = _version_tuple(version.get("version"))
    if parsed is None:
        return False
    floor = (0, 35, 1) if tag.startswith("clef") else (0, 35)
    if parsed < floor:
        return False
    tags = _preflight_get(f"{root}/api/tags", _ollama_headers(base))
    if tags is None:
        return False
    models = tags.get("models")
    if not isinstance(models, list):
        return False
    names = {
        model["name"]
        for model in models
        if isinstance(model, dict) and isinstance(model.get("name"), str)
    }
    if tag in names:
        return True
    bare = {
        name[: -len(":latest")] if name.endswith(":latest") else name for name in names
    }
    return tag in bare


def decide_via_ollama(
    *,
    local_model: str,
    local_base_url: str | None = None,
    state: dict[str, Any],
    questions: dict[str, Any],
    timeout: float = OLLAMA_TIMEOUT_SECONDS,
) -> EngineResult:
    """One routing decision via OllamaDecisionModel (``/v1/systemone``)."""
    return run_ollama_decision(
        local_model=local_model,
        local_base_url=local_base_url,
        state=state,
        questions=questions,
        timeout=timeout,
    )


def _validate_choice_shape(answer: object) -> dict[str, Any] | None:
    """Typed shape check shared by both decision calls; None holds.

    Checks finite probabilities in [0.0, 1.0] summing to 1 within 1e-6
    (widened for 4-decimal System One grid rounding within 5e-5 per option),
    plus a string choice present in the table.
    """
    if not isinstance(answer, dict) or answer.get("type") != "choice":
        return None
    probs = answer.get("probabilities")
    if not isinstance(probs, dict) or not probs:
        return None
    for prob in probs.values():
        if (
            isinstance(prob, bool)
            or not isinstance(prob, (int, float))
            or not math.isfinite(float(prob))
            or not 0.0 <= float(prob) <= 1.0
        ):
            return None
    vals = probs.values()
    rounded = all(abs(p * 1e4 - round(p * 1e4)) < 1e-6 for p in vals)
    tol = min(0.01, 1e-6 + (len(probs) * 5e-5 if rounded else 0.0))
    if abs(sum(vals) - 1.0) > tol:
        return None
    choice = answer.get("choice")
    if not isinstance(choice, str) or choice not in probs:
        return None
    return answer


def validate_choice_answer(
    answer: object, candidates: list[RoutingCandidate]
) -> dict[str, Any] | None:
    """Validate one typed choice answer; None holds the current model.

    The answer must pass the shape check plus name a ``choice`` that
    sits in the live candidate ids (a stale pick after a strategy
    edit must never route — no normalization, no fuzzy match). The
    vendor ``confidence`` field may be absent; it is logged, never
    gated on (T-08-21).
    """
    answer = _validate_choice_shape(answer)
    if answer is None:
        return None
    live = {candidate.id for candidate in candidates}
    choice = answer.get("choice")
    probs = answer.get("probabilities")
    if (
        not isinstance(choice, str)
        or choice not in live
        or not isinstance(probs, dict)
        or not set(probs).issubset(live)
    ):
        return None
    return answer


def _validate_effort_answer(answer: object) -> dict[str, float] | None:
    """Validate one effort table; the probability mapping or None.

    Shape only — level membership is judged downstream by
    ``validate_routed_effort`` so an outside-level read holds with
    its unsupported-effort detail instead of a bare engine failure.
    """
    answer = _validate_choice_shape(answer)
    if answer is None:
        return None
    return answer["probabilities"]


def _price_total(model_id: str) -> float | None:
    """Almanac in+out price for one id (None when unpriced — D-14)."""
    try:
        prices = price_for(model_id)
    except Exception:
        return None
    if prices is None:
        return None
    return prices[0] + prices[1]


def gate_model(
    answer: dict[str, Any], strategy: RoutingStrategy
) -> tuple[str | None, bool, str]:
    """Gate one validated model table: (model|None, tie_break, detail).

    Below-threshold top-1 probabilities hold (D-16); near-tie top-two
    gaps route the cheaper candidate per almanac prices with a detail
    note (D-14). The gate reads the probability table only — never
    the vendor confidence field (Pitfall 1) and never the ``choice``
    field (the argmax is the source of truth). Unpriced or
    equal-priced pairs keep the argmax with no tie marker.
    """
    ranked = sorted(
        answer["probabilities"].items(), key=lambda item: (-item[1], item[0])
    )
    top, top_prob = ranked[0]
    if top_prob < strategy.confidence_threshold:
        return (
            None,
            False,
            f"confidence {top_prob:.0%} < {strategy.confidence_threshold:.0%}",
        )
    if len(ranked) == 1:
        return (top, False, "")
    second, second_prob = ranked[1]
    if top_prob - second_prob > strategy.tie_margin:
        return (top, False, "")
    top_price = _price_total(top)
    second_price = _price_total(second)
    if top_price is None or second_price is None or second_price >= top_price:
        return (top, False, "")
    return (
        second,
        True,
        f"tie {top_prob:.0%} vs {second_prob:.0%} → {second} (cheaper)",
    )


EngineAttempt = Callable[
    [RoutingStrategy, dict[str, Any], dict[str, Any]], EngineResult | None
]
"""One engine try: (strategy, state, questions) -> result or None when skipped."""

_ENGINE_REGISTRY: list[tuple[str, EngineAttempt]] = []
"""Ordered engine chain; each engine is tried once per ask."""


def register_engine(name: str, attempt: EngineAttempt) -> None:
    """Append one named engine to the chain (openrouter, local, native)."""
    _ENGINE_REGISTRY.append((name, attempt))


def _openrouter_attempt(
    strategy: RoutingStrategy, state: dict[str, Any], questions: dict[str, Any]
) -> EngineResult | None:
    """OpenRouter chain link: None without a configured decision model."""
    decision_model = strategy.engine.decision_model
    if not decision_model:
        return None
    return decide_via_openrouter(
        decision_model=decision_model, state=state, questions=questions
    )


def _ollama_attempt(
    strategy: RoutingStrategy, state: dict[str, Any], questions: dict[str, Any]
) -> EngineResult | None:
    """Local chain link: None without a configured local model (skipped)."""
    local_model = strategy.engine.local_model
    if not local_model:
        return None
    return decide_via_ollama(
        local_model=local_model,
        local_base_url=strategy.engine.local_base_url,
        state=state,
        questions=questions,
    )


def _typesafe_attempt(
    strategy: RoutingStrategy, state: dict[str, Any], questions: dict[str, Any]
) -> EngineResult | None:
    """Native chain link: None without a model, or without a key (D-03).

    A listed native engine with no ``TYPESAFE_API_KEY`` skips
    silently here; :func:`chain_skip_notes` carries the one-line
    note for the print site.
    """
    native_model = strategy.engine.native_model
    if not native_model:
        return None
    if not read_env_api_key("TYPESAFE_API_KEY"):
        return None
    return decide_via_typesafe(
        native_model=native_model, state=state, questions=questions
    )


def _local_unready_attempt(
    _strategy: RoutingStrategy, _state: dict[str, Any], _questions: dict[str, Any]
) -> EngineResult:
    """Inert local link: an unready daemon skips with zero POSTs.

    Offered by :func:`_chain_for` when :func:`local_engine_ready`
    fails — version below the floor, tag not pulled, or preflight
    unreachable — so the verdict carries the distinct unready detail
    instead of a transport failure.
    """
    return EngineResult(answers=None, error="unready")


def _decisions_api_attempt(
    strategy: RoutingStrategy, state: dict[str, Any], questions: dict[str, Any]
) -> EngineResult | None:
    """Decisions API chain link: None without JEV_API_KEY."""
    if not read_env_api_key("JEV_API_KEY"):
        return None
    return decide_via_decisions_api(
        model_id=strategy.engine.decisions_api_model,
        state=state,
        questions=questions,
    )


def _llm_attempt(
    strategy: RoutingStrategy, state: dict[str, Any], questions: dict[str, Any]
) -> EngineResult | None:
    """LLM chain link: None without a configured llm_model."""
    llm_model = strategy.engine.llm_model
    if not llm_model:
        return None
    return decide_via_llm(
        llm_model=llm_model,
        state=state,
        questions=questions,
    )


register_engine("openrouter", _openrouter_attempt)
register_engine("local", _ollama_attempt)
register_engine("native", _typesafe_attempt)
register_engine("decisions_api", _decisions_api_attempt)
register_engine("llm", _llm_attempt)


def chain_skip_notes(strategy: RoutingStrategy) -> list[str]:
    """One-line D-03 notes for listed-but-skipped engines."""
    engine = strategy.engine
    order = _effective_order(engine)
    notes: list[str] = []
    if (
        "native" in order
        and engine.native_model
        and not read_env_api_key("TYPESAFE_API_KEY")
    ):
        notes.append("native engine skipped: TYPESAFE_API_KEY not set")
    if "decisions_api" in order and not read_env_api_key("JEV_API_KEY"):
        notes.append("decisions_api engine skipped: JEV_API_KEY not set")
    if "openrouter" in order and not read_env_api_key("OPENROUTER_API_KEY"):
        notes.append("openrouter engine skipped: OPENROUTER_API_KEY not set")
    return notes


def _link_detail(name: str, error: str | None) -> str:
    """Verdict detail for one failed link: engine plus cause.

    Unready skips name the preflight cause; HTTP failures name engine
    plus code; timeouts, refusals, and unreachable hosts name engine
    plus class; schema misses name the validation failure. Links
    without failure information keep the legacy ``<engine> failed``
    shape (byte-identical for missing-key and decide-level holds).
    """
    if error == "unready":
        return f"{name} unready (daemon version or tag not ready)"
    if error is not None and error.startswith("HTTP "):
        return f"{name} {error[len('HTTP ') :]}"
    if error in ("timeout", "refused", "unreachable"):
        return f"{name} {error}"
    if error in ("invalid body", "invalid table"):
        return f"{name} {error}"
    return f"{name} failed"


def _pause_detail(down: list[str]) -> str:
    """Distinct pause detail naming every unreachable link (D-09)."""
    return f"paused: all engines unreachable ({', '.join(down)})"


def is_pause_detail(detail: str) -> bool:
    """True when a verdict detail pauses routing for the ask (D-09)."""
    return detail.startswith("paused:")


def _effective_order(engine: RoutingEngine) -> list[str]:
    """Engine order for one strategy (sole engine.order schema)."""
    return list(engine.order)


def _acc_usage(
    acc: tuple[int, int, float | None], result: EngineResult
) -> tuple[int, int, float | None]:
    """Accumulate decision tokens and cost across engine calls."""
    return (
        acc[0] + result.input_tokens,
        acc[1] + result.output_tokens,
        _merge_cost(acc[2], result.cost),
    )


def _chain_for(strategy: RoutingStrategy) -> list[tuple[str, EngineAttempt]]:
    """Engine links for one strategy: order drives, unconfigured skips.

    The effective order lists the links in try order; an empty order
    tries nothing — the load layer already yields None for legacy
    off, and a directly built off strategy (or an explicit empty
    order) degrades the same way here. The local link is skipped,
    not failed, when no local model configures, and consults
    :func:`local_engine_ready` before it is offered: an unready
    daemon yields the inert unready link (zero POSTs, distinct
    detail) instead of a doomed decision call.
    """
    names = _effective_order(strategy.engine)
    by_name = dict(_ENGINE_REGISTRY)
    chain: list[tuple[str, EngineAttempt]] = []
    for name in names:
        if name == "local":
            if not strategy.engine.local_model:
                continue
            base = _ollama_base(strategy.engine.local_base_url)
            if not local_engine_ready(base, strategy.engine.local_model):
                chain.append((name, _local_unready_attempt))
                continue
        attempt = by_name.get(name)
        if attempt is not None:
            chain.append((name, attempt))
    return chain


def _merge_cost(first: float | None, second: float | None) -> float | None:
    """Summed reported spend; None only when both calls omit cost."""
    if first is None and second is None:
        return None
    return (first if first is not None else 0.0) + (
        second if second is not None else 0.0
    )


def _evaluate_effort_answer(
    name: str,
    result: EngineResult,
) -> tuple[str | None, float | None, tuple[int, int, float | None] | None]:
    """Validate one pick_effort answer; returns ``(effort, confidence, usage)``."""
    raw_effort = (result.answers or {}).get("pick_effort")
    if (
        name == "llm"
        and isinstance(raw_effort, dict)
        and raw_effort.get("type") == "llm_choice"
    ):
        choice = raw_effort.get("choice")
        if not isinstance(choice, str) or not choice.strip():
            return None, None, None
        return (
            choice,
            None,
            (result.input_tokens, result.output_tokens, result.cost),
        )
    table = _validate_effort_answer(raw_effort)
    if table is None:
        return None, None, None
    ranked = sorted(table.items(), key=lambda item: (-item[1], item[0]))
    top, top_prob = ranked[0]
    return (
        top,
        float(top_prob),
        (result.input_tokens, result.output_tokens, result.cost),
    )


def _decide_effort(
    strategy: RoutingStrategy,
    candidate: RoutingCandidate,
    state: dict[str, Any],
    chain: list[tuple[str, EngineAttempt]],
) -> tuple[str | None, float | None, tuple[int, int, float | None], str, str, bool]:
    """Second sequential choice over the picked levels (D-15)."""
    questions = {
        "pick_effort": build_effort_question(
            candidate=candidate, directives=strategy.directives
        )
    }
    order = _effective_order(strategy.engine)
    failed = chain[0][0] if chain else (order[0] if order else "off")
    detail = f"{failed} failed"
    down: list[str] = []
    informative = False
    truncated = False
    spent: tuple[int, int, float | None] = (0, 0, None)
    for name, attempt in chain:
        try:
            result = attempt(strategy, state, questions)
        except Exception:
            result = None
        if result is None:
            continue
        truncated = truncated or result.truncated
        spent = _acc_usage(spent, result)
        if result.answers is None:
            if result.uncertain:
                return (None, None, spent, name, f"{name} uncertain", truncated)
            failed, detail = name, _link_detail(name, result.error)
            if _note_link_error(name, result.error, down):
                informative = True
            continue
        if result.model:
            logger.debug(
                "Routing effort decision via %s served by %s", name, result.model
            )
        top, top_prob, usage_triple = _evaluate_effort_answer(name, result)
        if top is None or usage_triple is None:
            failed, detail = name, _link_detail(name, "invalid table")
            informative = True
            continue
        return top, top_prob, spent, name, "", truncated
    if down and not informative:
        return (None, None, spent, down[-1], _pause_detail(down), truncated)
    return (None, None, spent, failed, detail, truncated)


def _decide_single_candidate(
    strategy: RoutingStrategy,
    *,
    current_model: str,
    side: bool,
    ask: str,
) -> tuple[RoutingPick | None, str, tuple[int, int, float | None], str]:
    """Route the degenerate one-candidate strategy (D-15 fast path).

    No model choice exists, so the lone candidate's id rides through and
    only the effort question runs over its levels; a lone single level
    rides through with no decision call at all.
    """
    only = strategy.candidates[0]
    if not only.levels:
        return (
            None,
            "none",
            (0, 0, None),
            "only candidate advertises no levels",
        )
    if len(only.levels) == 1:
        # Fully degenerate: no model choice and no effort choice —
        # the lone level rides through with no decision call.
        fast = RoutingPick(
            model=only.id,
            effort=only.levels[0],
            model_confidence=None,
            effort_confidence=None,
            tie_break=False,
        )
        if only.id != current_model and not validate_routed_effort(
            fast, strategy.candidates
        ):
            return (
                None,
                "none",
                (0, 0, None),
                f"effort {only.levels[0]!r} unsupported by {only.id}",
            )
        return (fast, "none", (0, 0, None), "")
    state = build_decision_state(ask=ask, directives=strategy.directives, side=side)
    chain = _chain_for(strategy)
    if not chain:
        order = _effective_order(strategy.engine)
        head = order[0] if order else "off"
        return (None, head, (0, 0, None), f"{head} failed")
    (
        effort,
        effort_confidence,
        usage,
        name,
        effort_detail,
        effort_truncated,
    ) = _decide_effort(strategy, only, state, chain)
    if effort is None:
        return (
            None,
            name,
            usage,
            _with_truncation(effort_detail, effort_truncated),
        )
    fast = RoutingPick(
        model=only.id,
        effort=effort,
        model_confidence=None,
        effort_confidence=effort_confidence,
        tie_break=False,
    )
    if only.id != current_model and not validate_routed_effort(
        fast, strategy.candidates
    ):
        return (
            None,
            name,
            usage,
            _with_truncation(
                f"effort {effort!r} unsupported by {only.id}",
                effort_truncated,
            ),
        )
    return (
        fast,
        name,
        usage,
        _with_truncation("", effort_truncated),
    )


def _note_link_error(name: str, error: str | None, down: list[str]) -> bool:
    """File one link failure; True when it judges the pause (informative)."""
    if error in _CONNECTION_ERRORS:
        down.append(name)
        return False
    if error not in (None, "unready"):
        # Skipped and unready links are pause-neutral: never
        # attempted, so only attempted failures judge the pause.
        return True
    return False


def _resolve_effort(
    strategy: RoutingStrategy,
    candidate: RoutingCandidate,
    state: dict[str, Any],
    chain: list[tuple[str, EngineAttempt]],
    result: EngineResult,
) -> tuple[str | None, float | None, tuple[int, int, float | None], bool, str, str]:
    """Read the effort level for a routed candidate (call 2 unless degenerate).

    Returns ``(effort, confidence, total, truncated, engine, detail)``;
    effort None signals a hold, with engine/detail naming the cause and
    ``total`` preserving all paid decision tokens/spend from both calls.
    """
    if len(candidate.levels) == 1:
        # Degenerate choice: nothing to judge, and a one-option
        # question violates the 2-26 floor — the lone level rides
        # through with no effort read.
        return (
            candidate.levels[0],
            None,
            (result.input_tokens, result.output_tokens, result.cost),
            False,
            "",
            "",
        )
    (
        effort,
        effort_confidence,
        effort_usage,
        effort_engine,
        effort_detail,
        effort_truncated,
    ) = _decide_effort(strategy, candidate, state, chain)
    combined = (
        result.input_tokens + effort_usage[0],
        result.output_tokens + effort_usage[1],
        _merge_cost(result.cost, effort_usage[2]),
    )
    return (
        effort,
        effort_confidence,
        combined,
        effort_truncated,
        effort_engine,
        effort_detail,
    )


def _find_candidate(strategy: RoutingStrategy, model_id: str) -> RoutingCandidate:
    """Return the candidate the gate picked (always present: gated ids win)."""
    return next(entry for entry in strategy.candidates if entry.id == model_id)


def _select_model_from_result(
    name: str, result: EngineResult, strategy: RoutingStrategy
) -> tuple[str | None, float | None, bool, str] | None:
    raw = (result.answers or {}).get("pick_model")
    if name == "llm" and isinstance(raw, dict) and raw.get("type") == "llm_choice":
        choice = raw.get("choice")
        live = {candidate.id for candidate in strategy.candidates}
        if not isinstance(choice, str) or choice not in live:
            return None
        return choice, None, False, ""
    answer = validate_choice_answer(raw, strategy.candidates)
    if answer is None:
        return None
    model_id, tie_break, gate_detail = gate_model(answer, strategy)
    if model_id is None:
        return None, None, False, gate_detail
    return model_id, float(answer["probabilities"][model_id]), tie_break, gate_detail


def _evaluate_model_answer(
    name: str,
    result: EngineResult,
    strategy: RoutingStrategy,
    state: dict[str, Any],
    chain: list[tuple[str, EngineAttempt]],
    current_model: str,
    truncated_any: bool,
) -> tuple[
    bool, tuple[RoutingPick | None, str, tuple[int, int, float | None], str] | None
]:
    """Gate and resolve effort for one non-empty model decision result.

    Returns ``(False, None)`` when ``pick_model`` failed schema validation
    (continuing the chain) or ``(True, verdict)`` on route or hard hold.
    """
    call1_usage = (result.input_tokens, result.output_tokens, result.cost)
    selection = _select_model_from_result(name, result, strategy)
    if selection is None:
        return False, None
    model_id, model_confidence, tie_break, gate_detail = selection
    if model_id is None:
        return True, (
            None,
            name,
            call1_usage,
            _with_truncation(gate_detail, truncated_any),
        )
    candidate = _find_candidate(strategy, model_id)
    if not candidate.levels:
        return True, (
            None,
            name,
            call1_usage,
            f"picked candidate {model_id} advertises no levels",
        )
    (
        effort,
        effort_confidence,
        total,
        effort_truncated,
        effort_engine,
        effort_detail,
    ) = _resolve_effort(strategy, candidate, state, chain, result)
    if effort is None:
        return True, (
            None,
            effort_engine,
            total,
            _with_truncation(effort_detail, truncated_any or effort_truncated),
        )
    pick = RoutingPick(
        model=model_id,
        effort=effort,
        model_confidence=model_confidence,
        effort_confidence=effort_confidence,
        tie_break=tie_break,
    )
    shrunk = truncated_any or effort_truncated
    if model_id != current_model and not validate_routed_effort(
        pick, strategy.candidates
    ):
        return True, (
            None,
            name,
            total,
            _with_truncation(
                f"effort {pick.effort!r} unsupported by {model_id}", shrunk
            ),
        )
    return True, (pick, name, total, _with_truncation(gate_detail, shrunk))


def _run_chain(
    strategy: RoutingStrategy,
    state: dict[str, Any],
    questions: dict[str, Any],
    chain: list[tuple[str, EngineAttempt]],
    current_model: str,
) -> tuple[RoutingPick | None, str, tuple[int, int, float | None], str]:
    """Attempt each engine link in order; first valid table routes (D-08)."""
    failed = chain[0][0]
    detail = f"{failed} failed"
    down: list[str] = []
    informative = False
    truncated_any = False
    prior_spent: tuple[int, int, float | None] = (0, 0, None)
    for name, attempt in chain:
        try:
            result = attempt(strategy, state, questions)
        except Exception:
            result = None
        if result is None:
            continue
        truncated_any = truncated_any or result.truncated
        if result.answers is None:
            link_spent = _acc_usage(prior_spent, result)
            if result.uncertain:
                return (
                    None,
                    name,
                    link_spent,
                    _with_truncation(f"{name} uncertain", truncated_any),
                )
            prior_spent = link_spent
            failed, detail = name, _link_detail(name, result.error)
            if _note_link_error(name, result.error, down):
                informative = True
            continue
        if result.model:
            logger.debug("Routing decision via %s served by %s", name, result.model)
        handled, verdict = _evaluate_model_answer(
            name, result, strategy, state, chain, current_model, truncated_any
        )
        if handled and verdict is not None:
            v_pick, v_engine, v_usage, v_detail = verdict
            merged = (
                prior_spent[0] + v_usage[0],
                prior_spent[1] + v_usage[1],
                _merge_cost(prior_spent[2], v_usage[2]),
            )
            return (v_pick, v_engine, merged, v_detail)
        prior_spent = _acc_usage(prior_spent, result)
        failed, detail = name, _link_detail(name, "invalid table")
        informative = True
    if down and not informative:
        return (
            None,
            down[-1],
            prior_spent,
            _with_truncation(_pause_detail(down), truncated_any),
        )
    return (None, failed, prior_spent, _with_truncation(detail, truncated_any))


def decide(
    strategy: RoutingStrategy,
    *,
    current_model: str,
    side: bool = False,
    ask: str,
) -> tuple[RoutingPick | None, str, tuple[int, int, float | None], str]:
    """Route one ask: state build, engine chain, validate, gate.

    Returns ``(pick, engine, usage, detail)`` where engine names the
    model-decision engine on success and the last attempted engine on
    hold, usage sums decision calls into one ``(input, output,
    reported cost)`` triple (preserving paid tokens/spend across holds
    and ``Uncertain`` outcomes), and detail feeds the hold/route notes.
    """
    order = _effective_order(strategy.engine)
    if not order:
        return (None, "off", (0, 0, None), "routing disabled by config")
    if len(strategy.candidates) == 1:
        return _decide_single_candidate(
            strategy, current_model=current_model, side=side, ask=ask
        )
    state = build_decision_state(ask=ask, directives=strategy.directives, side=side)
    questions = {
        "pick_model": build_model_question(
            candidates=strategy.candidates, directives=strategy.directives
        )
    }
    chain = _chain_for(strategy)
    if not chain:
        head = order[0]
        return (None, head, (0, 0, None), f"{head} failed")
    return _run_chain(strategy, state, questions, chain, current_model)


_EFFORT_NO_THINKING = ("auto", "off")
"""Effort values that need no thinking support (harness default / disabled)."""


def _effort_supported_by_target(model_id: str, effort: str) -> bool:
    """True when the target model accepts ``effort`` without upstream ValueError/400."""
    if effort not in _EFFORT_NO_THINKING and not supports_reasoning(model_id):
        return False
    if effort in _EFFORT_NO_THINKING:
        return True
    oai_levels = openai_supported_efforts(model_id)
    if oai_levels is not None:
        return effort in oai_levels
    try:
        import strands_harness.models as harness_models
    except ImportError:
        return True
    normalized = normalize_model_ref(model_id)
    split_fn = getattr(harness_models, "_split_provider", None)
    if callable(split_fn):
        provider, tail = split_fn(normalized)
    else:
        provider, _, tail = normalized.partition("/")
    if provider == "bedrock":
        bedrock_levels_fn = getattr(harness_models, "_bedrock_levels", None)
        if callable(bedrock_levels_fn):
            return effort in bedrock_levels_fn(tail)
    prov_cfg = getattr(harness_models, "_PROVIDERS", {}).get(provider)
    if prov_cfg is not None:
        model_levels_fn = getattr(harness_models, "_model_levels", None)
        levels = (
            model_levels_fn(provider, tail, prov_cfg.thinking_levels)
            if callable(model_levels_fn)
            else prov_cfg.thinking_levels
        )
        return effort in levels
    return True


def validate_routed_effort(
    pick: RoutingPick, candidates: list[RoutingCandidate]
) -> bool:
    """True when the pick effort may apply; False holds current (D-05).

    Pre-mutation gate, run before ``apply_switch``: the effort must sit
    inside the candidate's advertised levels when levels are
    advertised, match any reasoning/OpenAI/Mantle/_MODEL_LEVELS model
    constraints, and never coerce the level down to a supported one (D-08).
    """
    candidate = next((entry for entry in candidates if entry.id == pick.model), None)
    if candidate is None:
        return False
    if candidate.levels is not None and pick.effort not in candidate.levels:
        return False
    return _effort_supported_by_target(pick.model, pick.effort)


def decision_model_for(strategy: RoutingStrategy, engine: str) -> str | None:
    """Decision model id behind one engine name, for /cost accounting.

    ``openrouter`` prices at the API decision model, ``local`` at the
    daemon model, ``native`` at the native model, ``decisions_api`` at
    the decisionapi.net model (default ``~typesafe/jev-latest``), and
    ``llm`` at the LLM router model; anything else (``resolve`` holds,
    unknown engines) has no decision model and prices nothing (T-08-08).
    """
    if engine == "openrouter":
        return strategy.engine.decision_model
    if engine == "local":
        return strategy.engine.local_model
    if engine == "native":
        return strategy.engine.native_model
    if engine == "decisions_api":
        return strategy.engine.decisions_api_model or DECISIONS_API_DEFAULT_MODEL
    if engine == "llm":
        return strategy.engine.llm_model
    return None


def route_cost_delta(new_model: str, prev_model: str, ask: str) -> str:
    """``+0.0123``-style per-ask delta of new vs prev, or ``n/a``.

    Both sides price the same ask estimate (chars/4, symmetric
    in/out proxy); ``n/a`` when either side lacks prices.
    """
    try:
        estimate = estimate_messages_tokens(
            [{"role": "user", "content": [{"text": ask}]}]
        )
        new_cost = cost_for(estimate, estimate, new_model)
        prev_cost = cost_for(estimate, estimate, prev_model)
    except Exception:
        return "n/a"
    if new_cost is None or prev_cost is None:
        return "n/a"
    return f"{new_cost - prev_cost:+.4f}"


def _confidence_cell(value: float | None) -> str:
    """Percent cell for one confidence (n/a when no read exists)."""
    return f"{value:.0%}" if value is not None else "n/a"


def format_routed_line(
    *,
    model: str,
    effort: str,
    model_confidence: float | None,
    effort_confidence: float | None = None,
    tie_break: bool = False,
    truncated: bool = False,
    prev_model: str,
    ask: str,
    side: bool = False,
) -> str:
    """One transcript line for a routed ask (D-12).

    Choice plus both confidences plus the code-computed ``~$/ask``
    delta, with the tie-break substitution noted on the line. Side
    asks print the ``Routed (btw)`` head so the transcript tells
    spawn-time side picks apart from main-turn picks. A shrunken
    payload appends the truncation marker.
    """
    delta = route_cost_delta(model, prev_model, ask)
    head = "Routed (btw)" if side else "Routed"
    line = (
        f"{head} \u2192 {model} ({effort}): "
        f"model {_confidence_cell(model_confidence)}, "
        f"effort {_confidence_cell(effort_confidence)} "
        f"\u00b7 ~${delta}/ask vs {prev_model}"
    )
    if tie_break:
        line += " \u00b7 tie-break (cheaper of near-tie)"
    if truncated:
        line += f" \u00b7 {TRUNCATION_MARKER}"
    return line


def format_hold_line(*, current: str, detail: str) -> str:
    """Hold-current note with the reason detail (D-08, D-16).

    Engine failures pass ``"<engine> failed"`` (the long-standing
    shape); the threshold gate passes its ``confidence <read> <
    <threshold>`` read so the note names both numbers.
    """
    return f"Routing held on {current} ({detail}; retrying next ask)"


ROUTING_ON_REPLY = "Routing on — asks route pre-turn through the decision model."
ROUTING_OFF_REPLY = "Routing off — the current model serves every ask."
ROUTE_USAGE = "Usage: /route [on|off|status|setup|validate]"
MODEL_ROUTING_KEEP_REPLY = "Model unchanged — routing stays on."
ROUTING_MANUAL_OFF_NOTE = "Routing off — manual /model wins; /route on to re-enable."


class RoutingState:
    """Session-sticky routing toggle (D-10; mirrors :class:`ModeState`).

    ``state`` is ``"on"`` or ``"off"`` (anything else raises
    ``ValueError``). The loop owns one instance, defaulting to on when
    a strategy configures; ``/route`` flips it and a confirmed manual
    ``/model`` switch turns it off. The pause flag is separate and
    turn-scoped: an all-refused ask pauses same-turn decisions with
    zero new POSTs, and the next pre-turn hook resumes.
    """

    VALID = ("on", "off")

    def __init__(self, initial: str = "on") -> None:
        if initial not in self.VALID:
            raise ValueError(f"unknown routing state {initial!r}: expected on|off")
        self._state = initial
        self._paused = False

    @property
    def state(self) -> str:
        """Current toggle state (``"on"`` or ``"off"``)."""
        return self._state

    def is_on(self) -> bool:
        """True when the pre-turn hook may route."""
        return self._state == "on"

    def is_paused(self) -> bool:
        """True when an all-refused ask paused this turn's decisions."""
        return self._paused

    def pause(self) -> None:
        """Pause routing for the ask: later same-turn decisions skip."""
        self._paused = True

    def resume(self) -> None:
        """Clear the pause: the next ask attempts its decision calls."""
        self._paused = False

    def set(self, state: str) -> str:
        """Flip the toggle; returns the transcript announcement.

        Raises:
            ValueError: For anything outside ``on|off``.
        """
        if state not in self.VALID:
            raise ValueError(f"unknown routing state {state!r}: expected on|off")
        self._state = state
        return ROUTING_ON_REPLY if state == "on" else ROUTING_OFF_REPLY

    def announce(self, strategy: RoutingStrategy | None = None) -> str:
        """Bare-status report for ``/route`` (toggle plus strategy detail)."""
        return route_status_text(self, strategy)


def route_status_text(routing: RoutingState, strategy: RoutingStrategy | None) -> str:
    """Full ``/route status`` report: toggle, source, engine, count."""
    lines = [f"Routing: {routing.state}"]
    if strategy is None:
        lines.append("Strategy: none configured")
        return "\n".join(lines)
    source = str(strategy.source) if strategy.source is not None else "(unsaved)"
    count = len(strategy.candidates)
    noun = "candidate" if count == 1 else "candidates"
    lines.append(f"Strategy: {source} ({count} {noun})")
    if not strategy.engine.order:
        lines.append("Engine: off")
    else:
        chain_parts = ", ".join(
            f"{name} ({decision_model_for(strategy, name) or 'none'})"
            for name in strategy.engine.order
        )
        lines.append(f"Engine: {chain_parts}")
    return "\n".join(lines)


def warn_applies(routing: RoutingState | None) -> bool:
    """True when ``/model`` must warn: toggle on AND a strategy configures."""
    if routing is None or not routing.is_on():
        return False
    try:
        strategy = load_strategy()
    except ValueError:
        return False
    return strategy is not None and bool(strategy.candidates)
